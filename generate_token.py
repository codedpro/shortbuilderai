from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

def main():
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    # Request offline access and force consent so that a refresh_token is returned
    creds = flow.run_local_server(port=8080, access_type="offline", prompt="consent")
    with open("token.json", "w") as token_file:
        token_file.write(creds.to_json())
    print("Authentication complete. Token saved to token.json.")

if __name__ == "__main__":
    main()
