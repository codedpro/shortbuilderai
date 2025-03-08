# app/scraper.py
import re
from app.logger import get_logger

logger = get_logger(__name__)

def extract_video_id(url):
    """
    Extract the video ID from a YouTube Shorts URL.
    Example URL: https://www.youtube.com/shorts/RVh0pQyM-gs
    """
    pattern = r"shorts/([^/?&]+)"
    match = re.search(pattern, url)
    if match:
        video_id = match.group(1)
        logger.info("Extracted video ID: %s", video_id)
        return video_id
    else:
        logger.error("Video ID not found in URL: %s", url)
        return None
