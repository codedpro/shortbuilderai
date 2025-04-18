import os
import json
from datetime import datetime, timedelta
from dateutil import parser

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime, timedelta, timezone
from dateutil import parser
import requests  # Needed for Instagram API calls
import cloudinary
import cloudinary.uploader
import cloudinary.api
from urllib.parse import urlparse

from app.logger import get_logger

logger = get_logger(__name__)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

#######################################################
# INTERNAL Scheduling Logic for 2x Daily (10:00 & 18:00)
#######################################################
TIME_SLOTS_UTC = [10, 18]  # 10:00 and 18:00 UTC daily
SCHEDULE_FILE = "youtube_schedule.json"

def _load_schedule_data():
    """
    Loads a JSON file to track the last scheduled time.
    Returns a dict: { "last_scheduled": "2025-04-03T10:00:00Z" } or None if missing.
    """
    if not os.path.exists(SCHEDULE_FILE):
        return None
    try:
        with open(SCHEDULE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to read %s: %s", SCHEDULE_FILE, e)
        return None

def _save_schedule_data(data):
    """
    Saves scheduling info to youtube_schedule.json.
    data is typically { "last_scheduled": ... }
    """
    try:
        with open(SCHEDULE_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(e)

TIME_SLOTS_UTC = [10, 18]  # 10:00 and 18:00 UTC daily
SCHEDULE_FILE = "youtube_schedule.json"

def _get_next_time_slot():
    """
    Computes the next available time slot (10:00 UTC or 18:00 UTC),
    following the last_scheduled slot if it exists,
    or from 'now' if there's no last_scheduled.

    Returns an RFC 3339 string, e.g. "2025-04-03T10:00:00Z".
    """
    schedule_data = _load_schedule_data()
    # Use an *aware* datetime in UTC:
    now_utc = datetime.now(timezone.utc)

    if schedule_data and "last_scheduled" in schedule_data:
        last_str = schedule_data["last_scheduled"]
        try:
            last_dt = parser.isoparse(last_str)
        except Exception:
            logger.warning("Invalid last_scheduled format in %s, ignoring.", SCHEDULE_FILE)
            last_dt = None
    else:
        last_dt = None

    # Start from whichever is later: now or last scheduled time
    if last_dt and last_dt > now_utc:
        candidate = last_dt
    else:
        candidate = now_utc

    # We want the NEXT slot after 'candidate'
    while True:
        candidate_date = candidate.date()
        for hour in TIME_SLOTS_UTC:
            # Also construct this slot time in UTC:
            slot_dt = datetime(candidate_date.year, candidate_date.month, candidate_date.day,
                               hour, 0, 0, tzinfo=timezone.utc)
            if slot_dt > candidate:
                return slot_dt.isoformat().replace("+00:00", "Z")
        # If we didn't find a slot for that day, jump to next day at midnight UTC
        candidate = datetime(candidate_date.year, candidate_date.month, candidate_date.day,
                             tzinfo=timezone.utc) + timedelta(days=1)


#################################################
# YOUTUBE AUTH & UPLOAD (with hidden scheduling)
#################################################

def authenticate_youtube():
    creds = None
    token_file = "token.json"
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception as e:
            logger.error("Failed to load credentials from token.json: %s", e)
            return None
    if not creds or not creds.valid:
        logger.error("No valid credentials found. Please run generate_token.py locally!")
        return None
    return build("youtube", "v3", credentials=creds)

def upload_video(video_path, title="My YouTube Short", description="Auto-uploaded Shorts", tags=["shorts"], privacy="public"):
    """
    Uploads a video to YouTube. The call signature remains the same
    but we automatically schedule it 2x per day (10:00 UTC, 18:00 UTC).
    """
    try:
        # --- Step 1: Load JSON metadata if present ---
        metadata_path = os.path.splitext(video_path)[0] + ".json"
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as meta_file:
                metadata = json.load(meta_file)
            title = metadata.get("title", title)
            description = metadata.get("description", description)
            tags = metadata.get("tags", tags)
            logger.info("Metadata loaded from %s", metadata_path)
        else:
            logger.info("No metadata file found; using default title, description, and tags.")

        # --- Step 2: Authenticate with YouTube ---
        logger.info("Authenticating with YouTube API...")
        youtube = authenticate_youtube()
        if not youtube:
            logger.error("Authentication failed. Cannot upload video.")
            return None

        # --- Step 3: Compute next time slot & override status for scheduling ---
        publish_at = _get_next_time_slot()  # e.g. "2025-04-03T10:00:00Z"
        logger.info("Scheduling video for next slot: %s", publish_at)

        # Force privacy to 'private' for scheduling to work
        # and set the publishAt field
        request_body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at
            },
        }

        # --- Step 4: Upload (insert) via API ---
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        logger.info("Uploading video to YouTube: %s", video_path)
        request = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media
        )
        response = request.execute()
        video_id = response.get("id")
        if video_id:
            logger.info("YouTube video scheduled! ID=%s | Goes public at: %s", video_id, publish_at)

            # Save the chosen publish time as "last_scheduled" so the next call picks the following slot
            schedule_data = {"last_scheduled": publish_at}
            _save_schedule_data(schedule_data)

            return video_id
        else:
            logger.error("YouTube upload failed. No video ID returned.")
            return None
    except Exception as e:
        logger.exception("Error uploading video to YouTube: %s", e)
        return None

