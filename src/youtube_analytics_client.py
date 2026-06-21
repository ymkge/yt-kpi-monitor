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

    def get_top_videos(self, start_date_str, end_date_str, max_results=3):
        """
        指定期間内の動画データを取得し、再生数上位と高評価数上位の動画リストを返す。
        API側の制限（sortパラメータの制限など）を回避するため、
        再生数順で多めにデータを取得した後にPython側でソートとフィルタリングを行います。
        """
        # APIからは最も基本的な「再生数による降順ソート」で多めに取得する
        request = self.analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date_str,
            endDate=end_date_str,
            metrics="views,likes",
            dimensions="video",
            sort="-views",
            maxResults=30  # ランキング候補として十分な件数を取得
        )
        response = request.execute()

        rows = response.get("rows", [])
        if not rows:
            return [], []

        # 取得したデータを一旦パース
        parsed_videos = []
        for row in rows:
            video_id = row[0]
            views = int(row[1]) if row[1] is not None else 0
            likes = int(row[2]) if row[2] is not None else 0
            parsed_videos.append({
                "video_id": video_id,
                "views": views,
                "likes": likes
            })

        # 再生数ランキング（views 降順）
        views_sorted = sorted(parsed_videos, key=lambda x: x["views"], reverse=True)[:max_results]
        
        # 高評価数ランキング（likes 降順）
        likes_sorted = sorted(parsed_videos, key=lambda x: x["likes"], reverse=True)[:max_results]

        # タイトルを一括取得するための動画IDを収集
        unique_video_ids = list(set(
            [v["video_id"] for v in views_sorted] + [v["video_id"] for v in likes_sorted]
        ))
        titles = self._get_video_titles(unique_video_ids)

        # 各リストにタイトルを適用
        for v in views_sorted:
            v["title"] = titles.get(v["video_id"], "不明な動画")
        for v in likes_sorted:
            v["title"] = titles.get(v["video_id"], "不明な動画")

        return views_sorted, likes_sorted
