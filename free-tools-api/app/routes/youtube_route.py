import time
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, FileResponse,  StreamingResponse  
from pydantic import BaseModel
import yt_dlp as youtube_dl
from app.services.youtube_service import get_transcript, download_audio_from_youtube, transcribe_audio
from app.services.youtube_service import get_proxy_config
from cachetools import TTLCache
import os
import urllib.parse  # To handle URL encoding
from io import BytesIO
from pydub import AudioSegment
import re

router = APIRouter()
_executor = None

# Cache configurations for video info and transcripts
video_cache = TTLCache(maxsize=100, ttl=3600)  # Cache for video info with TTL of 1 hour
transcript_cache = TTLCache(maxsize=100, ttl=3600)  # Cache for transcripts with TTL of 1 hour

# Path to cookies file
COOKIES_FILE_PATH = './app/routes/cookies.json'


# Model for Transcript Request
class TranscriptRequest(BaseModel):
    url: str


def is_valid_youtube_url(url: str) -> bool:
    """Validate YouTube URL format."""
    youtube_regex = (
        r'(?:https?:\/\/)?(?:www\.)?'
        r'(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|'
        r'youtu\.be\/)([a-zA-Z0-9_-]{11})'
    )
    return bool(re.match(youtube_regex, url))


def init_router(executor):
    global _executor
    _executor = executor


async def fetch_video_info(url: str) -> dict:
    """Fetches video info with yt-dlp, using proxy configuration and cookies."""
    
    # Ensure URL is properly encoded to handle special characters and query params
    cleaned_url = urllib.parse.quote(url.strip(), safe=':/?&=')  # Quote the URL while preserving query parameters
    
    # Check if cookies file exists
    if os.path.exists(COOKIES_FILE_PATH):
        cookies = COOKIES_FILE_PATH
    else:
        cookies = None  # Set cookies to None if not found

    max_retries = 5  # Set maximum retries
    for attempt in range(max_retries):
        try:
            proxy_config = await get_proxy_config()  # Get a new proxy for each attempt
            print(proxy_config)

            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',  # Get best quality video with audio
                'quiet': True,
                'extract_flat': True,
                'skip_download': True,
                'noplaylist': True,
                'retries': 5,  # Keep retries for yt-dlp
                'socket_timeout': 5,  # Reduce timeout to speed up the process
                'cookies': cookies,  # Use cookies if the file exists
                'proxy': proxy_config,  # Use proxy configuration
            }

            # Run blocking code (yt-dlp) in a separate thread
            return await asyncio.get_event_loop().run_in_executor(
                _executor,  # Use the passed executor
                fetch_video_info_blocking,
                cleaned_url,
                ydl_opts
            )

        except Exception as e:
            # logger.error(f"Attempt {attempt + 1} failed with proxy {proxy_config}: {str(e)}")
            if attempt == max_retries - 1:
                raise  # Raise the last exception if all attempts fail


def fetch_video_info_blocking(url: str, ydl_opts: dict) -> dict:
    """Fetch video info using yt-dlp (blocking version)."""
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            raise e


async def fetch_transcript(url: str) -> str:
    """Fetches transcript asynchronously if not cached."""
    if url in transcript_cache:
        return transcript_cache[url]

    # Get transcript
    transcript = await get_transcript(url)
    # Cache the result
    transcript_cache[url] = transcript
    return transcript


@router.post("/youtube-video-transcript")
async def get_transcript_controller(request: TranscriptRequest):
    """API endpoint for generating YouTube video transcript."""
    if not is_valid_youtube_url(request.url):
        return JSONResponse(
            content={"success": False, "error": "Invalid YouTube URL format"},
            status_code=400
        )
    
    start_time = time.time()  # Start time for transcript fetching

    try:
        # Get transcript
        transcript = await fetch_transcript(request.url)
        end_time = time.time()  # End time after fetching the transcript
        time_taken = end_time - start_time  # Calculate the time taken
        return JSONResponse(content={"success": True, "transcript": transcript, "time_taken": time_taken})
    except Exception as error:
        end_time = time.time()  # End time on error
        time_taken = end_time - start_time  # Calculate time taken
        return JSONResponse(content={"success": False, "error": str(error), "time_taken": time_taken}, status_code=400)