#####################################
# Cloudinary Upload Function
#####################################

def upload_to_cloudinary(video_path):
    """
    Uploads the local video file to Cloudinary and returns a publicly accessible URL.
    Cloudinary credentials are read from cloudinary_credentials.json.
    """
    credentials_file = "cloudinary_credentials.json"
    if not os.path.exists(credentials_file):
        logger.error("Cloudinary credentials file does not exist.")
        return None
    try:
        with open(credentials_file, "r") as f:
            data = json.load(f)
        cloudinary_url_str = data.get("CLOUDINARY_URL")
        if not cloudinary_url_str:
            logger.error("CLOUDINARY_URL not found in cloudinary_credentials.json")
            return None
        # Remove the "CLOUDINARY_URL=" prefix if present
        if cloudinary_url_str.startswith("CLOUDINARY_URL="):
            cloudinary_url_str = cloudinary_url_str.split("=", 1)[1]
        # Parse the Cloudinary URL to extract cloud_name, api_key, and api_secret
        parsed = urlparse(cloudinary_url_str)
        cloud_name = parsed.hostname
        api_key = parsed.username
        api_secret = parsed.password
        if not (cloud_name and api_key and api_secret):
            logger.error("Failed to parse Cloudinary credentials from URL: %s", cloudinary_url_str)
            return None
        # Configure Cloudinary with separate parameters
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret
        )
        logger.info("Uploading video to Cloudinary: %s", video_path)
        result = cloudinary.uploader.upload_large(video_path, resource_type="video")
        video_url = result.get("secure_url")
        if video_url:
            logger.info("Uploaded to Cloudinary, video URL: %s", video_url)
            return video_url
        else:
            logger.error("Cloudinary upload did not return a secure URL.")
            return None
    except Exception as e:
        logger.exception("Error uploading to Cloudinary: %s", e)
        return None

#####################################
# Instagram Credential Management
#####################################

