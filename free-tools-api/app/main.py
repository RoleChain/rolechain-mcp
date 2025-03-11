from fastapi import FastAPI, UploadFile, File, HTTPException, Form, BackgroundTasks, Request, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydub import AudioSegment
import tempfile
import uuid
import os
from firebase_admin import credentials, firestore, storage
from pydantic import BaseModel
import firebase_admin
from moviepy.editor import VideoFileClip
from app.services.youtube_service import get_proxy_config
import shutil
import time
import asyncio
import urllib.parse
from celery import Celery
import yt_dlp as youtube_dl
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse
from typing import Dict, Optional
from datetime import timedelta
import redis
from celery.result import AsyncResult
from fastapi.security.api_key import APIKeyHeader
import secrets

# Load environment variables from the .env file
from dotenv import load_dotenv
load_dotenv()

from app.routes.youtube_route import router as youtube_router, init_router

import subprocess

from concurrent.futures import ThreadPoolExecutor

# initialize firebase app
cred = credentials.Certificate("./app/cred.json")
firebase_admin.initialize_app(cred, {
    'storageBucket': 'code-translate-c9640.appspot.com',
})
db = firestore.client()

celery_app = Celery(
    "tasks",
    broker= "redis://localhost:6379/0",
    backend= "redis://localhost:6379/0",
)

# Create ThreadPoolExecutor instance
executor = ThreadPoolExecutor(max_workers=32)

# Add these constants near the top of the file
API_KEY_NAME = "X-API-Key"
API_KEY = os.getenv("API_KEY")  # Make sure to add this to your .env file
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

