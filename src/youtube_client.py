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
        self.youtube = build("youtube", "v3", developerKey=self.api_key, static_discovery=False)

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

    def get_all_videos_stats(self, channel_id, max_results=1000):
        """
        チャンネル内の全動画（または最新max_results件）の簡易スタッツ（ID, タイトル, 公開日, 再生数, いいね数）を取得する。
        """
        request = self.youtube.channels().list(
            part="contentDetails",
            id=channel_id
        )
        response = request.execute()
        if not response.get("items"):
            return []
        
        uploads_playlist_id = response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        videos_stats = []
        next_page_token = None
        
        while len(videos_stats) < max_results:
            batch_size = min(50, max_results - len(videos_stats))
            playlist_request = self.youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=batch_size,
                pageToken=next_page_token
            )
            playlist_response = playlist_request.execute()
            
            items = playlist_response.get("items", [])
            if not items:
                break
                
            video_data = []
            for item in items:
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})
                video_id = content_details.get("videoId")
                title = snippet.get("title", "不明な動画")
                published_at = snippet.get("publishedAt")
                if video_id:
                    video_data.append({
                        "video_id": video_id,
                        "title": title,
                        "published_at": published_at
                    })
            
            if not video_data:
                break
                
            video_ids = [v["video_id"] for v in video_data]
            video_request = self.youtube.videos().list(
                part="statistics",
                id=",".join(video_ids)
            )
            video_response = video_request.execute()
            
            stats_map = {}
            for video in video_response.get("items", []):
                v_id = video["id"]
                stats = video.get("statistics", {})
                stats_map[v_id] = {
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0))
                }
            
            for v in video_data:
                stats = stats_map.get(v["video_id"], {"views": 0, "likes": 0})
                v["views"] = stats["views"]
                v["likes"] = stats["likes"]
                videos_stats.append(v)
            
            next_page_token = playlist_response.get("nextPageToken")
            if not next_page_token:
                break
                
        return videos_stats

    def get_total_likes(self, channel_id):
        """
        全動画のいいね数の合計を取得する。
        """
        videos_stats = self.get_all_videos_stats(channel_id)
        return sum(v["likes"] for v in videos_stats)


    def get_video_comments(self, video_id, max_results=100):
        """
        指定された動画のコメント（トップレベルのコメント）を取得する。
        """
        comments = []
        try:
            request = self.youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(max_results, 100),
                textFormat="plainText"
            )
            response = request.execute()
            
            for item in response.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comments.append(snippet.get("textDisplay", ""))
                
        except Exception as e:
            # コメント機能が無効な動画などの場合は空リストを返す
            print(f"Warning: Failed to fetch comments for video {video_id}: {e}")
            
        return comments