def load_instagram_credentials():
    """Load credentials from instagram_credentials.json."""
    credentials_file = "instagram_credentials.json"
    if os.path.exists(credentials_file):
        try:
            with open(credentials_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Error reading Instagram credentials file: %s", e)
            return None
    else:
        logger.error("Instagram credentials file does not exist.")
        return None

def save_instagram_credentials(data):
    """Save credentials to instagram_credentials.json."""
    credentials_file = "instagram_credentials.json"
    try:
        with open(credentials_file, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error("Error saving Instagram credentials file: %s", e)

def get_instagram_credentials_data():
    """
    Returns a tuple:
      (access_token, business_id, app_id, app_secret, temporary_token)
    If a long-lived token exists in the file (Instagram_AccessToken) use it;
    otherwise fallback to Temporary_Token.
    """
    data = load_instagram_credentials()
    if not data:
        return None, None, None, None, None
    token = data.get("Instagram_AccessToken")
    temp_token = data.get("Temporary_Token")
    business_id = data.get("Instagram_Business_ID")
    app_id = data.get("App_ID")
    app_secret = data.get("App_Secret")
    if not token:
        token = temp_token  # Use temporary token if long-lived one is not present
    return token, business_id, app_id, app_secret, temp_token

def exchange_for_long_lived_token(short_lived_token, app_id, app_secret):
    """
    Exchanges a short-lived token for a long-lived token using Facebook's endpoint.
    Returns the new token if successful.
    """
    url = "https://graph.facebook.com/v18.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_lived_token
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        new_token = data.get("access_token")
        if new_token:
            logger.info("Successfully exchanged token for long-lived token.")
            return new_token
        else:
            logger.error("Exchange response did not contain a new access token: %s", data)
            return None
    else:
        logger.error("Failed to exchange token: %s", response.text)
        return None

#####################################
# Instagram Upload Function
#####################################

def handle_instagram_error(response):
    """
    Checks the Instagram API response for token-related errors.
    If the error indicates the token is expired or invalid, logs a clear message.
    """
    try:
        error_info = response.json().get("error", {})
        error_message = error_info.get("message", "").lower()
        if "expired" in error_message or "invalid" in error_message:
            logger.error("Instagram access token appears to be expired or invalid: %s", error_message)
    except Exception:
        pass

def upload_instagram(video_path, caption="My Instagram Post"):
    """
    Upload a video to Instagram using the Instagram Graph API.
    NOTE: Instagram requires the video to be hosted at a public URL.
    This function first uploads the local video file to Cloudinary to obtain a public URL.
    It then uses that URL along with credentials stored in instagram_credentials.json to
    create and publish an Instagram media container.
    """
    try:
        metadata_path = os.path.splitext(video_path)[0] + ".json"
        metadata = {}
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as meta_file:
                metadata = json.load(meta_file)
            caption = metadata.get("caption", caption)
            logger.info("Metadata loaded from %s", metadata_path)
        else:
            logger.info("No metadata file found; using default caption for Instagram.")

        # Instead of using a 'video_url' from metadata, upload the video to Cloudinary
        cloudinary_url = upload_to_cloudinary(video_path)
        if not cloudinary_url:
            logger.error("Failed to upload video to Cloudinary for Instagram upload.")
            return None
        # Use the Cloudinary URL as the public video URL for Instagram
        public_video_url = cloudinary_url

        # Load Instagram credentials from JSON file
        token, business_id, app_id, app_secret, temp_token = get_instagram_credentials_data()
        if not token or not business_id or not app_id or not app_secret or not temp_token:
            logger.error("Missing necessary Instagram credentials in instagram_credentials.json.")
            return None

        # Helper function: create media container with a given token
        def create_media_container(token_to_use):
            create_url = f"https://graph.facebook.com/v18.0/{business_id}/media"
            payload = {
                "video_url": public_video_url,
                "caption": caption,
                "access_token": token_to_use
            }
            logger.info("Creating Instagram media container...")
            return requests.post(create_url, data=payload)

        # First attempt using the current token
        r = create_media_container(token)
        if r.status_code != 200:
            error_info = r.json().get("error", {})
            error_message = error_info.get("message", "").lower()
            if "expired" in error_message or "invalid" in error_message:
                logger.info("Current token appears expired or invalid. Attempting to exchange temporary token for a long-lived token.")
                new_token = exchange_for_long_lived_token(temp_token, app_id, app_secret)
                if new_token:
                    # Update the credentials file with the new long-lived token
                    credentials = load_instagram_credentials()
                    credentials["Instagram_AccessToken"] = new_token
                    save_instagram_credentials(credentials)
                    token = new_token
                    # Retry creating media container
                    r = create_media_container(token)
                else:
                    logger.error("Failed to exchange temporary token for a long-lived token.")
                    return None
            if r.status_code != 200:
                handle_instagram_error(r)
                logger.error("Error creating Instagram media container after token refresh: %s", r.text)
                return None

        creation_response = r.json()
        creation_id = creation_response.get("id")
        if not creation_id:
            logger.error("No creation ID returned from Instagram: %s", creation_response)
            return None

        # Step 2: Publish the media container
        publish_url = f"https://graph.facebook.com/v18.0/{business_id}/media_publish"
        publish_payload = {
            "creation_id": creation_id,
            "access_token": token
        }
        logger.info("Publishing Instagram media...")
        r_publish = requests.post(publish_url, data=publish_payload)
        if r_publish.status_code != 200:
            handle_instagram_error(r_publish)
            logger.error("Error publishing Instagram media: %s", r_publish.text)
            return None
        publish_response = r_publish.json()
        instagram_post_id = publish_response.get("id")
        if instagram_post_id:
            logger.info("Instagram video uploaded successfully! Post ID: %s", instagram_post_id)
            return instagram_post_id
        else:
            logger.error("Instagram upload failed, no post ID returned.")
            return None
    except Exception as e:
        logger.exception("Error uploading to Instagram: %s", e)
        return None
