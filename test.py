import os
import json
import requests

CREDENTIALS_FILE = "instagram_credentials.json"

def load_instagram_credentials():
    """Load credentials from instagram_credentials.json."""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading {CREDENTIALS_FILE}: {e}")
            return None
    else:
        print(f"{CREDENTIALS_FILE} does not exist.")
        return None

def exchange_for_long_lived_token(short_lived_token, app_id, app_secret):
    """Exchanges a short-lived token for a long-lived token using Facebook's endpoint."""
    url = "https://graph.facebook.com/v18.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_lived_token
    }
    response = requests.get(url, params=params)
    return response

def main():
    creds = load_instagram_credentials()
    if not creds:
        print("Failed to load credentials.")
        return

    temp_token = creds.get("Temporary_Token")
    app_id = creds.get("App_ID")
    app_secret = creds.get("App_Secret")

    if not temp_token or not app_id or not app_secret:
        print("Missing required fields in credentials file.")
        return

    print("Exchanging temporary token for a long-lived token...")
    response = exchange_for_long_lived_token(temp_token, app_id, app_secret)
    print("Status Code:", response.status_code)
    try:
        data = response.json()
        print("Response:")
        print(json.dumps(data, indent=4))
    except Exception as e:
        print("Error parsing response:", e)

if __name__ == "__main__":
    main()
