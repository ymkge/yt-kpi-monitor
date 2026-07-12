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

        self.analytics = build("youtubeAnalytics", "v2", credentials=self.credentials, static_discovery=False)
        self.youtube = build("youtube", "v3", credentials=self.credentials, static_discovery=False)
        self.reporting = build("youtubeReporting", "v1", credentials=self.credentials, static_discovery=False)

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
        api_max_results = max(30, max_results)
        request = self.analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date_str,
            endDate=end_date_str,
            metrics="views,likes",
            dimensions="video",
            sort="-views",
            maxResults=api_max_results
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

    def get_video_metrics(self, video_ids, start_date_str, end_date_str):
        """
        指定した動画IDリストについて、期間内の視聴回数、Premium視聴回数、登録者増分、平均視聴時間、いいね数を取得する。
        """
        if not video_ids:
            return {}

        # フィルターに指定する動画IDをカンマ区切りにする
        video_filter = ",".join(video_ids)

        request = self.analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date_str,
            endDate=end_date_str,
            metrics="views,redViews,subscribersGained,averageViewDuration,likes",
            dimensions="video",
            filters=f"video=={video_filter}"
        )
        response = request.execute()

        rows = response.get("rows", [])
        metrics_by_video = {}
        
        # 初期値で埋める
        for vid in video_ids:
            metrics_by_video[vid] = {
                "views": 0,
                "red_views": 0,
                "subscribers_gained": 0,
                "average_view_duration": 0,
                "likes": 0
            }

        if rows:
            for row in rows:
                vid = row[0]
                if vid in metrics_by_video:
                    metrics_by_video[vid] = {
                        "views": int(row[1]) if row[1] is not None else 0,
                        "red_views": int(row[2]) if row[2] is not None else 0,
                        "subscribers_gained": int(row[3]) if row[3] is not None else 0,
                        "average_view_duration": int(row[4]) if row[4] is not None else 0,
                        "likes": int(row[5]) if row[5] is not None else 0
                    }

        return metrics_by_video

    def get_impressions_and_ctr(self, video_ids):
        """
        YouTube Reporting APIを使用して、指定された動画の直近14日分のインプレッション数とCTRを集計する。
        """
        import gzip
        import io
        import csv
        import requests
        from datetime import datetime, timezone, timedelta

        if not video_ids:
            return {}

        # 1. channel_reach_basic_a1 ジョブの確認・作成
        try:
            jobs_response = self.reporting.jobs().list().execute()
            jobs = jobs_response.get("jobs", [])
        except Exception as e:
            print(f"Warning: Failed to list Reporting API jobs: {e}")
            return {}

        job_id = None
        for job in jobs:
            if job.get("reportTypeId") == "channel_reach_basic_a1":
                job_id = job.get("id")
                break

        if not job_id:
            try:
                new_job = self.reporting.jobs().create(body={
                    "reportTypeId": "channel_reach_basic_a1",
                    "name": "Channel Reach Basic Job"
                }).execute()
                job_id = new_job.get("id")
                print(f"Created new Reporting API Job for channel_reach_basic_a1: {job_id}")
            except Exception as e:
                print(f"Warning: Failed to create Reporting API job: {e}")
            return {} # 新規作成直後はレポートデータがないため空で返す

        # 2. 直近14日以内に生成されたレポートのリストを取得
        created_after = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat().replace("+00:00", "Z")
        try:
            reports_response = self.reporting.jobs().reports().list(
                jobId=job_id,
                createdAfter=created_after
            ).execute()
            reports = reports_response.get("reports", [])
        except Exception as e:
            print(f"Warning: Failed to list reports for job {job_id}: {e}")
            return {}

        if not reports:
            return {}

        # 3. レポートのダウンロードと集計
        video_stats = {vid: {"impressions": 0, "clicks_accumulated": 0.0} for vid in video_ids}
        headers = {"Authorization": f"Bearer {self.credentials.token}"}

        for report in reports:
            download_url = report.get("downloadUrl")
            if not download_url:
                continue

            try:
                # credentials.tokenが期限切れの場合は自動リフレッシュされる
                if self.credentials.expired:
                    self.credentials.refresh(Request())
                    headers["Authorization"] = f"Bearer {self.credentials.token}"

                response = requests.get(download_url, headers=headers)
                response.raise_for_status()

                # GZIP 展開またはプレーンテキストとして CSV パース
                if response.content.startswith(b'\x1f\x8b'):
                    f = gzip.open(io.BytesIO(response.content), "rt", encoding="utf-8")
                else:
                    f = io.StringIO(response.content.decode("utf-8"))

                with f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        v_id = row.get("video_id")
                        if v_id in video_stats:
                            imprs = int(row.get("video_thumbnail_impressions", 0))
                            ctr = float(row.get("video_thumbnail_impressions_ctr", 0.0))
                            
                            video_stats[v_id]["impressions"] += imprs
                            video_stats[v_id]["clicks_accumulated"] += imprs * ctr
            except Exception as err:
                print(f"Warning: Failed to process report {report.get('id')}: {err}")

        # 4. CTRの逆算と整形
        result = {}
        for v_id, stats in video_stats.items():
            total_imprs = stats["impressions"]
            clicks = stats["clicks_accumulated"]
            overall_ctr = (clicks / total_imprs * 100) if total_imprs > 0 else 0.0
            
            result[v_id] = {
                "impressions": total_imprs,
                "ctr": overall_ctr
            }

        return result

    def get_traffic_sources(self, start_date_str, end_date_str, max_results=5):
        """
        指定期間内のチャンネル全体のトラフィックソース（流入元）別のデータを取得する。
        """
        request = self.analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date_str,
            endDate=end_date_str,
            metrics="views,estimatedMinutesWatched",
            dimensions="trafficSourceType",
            sort="-views",
            maxResults=max_results
        )
        response = request.execute()
        
        rows = response.get("rows", [])
        sources = []
        for row in rows:
            sources.append({
                "source_type": row[0],
                "views": int(row[1]) if row[1] is not None else 0,
                "watch_time_minutes": int(row[2]) if row[2] is not None else 0
            })
        return sources

    def get_audience_retention(self, video_id, start_date_str, end_date_str):
        """
        指定された動画の視聴維持率データを取得する。
        """
        request = self.analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date_str,
            endDate=end_date_str,
            metrics="audienceWatchRatio",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}"
        )
        response = request.execute()
        
        rows = response.get("rows", [])
        # elapsedVideoTimeRatio でソート（昇順）
        sorted_rows = sorted(rows, key=lambda x: float(x[0]))
        
        retention_data = []
        for row in sorted_rows:
            retention_data.append({
                "ratio": float(row[0]),
                "retention_percentage": float(row[1]) * 100.0 if row[1] is not None else 0.0
            })
        return retention_data

    def get_subscriber_views(self, start_date_str, end_date_str):
        """
        指定期間内のチャンネル登録者・未登録者別の視聴回数と視聴時間を取得する。
        """
        request = self.analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date_str,
            endDate=end_date_str,
            metrics="views,estimatedMinutesWatched",
            dimensions="subscribedStatus"
        )
        response = request.execute()
        
        rows = response.get("rows", [])
        sub_views = {}
        for row in rows:
            status = row[0] # 'SUBSCRIBED' or 'UNSUBSCRIBED'
            sub_views[status] = {
                "views": int(row[1]) if row[1] is not None else 0,
                "watch_time_minutes": int(row[2]) if row[2] is not None else 0
            }
        return sub_views

