import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

SECRETS_FILE = Path("client_secrets.json")
TOKEN_FILE = Path("youtube_token.json")

class YouTubeUploader:
    def __init__(self):
        self.service = None

    def get_credentials(self) -> Optional[Credentials]:
        creds = None
        if TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            except Exception as e:
                print(f"[YouTubeUploader] Token error: {e}")
                return None

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception as e:
                print(f"[YouTubeUploader] Refresh error: {e}")
                return None

        return creds if creds and creds.valid else None

    def get_channel_info(self) -> Dict[str, Any]:
        """
        Check connection and fetch connected channel details.
        """
        creds = self.get_credentials()
        if not creds:
            return {"connected": False, "channel": None}

        try:
            youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
            res = youtube.channels().list(part="snippet,statistics", mine=True).execute()
            items = res.get("items", [])
            if items:
                ch = items[0]
                snippet = ch.get("snippet", {})
                stats = ch.get("statistics", {})
                return {
                    "connected": True,
                    "channel": {
                        "id": ch.get("id"),
                        "title": snippet.get("title"),
                        "customUrl": snippet.get("customUrl"),
                        "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url"),
                        "subscribers": stats.get("subscriberCount", "0"),
                        "videoCount": stats.get("videoCount", "0")
                    }
                }
            return {"connected": False, "channel": None}
        except Exception as e:
            print(f"[YouTubeUploader] Fetch channel error: {e}")
            return {"connected": False, "error": str(e)}

    def create_oauth_flow(self, redirect_uri: str = "http://localhost:8000/api/youtube/callback") -> Optional[google_auth_oauthlib.flow.Flow]:
        if not SECRETS_FILE.exists():
            return None
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            str(SECRETS_FILE),
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        return flow

    def save_client_secrets(self, client_id: str, client_secret: str):
        """Save manual Client ID & Secret from Google Cloud Console"""
        data = {
            "web": {
                "client_id": client_id.strip(),
                "client_secret": client_secret.strip(),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8000/api/youtube/callback"]
            }
        }
        with open(SECRETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Optional[List[str]] = None,
        category_id: str = "20",  # 20 = Gaming
        privacy_status: str = "public"
    ) -> Dict[str, Any]:
        """
        Uploads an MP4 file directly to YouTube channel.
        """
        creds = self.get_credentials()
        if not creds:
            raise RuntimeError("YouTube account is not connected. Authorize channel first.")

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found at: {video_path}")

        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags or ["Gaming", "GTA", "Shorts", "Highlights"],
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 4  # 4MB chunks
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"[YouTube Upload] Uploading {int(status.progress() * 100)}%...", flush=True)

        video_id = response.get("id")
        video_url = f"https://youtu.be/{video_id}"
        print(f"[YouTube Upload] Successfully published! URL: {video_url}", flush=True)

        return {
            "success": True,
            "video_id": video_id,
            "video_url": video_url,
            "title": title,
            "status": privacy_status
        }
