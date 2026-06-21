import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()

def main():
    client_id = os.getenv("YOUTUBE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_OAUTH_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("Error: OAuth credentials are not fully set in .env")
        return

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )
    
    try:
        credentials.refresh(Request())
    except Exception as e:
        print(f"Error refreshing token: {e}")
        return

    # 1. Data APIで認証されたチャンネル情報を取得
    youtube = build("youtube", "v3", credentials=credentials)
    try:
        ch_request = youtube.channels().list(part="snippet,statistics", mine=True)
        ch_response = ch_request.execute()

        print("=== 認証されたチャンネル情報 ===")
        if not ch_response.get("items"):
            print("チャンネルが見つかりません（mine=True）")
        else:
            for item in ch_response["items"]:
                print(f"チャンネルID: {item['id']}")
                print(f"タイトル: {item['snippet']['title']}")
                print(f"総再生数: {item['statistics'].get('viewCount')}")
                print(f"登録者数: {item['statistics'].get('subscriberCount')}")
        print("================================\n")
    except Exception as e:
        print(f"Error fetching channel info: {e}")

    # 2. Analytics API で直近の生データを取得して出力
    from datetime import datetime, timedelta
    today = datetime.now()
    start_date = (today - timedelta(days=28)).strftime("%Y-%m-%d")
    end_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    analytics = build("youtubeAnalytics", "v2", credentials=credentials)
    try:
        request = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,likes",
            dimensions="video",
            sort="-views",
            maxResults=5
        )
        response = request.execute()
        
        print("=== Analytics API 生レスポンス ===")
        print("ColumnHeaders:", response.get("columnHeaders"))
        print("Rows:", response.get("rows"))
        print("==================================")
    except Exception as e:
        print(f"Error fetching analytics: {e}")

if __name__ == "__main__":
    main()
