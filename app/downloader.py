from yt_dlp import YoutubeDL
import os
from app.logger import get_logger
import imageio_ffmpeg

logger = get_logger(__name__)

def progress_hook(d):
    if d.get("status") == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes", 0)
        if total:
            percent = downloaded / total * 100
            logger.info("Downloading: %.2f%% complete", percent)
        else:
            logger.info("Downloading: %d bytes", downloaded)
    elif d.get("status") == "finished":
        logger.info("Download finished, now post-processing...")

def download_video(video_id, 
                   output_folder="downloads", 
                   cookies_path="cookies.txt", 
                   use_cookies_from_browser=True,
                   visitor_data=None):
    url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info("Downloading video from URL: %s", url)
    
    os.makedirs(output_folder, exist_ok=True)
    
    # Use a format that downloads the best video and best audio streams separately,
    # then merges them into an MP4 container (requires ffmpeg).
    ydl_opts = {
        'outtmpl': os.path.join(output_folder, '%(id)s.%(ext)s'),
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',  # Ensures the final file is in MP4 format
        'noplaylist': True,
        'progress_hooks': [progress_hook],
        'quiet': False,
        'no_warnings': False,
    }
    
    # Set ffmpeg_location using imageio-ffmpeg
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    ydl_opts['ffmpeg_location'] = ffmpeg_path
    logger.info("Using ffmpeg binary from: %s", ffmpeg_path)
    
    # Option A: Use cookies from file if found
    if cookies_path and os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 0:
        ydl_opts['cookiefile'] = cookies_path
        logger.info("Using cookies from file: %s", cookies_path)
    
    # Option B: If user wants, try extracting from the browser (Chrome)
    elif use_cookies_from_browser:
        logger.info("Attempting to use cookies from Chrome browser (yt_dlp feature).")
        ydl_opts['cookiesfrombrowser'] = ('chrome',)
    
    # Option C: If visitor_data is specified, use that
    if visitor_data:
        # Use the “Innertube” approach with visitor data
        ydl_opts.setdefault('extractor_args', {})
        ydl_opts['extractor_args']['youtube'] = {
            'player_skip': 'webpage,configs',
            'visitor_data': visitor_data,
        }
        ydl_opts['extractor_args']['youtubetab'] = {
            'skip': 'webpage',
        }
        logger.info("Using provided visitor data for authentication.")
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info_dict)
            logger.info("Video downloaded to: %s", video_path)
            return video_path
    except Exception as e:
        logger.exception("Error downloading video: %s", e)
        return None