# @router.get("/youtube-video-info")
# async def get_video_info(url: str):
#     """API endpoint for fetching YouTube video info."""
#     if not is_valid_youtube_url(url):
#         return JSONResponse(
#             content={"success": False, "error": "Invalid YouTube URL format"},
#             status_code=400
#         )
    
#     start_time = time.time()
#     cleaned_url = urllib.parse.quote(url.strip(), safe=':/?&=')
    
#     # Check cache first
#     if cleaned_url in video_cache:
#         end_time = time.time()
#         time_taken = end_time - start_time
#         return JSONResponse(content=video_cache[cleaned_url])

#     max_retries = 5
#     last_error = None
    
#     for attempt in range(max_retries):
#         try:
#             # Fetch video info concurrently
#             info = await fetch_video_info(cleaned_url)
            
#             # Prepare the response with relevant video details
#             video_info = {
#                 "success": True,
#                 "title": info.get('title'),
#                 "duration": info.get('duration'),
#                 "view_count": info.get('view_count'),
#                 "description": info.get('description'),
#                 "thumbnail": info.get('thumbnail'),
#                 "formats": [
#                     {
#                         'resolution': f'{f.get("width", "?")}x{f.get("height", "?")}',
#                         'quality': f['format_note'],
#                         'itag': f['format_id'],
#                         'type': 'video+audio' if f.get('acodec') != 'none' else 'video',
#                         'url': f['url'],
#                         'ext': f['ext']
#                     }
#                     for f in info.get('formats', [])
#                     if 'format_note' in f and f.get('vcodec') != 'none'  # Only include formats with video
#                 ]
#             }

#             # Cache video info
#             video_cache[cleaned_url] = video_info
#             end_time = time.time()
#             time_taken = end_time - start_time
#             return JSONResponse(content=video_info)

#         except Exception as error:
#             last_error = error
#             continue

#     # If all retries failed
#     end_time = time.time()
#     time_taken = end_time - start_time
#     return JSONResponse(
#         content={"success": False, "error": str(last_error), "time_taken": time_taken},
#         status_code=400
#     )


@router.get("/youtube-audio-info")
async def get_audio_info(url: str):
    """API endpoint for fetching YouTube audio info and returning a file URL if the audio format is webm."""
    if not is_valid_youtube_url(url):
        return JSONResponse(
            content={"success": False, "error": "Invalid YouTube URL format"},
            status_code=400
        )
    
    start_time = time.time()
    cleaned_url = urllib.parse.quote(url.strip(), safe=':/?&=')
    
    max_retries = 5
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Fetch audio info concurrently
            info = await fetch_video_info(cleaned_url)

            # Prepare the response with relevant audio details
            audio_info = {
                "success": True,
                "title": info.get('title'),
                "duration": info.get('duration'),
                "artist": info.get('artist'),
                "album": info.get('album'),
                "genre": info.get('genre'),
                "formats": [
                    {
                        'resolution': f.get('resolution', 'audio only'),
                        'quality': f.get('format_note', 'unknown'),
                        'url': f.get('url'),
                        'ext': f.get('ext'),
                        'file_url': f.get('url') if f.get('audio_ext') == 'webm' else None
                    }
                    for f in info.get('formats', [])
                    if 'format_note' in f and f.get('acodec') != 'none'  # Only include formats with audio
                ]
            }

            end_time = time.time()
            time_taken = end_time - start_time
            file_url = next((f['file_url'] for f in audio_info['formats'] if f.get('file_url')), None)
            return JSONResponse(content={"file_url": file_url})

        except Exception as error:
            last_error = error
            continue

    # If all retries failed
    end_time = time.time()
    time_taken = end_time - start_time
    return JSONResponse(
        content={"success": False, "error": str(last_error), "time_taken": time_taken},
        status_code=400
    )
