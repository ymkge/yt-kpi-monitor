import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()

class YouTubeAnalyticsClient:
    def __init__(self, client_id=None, client_secret=None, refresh_token=None):
        self.client_id = client_id or os.getenv("YOUTUBE_OAUTH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET")
        self.refresh_token = refresh_token or os.getenv("YOUTUBE_OAUTH_REFRESH_TOKEN")

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError(
                "YOUTUBE_OAUTH_CLIENT_ID, YOUTUBE_OAUTH_CLIENT_SECRET, and "
                "YOUTUBE_OAUTH_REFRESH_TOKEN must be set."
            )

        self.credentials = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

        # アクセストークンの初回更新
        self.credentials.refresh(Request())

        self.analytics = build("youtubeAnalytics", "v2", credentials=self.credentials)
        self.youtube = build("youtube", "v3", credentials=self.credentials)

    def _get_video_titles(self, video_ids):
        """
        動画IDリストから動画タイトルのマッピングを取得する。
        """
        if not video_ids:
            return {}

        titles = {}
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i+50]
            request = self.youtube.videos().list(
                part="snippet",
                id=",".join(chunk)
            )
            response = request.execute()
            for item in response.get("items", []):
                titles[item["id"]] = item["snippet"]["title"]
        return titles

    def get_top_videos_by_views(self, start_date_str, end_date_str, max_results=3):
        """
        指定期間内で再生数（views）が多い上位動画を取得する。
        """
        request = self.analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date_str,
            endDate=end_date_str,
            metrics="views,likes",
            dimensions="video",
            sort="-views",
            maxResults=max_results
        )
        response = request.execute()

        rows = response.get("rows", [])
        if not rows:
            return []

        video_ids = [row[0] for row in rows]
        titles = self._get_video_titles(video_ids)

        result = []
        for row in rows:
            video_id = row[0]
            views = int(row[1])
            likes = int(row[2]) if row[2] is not None else 0
            result.append({
                "video_id": video_id,
                "title": titles.get(video_id, "不明な動画"),
                "views": views,
                "likes": likes
            })
        return result

    def get_top_videos_by_likes(self, start_date_str, end_date_str, max_results=3):
        """
        指定期間内で高評価数（likes）が多い上位動画を取得する。
        """
        request = self.analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date_str,
            endDate=end_date_str,
            metrics="views,likes",
            dimensions="video",
            sort="-likes",
            maxResults=max_results
        )
        response = request.execute()

        rows = response.get("rows", [])
        if not rows:
            return []

        video_ids = [row[0] for row in rows]
        titles = self._get_video_titles(video_ids)

        result = []
        for row in rows:
            video_id = row[0]
            views = int(row[1])
            likes = int(row[2]) if row[2] is not None else 0
            result.append({
                "video_id": video_id,
                "title": titles.get(video_id, "不明な動画"),
                "views": views,
                "likes": likes
            })
        return result
