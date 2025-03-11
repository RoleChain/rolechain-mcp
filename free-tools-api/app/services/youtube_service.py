import os
import shutil
from pydub import AudioSegment
import yt_dlp as youtube_dl
import openai      # For transcript generation
import urllib.request
import urllib.parse
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from pathlib import Path
import random


openai.api_key = os.getenv('OPENAI_API_KEY')

async def download_audio_from_youtube(url: str) -> str:
    """Download audio from YouTube and return the path to the audio file."""
    try:
        # Define options for yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,
            'outtmpl': 'temp_audio.%(ext)s',  # Save to a temporary file
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            # Extract info and download the audio
            info = ydl.extract_info(url, download=True)
            title = info['title']
            mp3_filename = f"{title}.mp3"
            mp3_file_path = os.path.join(os.getcwd(), mp3_filename)

            # Move the temporary file to the final path
            shutil.move('temp_audio.mp3', mp3_file_path)

            # Ensure the file was created
            if not os.path.exists(mp3_file_path):
                raise Exception(f"File {mp3_filename} was not created.")
                
            return mp3_file_path  # Return the path of the converted MP3 file
    except Exception as e:
        print('Failed to download audio: ', e)
        raise Exception("Failed to download audio.") from e

def transcribe_audio(audio_file_path: str) -> str:
    """Transcribe the audio file using OpenAI's API, handling large files by splitting them into chunks."""
    try:
        # Load the audio file
        audio = AudioSegment.from_mp3(audio_file_path)
        
        # Split the audio into chunks (e.g., 3 minutes per chunk)
        chunk_length_ms = 3 * 60 * 1000  # 3 minutes in milliseconds
        chunks = [audio[i:i + chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]

        transcripts = []
        for idx, chunk in enumerate(chunks):
            # Save the chunk temporarily
            chunk_file = f"chunk_{idx}.mp3"
            chunk.export(chunk_file, format="mp3")
            
            # Open the chunk file
            with open(chunk_file, 'rb') as audio_chunk:
                # Transcribe the chunk using OpenAI API
                response = openai.Audio.transcribe(
                    file=audio_chunk,
                    model='whisper-1'
                )
                transcripts.append(response['text'])

            # Clean up the temporary chunk file
            os.remove(chunk_file)

        # Combine all transcripts into a single string
        final_transcript = " ".join(transcripts)
        return final_transcript

    except Exception as e:
        print('Failed to transcribe:', e)
        raise Exception("Failed to transcribe audio.") from e

    finally:
        # Clean up the original audio file
        if os.path.exists(audio_file_path):
            os.remove(audio_file_path)


def get_video_id(url):
    try:
        query = urllib.parse.urlparse(url).query
        params = urllib.parse.parse_qs(query)
        return params["v"][0]
    except Exception as e:
        print(e)
        # logger.error(f"Failed to parse video ID", {"error": str(e), "url": url})

async def get_proxy_config():
    try:
        file_path = Path(__file__).parent.parent / "proxies.txt"
        with open(file_path, "r") as f:
            proxy_lines = [line.strip() for line in f if line.strip()]
        
        if not proxy_lines:
            raise Exception("No proxies available in the file")
            
        selected_proxy = random.choice(proxy_lines)
        address, port, username, password = selected_proxy.split(":")
        return f"http://{username}:{password}@{address}:{port}"
    except Exception as error:
        print(f"Failed to get proxy configuration: {str(error)}")
        raise error

async def get_transcript(youtube_url: str) -> list:
    max_proxy_retries = 5
    proxy_attempt = 0
    last_error = None

    while proxy_attempt < max_proxy_retries:
        try:
            # Get proxy configuration
            proxy = await get_proxy_config()
            video_id = get_video_id(url=youtube_url)
            
            # Configure proxy using the proxies parameter
            transcript_list = YouTubeTranscriptApi.list_transcripts(
                video_id,
                proxies={'http': proxy, 'https': proxy}
            )
            
            # First check if transcript is available
            if not transcript_list.find_transcript(['en']):
                raise Exception("Transcript is disabled or not available for this video")
            
            trans = YouTubeTranscriptApi.get_transcripts(
                video_ids=[video_id], 
                languages=['en'], 
                preserve_formatting=True,
                proxies={'http': proxy, 'https': proxy}
            )
            return trans[0][video_id]

        except (TranscriptsDisabled, NoTranscriptFound) as e:
            # Don't retry for these specific errors
            print(f"Transcript is disabled or not found error {str(e)}")
            error_message = "Transcript is disabled or not available for this video"
            last_error = error_message
            proxy_attempt += 1
        except Exception as error:
            print(error)
            print(f"Failed to get transcript on attempt {proxy_attempt + 1}: {str(error)}")
            last_error = "Failed to get transcript"
            proxy_attempt += 1
            
    print('All proxy attempts failed.')
    logger.error(f"Failed to get transcript after all retries", {"error": str(last_error), "url": youtube_url})
    raise last_error