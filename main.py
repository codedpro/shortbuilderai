import os
import time
import shutil
import sys
from app.logger import get_logger
from app.scraper import extract_video_id
from app.stats import get_video_stats, is_viral, get_video_metadata, save_video_metadata
from app.downloader import download_video
from app.editor import add_feedback_template
from app.uploader import upload_video  # YouTube upload function
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

logger = get_logger("Main")

def run_process():
    logger.info("Starting video automation process")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=chrome_options)
    action = ActionChains(driver)
    base_url = "https://www.youtube.com/shorts/"
    logger.info("Opening URL: %s", base_url)
    driver.get(base_url)
    time.sleep(5)
    max_attempts = 50
    attempts = 0
    video_id = None

    while attempts < max_attempts:
        attempts += 1
        current_url = driver.current_url
        video_id = extract_video_id(current_url)
        if not video_id:
            logger.error("No video ID found. Attempt %d of %d", attempts, max_attempts)
            driver.get(base_url)
            time.sleep(5)
            continue

        # Skip if video was already processed (exists in downloads or shorts)
        if os.path.exists(os.path.join("downloads", f"{video_id}.json")) or os.path.exists(os.path.join("shorts", f"{video_id}.json")):
            logger.info("Video %s already processed. Skipping.", video_id)
            driver.get(base_url)
            time.sleep(5)
            continue

        stats = get_video_stats(video_id)
        if is_viral(stats):
            logger.info("Found viral video: %s (Stats: %s)", video_id, stats)
            break
        else:
            logger.info("Video %s is not viral: %s (Attempt %d of %d)", video_id, stats, attempts, max_attempts)
            driver.get(base_url)
            time.sleep(5)
    else:
        logger.error("No viral video found after %d attempts. Exiting.", max_attempts)
        driver.quit()
        return False

    driver.quit()

    downloaded_video_path = download_video(
        video_id,
        output_folder="downloads",
        cookies_path="cookies.txt",
        use_cookies_from_browser=True,
        visitor_data=None
    )
    if not downloaded_video_path:
        logger.error("Failed to download video. Exiting process.")
        return False

    metadata = get_video_metadata(video_id)
    if metadata:
        save_video_metadata(video_id, metadata, output_dir=os.path.dirname(downloaded_video_path))
    else:
        logger.error("Failed to fetch metadata for video %s", video_id)

    edited_video_path = os.path.join("downloads", f"edited_{os.path.basename(downloaded_video_path)}")
    if not add_feedback_template(downloaded_video_path, edited_video_path):
        logger.error("Failed to edit video. Exiting process.")
        return False

    original_metadata_file = os.path.join(os.path.dirname(downloaded_video_path), f"{video_id}.json")
    edited_metadata_file = os.path.splitext(edited_video_path)[0] + ".json"
    if os.path.exists(original_metadata_file):
        shutil.copy(original_metadata_file, edited_metadata_file)
        logger.info("Copied metadata file to %s", edited_metadata_file)
    else:
        logger.warning("Original metadata file not found; uploader will use default metadata.")

    # Upload to YouTube and Instagram based on flags
    uploaded_video = None
    uploaded_instagram = None

    # Import the new Instagram uploader function from uploader
    from app.uploader import upload_instagram

    if globals().get("UPLOAD_YOUTUBE", True):
        uploaded_video = upload_video(edited_video_path)
        if not uploaded_video:
            logger.error("Failed to upload video to YouTube. Exiting process.")
            return False

    if globals().get("UPLOAD_INSTAGRAM", True):
        uploaded_instagram = upload_instagram(edited_video_path)
        if not uploaded_instagram:
            logger.error("Failed to upload video to Instagram. Exiting process.")
            return False

    logger.info("Video uploaded successfully. Moving video and metadata to shorts folder.")
    shorts_folder = "shorts"
    os.makedirs(shorts_folder, exist_ok=True)
    edited_video_name = os.path.basename(edited_video_path)
    target_video_path = os.path.join(shorts_folder, edited_video_name)
    shutil.move(edited_video_path, target_video_path)
    metadata_file = os.path.splitext(edited_video_path)[0] + ".json"
    if os.path.exists(metadata_file):
        target_metadata_file = os.path.join(shorts_folder, os.path.basename(metadata_file))
        shutil.move(metadata_file, target_metadata_file)
    logger.info("Process completed successfully.")
    return True

def main(run_count=1):
    # Add two simple parameters: --no-youtube and --no-instagram.
    global UPLOAD_YOUTUBE, UPLOAD_INSTAGRAM
    UPLOAD_YOUTUBE = True
    UPLOAD_INSTAGRAM = True

    if "--no-youtube" in sys.argv:
        UPLOAD_YOUTUBE = False
    if "--no-instagram" in sys.argv:
        UPLOAD_INSTAGRAM = False

    for i in range(run_count):
        logger.info("=== Starting iteration %d of %d ===", i+1, run_count)
        if not run_process():
            logger.error("Process failed at iteration %d", i+1)
            break
        time.sleep(5)

if __name__ == "__main__":
    try:
        count = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    except ValueError:
        count = 1
    main(run_count=count)