# Add this function to verify the API key
async def verify_api_key(api_key: str = Security(api_key_header)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured on server")
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

# Update the app creation to require API key for all routes
app = FastAPI(dependencies=[Depends(verify_api_key)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# After creating the executor
init_router(executor)
app.include_router(youtube_router)

COOKIES_FILE_PATH = './app/routes/cookies.json'


class YouTubeToWavRequest(BaseModel):
    url: str

class YouTubeToMp4Request(BaseModel):
    url: str

class VideoInfo(BaseModel):
    """Response model for video information"""
    title: str
    duration: int
    thumbnail: str
    formats: list
    description: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None

# Function to upload file to Firebase
def upload_file_to_firebase(file_path, content_type='audio/mpeg', folder_name='free_audio_conversions'):
    # Create a unique filename for the storage
    filename = f"{uuid.uuid4()}.{file_path.split('.')[-1]}"
    # Specify the folder path in Firebase storage
    firebase_path = f"{folder_name}/{filename}"
    bucket = storage.bucket()
    blob = bucket.blob(firebase_path)
    blob.upload_from_filename(file_path, content_type=content_type)
    blob.make_public()  # Make the file publicly accessible
    return blob.public_url

def get_proxy_config_sync():
    return asyncio.run(get_proxy_config())

# Function to download audio from YouTube and convert to WAV
@celery_app.task(bind=True)
def download_audio_from_youtube_wav(self, url: str) -> str:
    """Downloads YouTube audio and converts it to WAV format."""
    cleaned_url = urllib.parse.quote(url.strip(), safe=':/?&=')
    self.update_state(state='PROGRESS', meta={'progress': 0})
    # Check if cookies file exists
    if not os.path.exists(COOKIES_FILE_PATH):
        raise HTTPException(status_code=400, detail="Cookies file not found")
    
    download_dir = "/app/youtube_audio"
    os.makedirs(download_dir, exist_ok=True)

    try:
        # Get a new proxy for each retry attempt
        retry_count = self.request.retries
        if retry_count > 0:
            proxy_config = get_proxy_config_sync()
            print(f"Retry {retry_count} with new proxy: {proxy_config}")
        else:
            proxy_config = get_proxy_config_sync()
        self.update_state(state='PROGRESS', meta={'progress': 20})
        # yt-dlp options for direct WAV conversion
        ydl_opts = {
            'format': 'worstaudio/worst',
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '64',
            }],
            'postprocessor_args': [
                '-preset', 'ultrafast',
                '-threads', '2',
                '-b:a', '64k',
                '-ar', '22050'
            ],
            'noplaylist': True,
            'retries': 3,
            'socket_timeout': 4,
            'cookies': COOKIES_FILE_PATH,
            'proxy': proxy_config,
            'outtmpl': f"{download_dir}/%(id)s.%(ext)s",
            'buffer-size': '32M',
        }
        self.update_state(state='PROGRESS', meta={'progress': 40})

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            # First, check duration without downloading
            info = ydl.extract_info(cleaned_url, download=False)
            
            # Check duration first - this will fail fast if video is too long
            if info.get('duration', 0) > 1200:  # 20 minutes in seconds
                raise HTTPException(
                    status_code=400, 
                    detail="Duration is greater than 20 minutes"
                )
            
            # If duration is okay, proceed with download
            info = ydl.extract_info(cleaned_url, download=True)
            wav_file_path = f"{download_dir}/{info['id']}.wav"
            self.update_state(state='PROGRESS', meta={'progress': 80})
            if not os.path.exists(wav_file_path):
                raise FileNotFoundError(f"WAV file not found: {wav_file_path}")
            
            self.update_state(state='PROGRESS', meta={'progress': 100})

            return wav_file_path

    except HTTPException as e:
        # Don't retry for HTTP exceptions (like duration too long)
        print(f"HTTP Exception: {e.detail}")
        raise e
    except Exception as e:
        print(f"Error in download_audio_from_youtube_wav: {e}")
        # Retry up to 5 times with exponential backoff for other errors
        if self.request.retries < 5:
            # Pass only the string representation of the error
            raise self.retry(exc=str(e), countdown=2 ** self.request.retries)
        raise Exception(f"Failed after 5 attempts: {str(e)}")

@app.post("/youtube-to-wav")
async def youtube_to_wav(request: YouTubeToWavRequest):
    """API endpoint for converting YouTube video to WAV format."""
    start_time = time.time()

    try:
        # Start the Celery task and wait for result
        task = download_audio_from_youtube_wav.delay(request.url)

        return {"success": True, "task_id": task.id}


    except HTTPException as error:
        # Handle HTTP exceptions (including duration too long)
        return JSONResponse(
            content={
                "success": False,
                "error": error.detail,
                "time_taken": time.time() - start_time
            },
            status_code=error.status_code
        )
    except Exception as error:
        error_message = str(error)
        status_code = 500
        
        if "Max retries exceeded" in error_message:
            error_message = "Failed to download after multiple attempts with different proxies"
            
        return JSONResponse(
            content={
                "success": False,
                "error": error_message,
                "time_taken": time.time() - start_time
            },
            status_code=status_code
        )
    
@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of a Celery task and its result if complete."""
    try:
        task_result = AsyncResult(task_id)
        
        if task_result.ready():
            if task_result.successful():
                file_path = task_result.get()
                try:
                    # Determine content type based on file extension
                    content_type = 'audio/wav' if file_path.endswith('.wav') else 'video/mp4'
                    
                    # Upload to Firebase and get URL
                    download_url = upload_file_to_firebase(file_path, content_type=content_type)
                finally:
                    # Always clean up the file after upload attempt
                    if os.path.exists(file_path):
                        await async_remove_file(file_path)
                
                return {
                    "status": "completed",
                    "file_url": download_url
                }
            else:
                # Task failed
                error = str(task_result.result)
                return {
                    "status": "failed",
                    "error": error
                }
        else:
            # Task is still running
            return {
                "status": "processing",
                "progress": task_result.info.get('progress', 0) if task_result.info else 0
            }

    except Exception as error:
        return JSONResponse(
            content={
                "status": "error",
                "error": str(error)
            },
            status_code=500
        )

def get_formats(url):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'extract_flat': True,
            # 'force_generic_extractor': True,  # Consider removing this line
        }
        print("Downloading formats")
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # return those formats where audio or both video and audio is available
            formats = [{'quality': f['format_note'], 'itag': f['format_id'], 'type': 'audio' if f.get('height') is None else 'video'} for f in info['formats'] if 'format_note' in f and f.get('audio_channels') is not None]
            return formats
    except Exception as e:
        print(f"Error occurred: {e}")  # Print the original error message for debugging
        raise Exception("Failed to retrieve formats.") from e

async def download_video(url: str, itag: str):
    if url is None:
        raise ValueError("URL is required")
    
    max_retries = 5  # Set maximum retries
    for attempt in range(max_retries):
        try:
            # Define options for yt-dlp
            proxy_config = await get_proxy_config()  # Get proxy config asynchronously
            
            ydl_opts = {
                'format': itag,
                'outtmpl': '%(id)s.%(ext)s',
                'quiet': True,
                'noplaylist': True,
                'proxy': proxy_config,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '64',  # Low bitrate for smaller file size and faster processing
                }],
                'postprocessor_args': [
                    '-c:v', 'libx264',  # Ensure H.264 for video
                    '-c:a', 'aac',      # Ensure AAC for audio
                    '-strict', 'experimental',  # Enable experimental AAC support
                    '-movflags', 'faststart'    # Makes MP4 file more compatible for streaming
                ],
            }
            
            # Run blocking code in a separate thread using the executor
            return await asyncio.get_event_loop().run_in_executor(executor, download_video_blocking, url, ydl_opts)

        except Exception as e:
            if "Download ETA or fragment size is greater than 150" in str(e):
                raise Exception("Download ETA or fragment size is greater than 150.") from e
            if attempt == max_retries - 1:
                raise  # Raise the last exception if all attempts fail
            print(f"Attempt {attempt + 1} failed with proxy {proxy_config}: {str(e)}")  # Log the error and attempt number

def download_video_blocking(url: str, ydl_opts: dict) -> str:
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info['title']
        filename = f"{title}.mp4"
        file_path = os.path.join(os.getcwd(), filename)
        return file_path

def remove_file(file_path: str):
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"File {file_path} has been removed.")

@celery_app.task(bind=True)
def download_audio_from_youtube_mp3(self, url: str) -> str:
    """Downloads YouTube audio and converts it to MP3 format."""
    if url is None:
        raise ValueError("URL is required")
    
    self.update_state(state='PROGRESS', meta={'progress': 0})
    
    try:
        # Get proxy config synchronously for Celery task
        proxy_config = get_proxy_config_sync()
        self.update_state(state='PROGRESS', meta={'progress': 20})
        
        ydl_opts = {
            'format': 'worstaudio/worst',
            'outtmpl': '%(id)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '64',
            }],
            'postprocessor_args': [
                '-preset', 'ultrafast',
                '-threads', '8',
                '-b:a', '64k',
                '-ar', '22050'
            ],
            'noplaylist': True,
            'retries': 3,
            'socket_timeout': 4,
            'cookies': COOKIES_FILE_PATH,
            'proxy': proxy_config,
            'extractaudio': True,
            'concurrent-fragments': 4,
            'concurrent-downloads': 4,
            'buffer-size': '32M',
        }

        self.update_state(state='PROGRESS', meta={'progress': 40})

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            # Check duration first
            info = ydl.extract_info(url, download=False)
            if info.get('duration', 0) > 1200:
                raise HTTPException(
                    status_code=400,
                    detail="Duration is greater than 20 minutes"
                )
            
            self.update_state(state='PROGRESS', meta={'progress': 60})
            
            # If duration is okay, proceed with download
            info = ydl.extract_info(url, download=True)
            mp3_filename = f"{info['id']}.mp3"
            mp3_file_path = os.path.join(os.getcwd(), mp3_filename)
            
            self.update_state(state='PROGRESS', meta={'progress': 80})
            
            if not os.path.exists(mp3_file_path):
                raise FileNotFoundError(f"MP3 file not found: {mp3_file_path}")
            
            self.update_state(state='PROGRESS', meta={'progress': 100})    
            return mp3_file_path

    except HTTPException as e:
        print(f"HTTP Exception: {e.detail}")
        raise e
    except Exception as e:
        print(f"Error in download_audio_from_youtube_mp3: {e}")
        if self.request.retries < 5:
            raise self.retry(exc=str(e), countdown=2 ** self.request.retries)
        raise Exception(f"Failed after 5 attempts: {str(e)}")

# @app.post("/youtube-video-mp3-convert")
# async def convert_to_mp3_controller(request: YouTubeToWavRequest):
#     """API endpoint for converting YouTube video to MP3 format."""
#     start_time = time.time()

#     try:
#         # Start the Celery task and wait for result
#         task = download_audio_from_youtube_mp3.delay(request.url)
#         return {"success": True, "task_id": task.id}

#     except HTTPException as error:
#         return JSONResponse(
#             content={
#                 "success": False,
#                 "error": error.detail,
#                 "time_taken": time.time() - start_time
#             },
#             status_code=error.status_code
#         )
#     except Exception as error:
#         error_message = str(error)
#         status_code = 500
        
#         if "Max retries exceeded" in error_message:
#             error_message = "Failed to download after multiple attempts with different proxies"
            
#         return JSONResponse(
#             content={
#                 "success": False,
#                 "error": error_message,
#                 "time_taken": time.time() - start_time
#             },
#             status_code=status_code
#         )

def convert_audio(file, target_format="mp3"):
    # Load audio (assuming the file is in a format recognizable by pydub, e.g., "wav", "mp4", etc.)
    audio = AudioSegment.from_file(file)
    # Convert audio to target format and save to a temporary file
    temp_file = tempfile.NamedTemporaryFile(
        delete=False, suffix=f".{target_format}")
    audio.export(temp_file.name, format=target_format)
    return temp_file


async def convert_video(upload_file: UploadFile, target_format="mp4"):
    temp_file_path = None
    try:
        # Save the uploaded file to a temporary file asynchronously
        temp_file_path = f"{uuid.uuid4()}.tmp"
        with open(temp_file_path, 'wb') as temp_file:
            content = await upload_file.read()
            temp_file.write(content)

        # Define codecs based on the output format
        codec = "libx264"
        audio_codec = "aac"
        if target_format == "webm":
            codec, audio_codec = "libvpx", "libvorbis"
        elif target_format == "mpeg":
            codec, audio_codec = "mpeg2video", "mp2"

        # Output file path
        output_file_path = f"{temp_file_path}_converted.{target_format}"

        # Convert the video using FFmpeg asynchronously
        command = [
            'ffmpeg',
            '-y',  # Overwrite existing files
            '-i', temp_file_path,
            '-c:v', codec,
            '-c:a', audio_codec,
            output_file_path
        ]

        # Run FFmpeg command asynchronously
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        # Check FFmpeg process for errors
        if process.returncode != 0:
            print(f"FFmpeg error: {stderr.decode()}")
            raise RuntimeError("FFmpeg conversion failed.")

        return output_file_path
    except Exception as e:
        print(f"Error during video conversion: {str(e)}")
        raise HTTPException(status_code=500, detail="Video conversion failed.")
    finally:
        # Clean up the temporary input file
        if temp_file_path and os.path.exists(temp_file_path):
            await asyncio.get_event_loop().run_in_executor(None, os.unlink, temp_file_path)


@app.get("/")
async def hello():
    return "Welcome"


@app.post("/convert-audio")
async def convert_audio_endpoint(audio_file: UploadFile = File(...), output_format: str = Form("mp3")):
    supported_formats = {"mp3", "aac", "flac", "ogg", "wma", "aiff", "wav", "m4a"}

    # Validate output format
    if output_format not in supported_formats:
        raise HTTPException(status_code=400, detail=f"Invalid output format: {output_format}")

    try:
        # Use ffmpeg method for m4a, wma, and aac
        if output_format in {"m4a", "wma", "aac"}:
            # Create a temporary file for the input audio
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as input_file:
                input_file.write(audio_file.file.read())
                input_file.flush()
                input_file_path = input_file.name

            output_file_path = tempfile.mktemp(suffix=f".{output_format}")
            
            # Determine the codec based on output format
            codec = {
                "m4a": "aac",
                "wma": "wmav2",
                "aac": "aac"
            }[output_format]
            
            # Construct the ffmpeg command
            command = [
                'ffmpeg',
                '-y',
                '-i', input_file_path,
                '-c:a', codec,
                output_file_path
            ]

            # Convert the audio using ffmpeg
            process = subprocess.run(command, capture_output=True, text=True)
            
            # Check if the conversion was successful
            if process.returncode != 0:
                raise RuntimeError(f"Error converting file: {process.stderr.strip()}")
            
            # Clean up input file
            os.unlink(input_file_path)
            
            converted_file_path = output_file_path
        else:
            # Use original pydub method for other formats
            converted_file = convert_audio(audio_file.file, output_format)
            converted_file_path = converted_file.name

        # Upload to Firebase and get download URL
        download_url = upload_file_to_firebase(converted_file_path)
        
        # Clean up the temporary file
        os.unlink(converted_file_path)

        return {"download_url": download_url}

    except Exception as e:
        print(f"Error during conversion: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    

@app.post("/convert-video")
async def convert_video_endpoint(video_file: UploadFile = File(...), output_format: str = Form("mp4")):
    supported_formats = {"mp4", "avi", "mov", "flv", "mkv", "webm", "3gp", "mpeg"}

    if output_format not in supported_formats:
        raise HTTPException(status_code=400, detail=f"Invalid output format: {output_format}")
    
    # Check file size asynchronously
    content = await video_file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded video file is empty.")
    
    # Reset file pointer
    await video_file.seek(0)

    try:
        # Convert video asynchronously
        converted_file_path = await convert_video(video_file, output_format)
        
        # Upload to Firebase (this is synchronous - consider making async if needed)
        download_url = upload_file_to_firebase(
            converted_file_path, 
            content_type='video/mp4', 
            folder_name='free_video_conversions'
        )
        
        # Schedule async cleanup
        asyncio.create_task(async_remove_file(converted_file_path))

        return {"download_url": download_url}

    except Exception as e:
        print(f"Error during conversion: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/youtube-video-format")
async def get_formats_controller(url: str):
    print("Request received")
    try:
        formats = get_formats(url)
        return {"success": True, "data": {'formats': formats}}
    except Exception as error:
        print(f"Error during get_formats_controller: {str(error)}")
        return {"success": False, "error": str(error)}, 400

# Add this helper function for async file cleanup
async def async_remove_file(file_path: str):
    """Asynchronously remove a file using asyncio."""
    if os.path.exists(file_path):
        # Use asyncio to run file removal in a thread pool
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, os.unlink, file_path)
        print(f"File {file_path} has been removed asynchronously.")
 

# Update the youtube-video-download endpoint
@app.post("/youtube-video-download")
async def download_video_controller(request: YouTubeToMp4Request):
    try:
        file_path = await download_video(request.url, request.itag)
        
        # Upload the video to Firebase and get the download URL
        download_url = upload_file_to_firebase(file_path, content_type='video/mp4', folder_name='free_video_downloads')
        
        # Schedule async file cleanup
        asyncio.create_task(async_remove_file(file_path))
        
        return JSONResponse(content={"success": True, "file_url": download_url})
    except Exception as error:
        return JSONResponse(content={"success": False, "error": str(error)}, status_code=400)
    

@celery_app.task(bind=True)
def download_video_from_youtube_mp4(self, url: str) -> str:
    """Downloads YouTube video and converts it to MP4 format."""
    self.update_state(state='PROGRESS', meta={'progress': 0})
    
    # Ensure download directory exists
    download_dir = "/app/youtube_video"
    os.makedirs(download_dir, exist_ok=True)

    # Path to your logo file - adjust this path as needed
    logo_path = "./app/assets/watermark.png"
    if not os.path.exists(logo_path):
        raise FileNotFoundError(f"Logo file not found at {logo_path}")

    try:
        # Get proxy configuration
        proxy_config = get_proxy_config_sync()
        self.update_state(state='PROGRESS', meta={'progress': 20})
        
        # Generate unique filename using UUID
        unique_filename = f"{uuid.uuid4()}.mp4"
        output_template = os.path.join(download_dir, unique_filename)
        
        # Configure yt-dlp options with more robust post-processing
        ydl_opts = {
            'outtmpl': output_template,
            'proxy': proxy_config,
            'concurrent_fragment_downloads': 5,
            'format': 'bv*[height<=1080]+ba/best[height<=1080]',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'cookies': COOKIES_FILE_PATH,
            'quiet': True,
            'no_warnings': True,
            # FFmpeg post-processing options
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': [
                # Video codec settings
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                # Audio codec settings
                '-c:a', 'aac',
                '-b:a', '128k',
                # Watermark settings
                '-vf', f'movie={logo_path}[watermark];[in][watermark]overlay=main_w-overlay_w-10:main_h-overlay_h-10:format=auto,format=yuv420p[out]',
                # Container settings
                '-movflags', '+faststart',
                # Error handling
                '-err_detect', 'ignore_err',
                '-xerror'
            ],
            # Additional options to handle errors
            'ignoreerrors': True,
            'continue': True,
            'retries': 10,
            'fragment_retries': 10,
            'file_access_retries': 5,
        }

        self.update_state(state='PROGRESS', meta={'progress': 40})

        # First check video duration
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise Exception('Failed to fetch video metadata')
                
            duration = info.get('duration', 0)
            if duration > 1200:  # 20 minutes
                raise HTTPException(
                    status_code=400,
                    detail=f"Video duration is too long with {duration} seconds, max is 1200 seconds"
                )
            
            self.update_state(state='PROGRESS', meta={'progress': 60})
            
            try:
                # If duration is acceptable, proceed with download
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise Exception('Failed to download video')
            except Exception as e:
                if "Postprocessing: Conversion failed" in str(e):
                    # Try one more time with simpler settings
                    ydl_opts['postprocessor_args'] = [
                        '-c:v', 'libx264',
                        '-c:a', 'aac',
                        '-vf', f'movie={logo_path}[watermark];[in][watermark]overlay=main_w-overlay_w-10:main_h-overlay_h-10:format=auto,format=yuv420p[out]',
                        '-movflags', '+faststart'
                    ]
                    info = ydl.extract_info(url, download=True)
                else:
                    raise
                
            self.update_state(state='PROGRESS', meta={'progress': 80})
            
            # Verify file exists
            if not os.path.exists(output_template):
                raise FileNotFoundError(f"MP4 file not found: {output_template}")
            
            self.update_state(state='PROGRESS', meta={'progress': 100})
            
            return output_template

    except HTTPException as e:
        print(f"HTTP Exception: {e.detail}")
        raise e
    except Exception as e:
        print(f"Error in download_video_from_youtube_mp4: {e}")
        if self.request.retries < 5:
            raise self.retry(exc=Exception(str(e)), countdown=2 ** self.request.retries)
        raise Exception(f"Failed after 5 attempts: {str(e)}")

@app.post("/youtube-to-mp4")
async def youtube_to_mp4(request: YouTubeToMp4Request):
    """API endpoint for converting YouTube video to MP4 format."""
    start_time = time.time()

    try:
        # Start the Celery task
        task = download_video_from_youtube_mp4.delay(request.url)
        return {"success": True, "task_id": task.id}

    except HTTPException as error:
        return JSONResponse(
            content={
                "success": False,
                "error": error.detail,
                "time_taken": time.time() - start_time
            },
            status_code=error.status_code
        )
    except Exception as error:
        error_message = str(error)
        status_code = 500
        
        if "Max retries exceeded" in error_message:
            error_message = "Failed to download after multiple attempts with different proxies"
            
        return JSONResponse(
            content={
                "success": False,
                "error": error_message,
                "time_taken": time.time() - start_time
            },
            status_code=status_code
        )

@app.get("/youtube-video-info")
async def get_video_info(url: str):
    """
    Fetch video information and available formats from YouTube
    Returns title, duration, thumbnail, and available formats with direct URLs
    """
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            # Configure yt-dlp options for faster extraction
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,  # Faster extraction
                'skip_download': True,  # Ensure no download attempts
                'cookies': COOKIES_FILE_PATH,
                'format': 'best',  # Only get best format initially
                'socket_timeout': 3,  # Reduce timeout
                'retries': 2,  # Reduce retries for faster failure
            }

            # Get new proxy configuration for each attempt
            proxy_config = await get_proxy_config()
            if proxy_config:
                ydl_opts['proxy'] = proxy_config
                print(f"Attempt {attempt + 1} with proxy: {proxy_config}")

            # Run the extraction in a thread pool to not block
            def extract_info():
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            # Execute in thread pool
            info = await asyncio.get_event_loop().run_in_executor(executor, extract_info)
                
            # Format response to match desired structure
            video_info = {
                "success": True,
                "title": info.get('title'),
                "duration": info.get('duration'),
                "view_count": info.get('view_count'),
                "description": info.get('description'),
                "thumbnail": info.get('thumbnail'),
                "formats": [
                    {
                        'resolution': f'{f.get("width", "?")}x{f.get("height", "?")}',
                        'quality': f['format_note'],
                        'itag': f['format_id'],
                        'type': 'video+audio' if f.get('acodec') != 'none' else 'video',
                        'url': f['url'],
                        'ext': f['ext']
                    }
                    for f in info.get('formats', [])
                    if 'format_note' in f and f.get('vcodec') != 'none'  # Only include formats with video
                ]
            }

            return JSONResponse(content=video_info)

        except Exception as error:
            last_error = error
            print(f"Attempt {attempt + 1} failed with error: {str(error)}")
            if attempt < max_retries - 1:
                # Wait a bit before retrying with exponential backoff
                await asyncio.sleep(2 ** attempt)
                continue
            
    # If we get here, all attempts failed
    print(f"All {max_retries} attempts failed. Last error: {str(last_error)}")
    return JSONResponse(
        content={
            "success": False,
            "error": f"Failed after {max_retries} attempts with different proxies. Last error: {str(last_error)}"
        },
        status_code=400
    )

if __name__ == '__main__':
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=16,  # Matches number of vCPUs
        loop="uvloop",  # High-performance event loop
        limit_concurrency=1000,  # Allows more concurrent requests per worker
        backlog=2048  # Queue up more connections before rejecting
    )
    
    
