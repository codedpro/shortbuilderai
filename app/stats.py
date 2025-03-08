import os
import json
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from app.logger import get_logger

logger = get_logger(__name__)

# IMPORTANT: Ensure token.json is generated via the OAuth2 flow using your credentials.json.
SCOPES_READ = ["https://www.googleapis.com/auth/youtube.readonly"]

def get_youtube_service():
    """
    Authenticate and return the YouTube API service for read-only operations.
    Expects a valid token.json (created via an OAuth2 flow) to exist.
    """
    creds = None
    token_file = "token.json"
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES_READ)
        except Exception as e:
            logger.error("Failed to load credentials from token.json: %s", e)
            return None
    if not creds or not creds.valid:
        logger.error("No valid credentials found for YouTube API. Please run generate_token.py locally!")
        return None
    return build("youtube", "v3", credentials=creds)

def get_video_stats(video_id):
    """
    Fetches real video statistics from YouTube API for the given video ID.
    
    Args:
        video_id (str): The YouTube video ID.
        
    Returns:
        dict: A dictionary containing viewCount, likeCount, and commentCount as integers,
              or None if the video was not found.
    """
    youtube = get_youtube_service()
    if not youtube:
        return None

    request = youtube.videos().list(
        part="statistics",
        id=video_id
    )
    response = request.execute()
    items = response.get("items", [])
    if not items:
        logger.error("No video found for ID: %s", video_id)
        return None
    statistics = items[0].get("statistics", {})
    stats = {
        "views": int(statistics.get("viewCount", 0)),
        "likes": int(statistics.get("likeCount", 0)),
        "comments": int(statistics.get("commentCount", 0))
    }
    logger.info("Fetched stats for video %s: %s", video_id, stats)
    return stats

def is_viral(stats, min_views=1000000, min_likes=150000, min_comments=5000):
    """
    Determines whether a video is viral based on given thresholds.
    
    Args:
        stats (dict): Dictionary containing video statistics.
        min_views (int): Minimum view count to be considered viral.
        min_likes (int): Minimum like count to be considered viral.
        min_comments (int): Minimum comment count to be considered viral.
    
    Returns:
        bool: True if the video meets or exceeds all thresholds; otherwise, False.
    """
    if not stats:
        return False
    viral = (stats.get("views", 0) >= min_views and 
             stats.get("likes", 0) >= min_likes and 
             stats.get("comments", 0) >= min_comments)
    if viral:
        logger.info("Video is viral: %s", stats)
    else:
        logger.info("Video is not viral: %s", stats)
    return viral

def get_video_metadata(video_id):
    """
    Fetches real video metadata (title, description, tags) from YouTube API for the given video ID.
    
    Args:
        video_id (str): The YouTube video ID.
        
    Returns:
        dict: A dictionary with keys "title", "description", and "tags", or None if the video was not found.
    """
    youtube = get_youtube_service()
    if not youtube:
        return None

    request = youtube.videos().list(
        part="snippet",
        id=video_id
    )
    response = request.execute()
    items = response.get("items", [])
    if not items:
        logger.error("No video found for ID: %s", video_id)
        return None
    snippet = items[0].get("snippet", {})
    metadata = {
        "title": snippet.get("title", f"Viral Short: {video_id}"),
        "description": snippet.get("description", f"This is a viral YouTube Short with ID {video_id}. Enjoy the video!"),
        "tags": snippet.get("tags", ["shorts", "viral", "trending"])
    }
    logger.info("Fetched metadata for video %s: %s", video_id, metadata)
    return metadata

def save_video_metadata(video_id, metadata, output_dir="downloads"):
    """
    Saves video metadata as a JSON file with the same base name as the video.
    
    Args:
        video_id (str): The ID of the video.
        metadata (dict): Metadata containing title, description, and tags.
        output_dir (str): Directory where the JSON file will be saved.
        
    Returns:
        str: The path to the saved metadata file.
    """
    os.makedirs(output_dir, exist_ok=True)
    metadata_file = os.path.join(output_dir, f"{video_id}.json")
    try:
        with open(metadata_file, "w") as f:
            json.dump(metadata, f)
        logger.info("Saved metadata to %s", metadata_file)
    except Exception as e:
        logger.exception("Error saving metadata: %s", e)
    return metadata_file
