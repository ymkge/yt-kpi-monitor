import os
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

class YouTubeClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        if not self.api_key:
            raise ValueError("YOUTUBE_API_KEY is not set.")
        self.youtube = build("youtube", "v3", developerKey=self.api_key)

    def get_recent_videos(self, channel_id, max_days=14):
        """
        指定したチャンネルで、直近 max_days 日以内に公開された動画のリストを取得する。
        リアルタイムの視聴回数といいね数も合わせて取得する。
        """
        # 1. チャンネルのアップロード動画リストIDを取得
        request = self.youtube.channels().list(
            part="contentDetails",
            id=channel_id
        )
        response = request.execute()
        if not response.get("items"):
            return []
        
        uploads_playlist_id = response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        # 2. 直近のプレイリスト項目を取得
        playlist_request = self.youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50
        )
        playlist_response = playlist_request.execute()
        
        raw_videos = []
        video_ids = []
        now_utc = datetime.now(timezone.utc)
        
        for item in playlist_response.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("contentDetails", {}).get("videoId")
            published_at_str = snippet.get("publishedAt")
            
            if not video_id or not published_at_str:
                continue
                
            # ISO 8601 形式のUTC日時をパース
            published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
            
            if now_utc - published_at <= timedelta(days=max_days):
                raw_videos.append({
                    "video_id": video_id,
                    "title": snippet.get("title", "不明な動画"),
                    "published_at": published_at_str
                })
                video_ids.append(video_id)
                
        if not raw_videos:
            return []

        # 3. videos().list を使ってリアルタイムの再生数といいね数を一括取得
        realtime_stats = {}
        for i in range(0, len(video_ids), 50):
            chunk_ids = video_ids[i:i+50]
            video_request = self.youtube.videos().list(
                part="statistics",
                id=",".join(chunk_ids)
            )
            video_response = video_request.execute()
            for item in video_response.get("items", []):
                v_id = item["id"]
                stats = item.get("statistics", {})
                realtime_stats[v_id] = {
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0))
                }

        # 4. データをマージして返却
        recent_videos = []
        for v in raw_videos:
            stats = realtime_stats.get(v["video_id"], {"views": 0, "likes": 0})
            recent_videos.append({
                "video_id": v["video_id"],
                "title": v["title"],
                "published_at": v["published_at"],
                "realtime_views": stats["views"],
                "realtime_likes": stats["likes"]
            })
            
        return recent_videos

    def get_channel_stats(self, channel_id):
        """
        指定したチャンネルの基本統計情報を取得する。
        """
        request = self.youtube.channels().list(
            part="snippet,statistics",
            id=channel_id
        )
        response = request.execute()

        if not response.get("items"):
            return None

        item = response["items"][0]
        stats = item["statistics"]
        snippet = item["snippet"]

        return {
            "channel_id": channel_id,
            "channel_title": snippet["title"],
            "subscriber_count": int(stats.get("subscriberCount", 0)),
            "view_count": int(stats.get("viewCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
        }

    def get_total_likes(self, channel_id):
        """
        全動画のいいね数の合計を取得する（Data API v3のクォータを消費しやすいため注意）。
        Phase 3でAnalytics APIを使用するまでの暫定実装。
        """
        # チャンネルのアップロード動画リストIDを取得
        request = self.youtube.channels().list(
            part="contentDetails",
            id=channel_id
        )
        response = request.execute()
        if not response.get("items"):
            return 0
        
        uploads_playlist_id = response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        total_likes = 0
        next_page_token = None
        
        # 全動画を回すとクォータが厳しいため、直近50件程度にするか検討が必要だが、
        # ここでは一旦全件取得のロジック（簡易版）を記述
        while True:
            playlist_request = self.youtube.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            playlist_response = playlist_request.execute()
            
            video_ids = [item["contentDetails"]["videoId"] for item in playlist_response.get("items", [])]
            if not video_ids:
                break
                
            video_request = self.youtube.videos().list(
                part="statistics",
                id=",".join(video_ids)
            )
            video_response = video_request.execute()
            
            for video in video_response.get("items", []):
                total_likes += int(video["statistics"].get("likeCount", 0))
            
            next_page_token = playlist_response.get("nextPageToken")
            if not next_page_token:
                break
                
        return total_likes
