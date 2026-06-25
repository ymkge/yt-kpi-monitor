import os
import sys
from dotenv import load_dotenv
from src.youtube_client import YouTubeClient
from src.bigquery_client import BigQueryClient
from src.slack_client import SlackClient

load_dotenv()

def main():
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
    if not channel_id:
        print("Error: YOUTUBE_CHANNEL_ID is not set.")
        sys.exit(1)

    print(f"Starting Daily KPI Monitor for channel: {channel_id}")

    try:
        # クライアントの初期化
        yt = YouTubeClient()
        bq = BigQueryClient()
        slack = SlackClient()

        # 1. 現在のKPIを取得
        print("Fetching current KPI from YouTube...")
        current_kpi = yt.get_channel_stats(channel_id)
        if not current_kpi:
            print(f"Error: Could not find channel with ID {channel_id}")
            sys.exit(1)
        
        # いいね数の取得（Data API v3暂定実装）
        print("Fetching total likes (this may take a while depending on video count)...")
        current_kpi["total_like_count"] = yt.get_total_likes(channel_id)

        # 2. 前回のKPIを取得
        print("Fetching previous KPI from BigQuery...")
        previous_kpi = bq.fetch_previous_kpi(channel_id)

        # 3. 今回のKPIを保存
        print("Saving current KPI to BigQuery...")
        bq.save_kpi(current_kpi)

        # 4. 直近14日以内に公開された動画のKPIを取得
        recent_videos_kpis = []
        oauth_available = all([
            os.getenv("YOUTUBE_OAUTH_CLIENT_ID"),
            os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET"),
            os.getenv("YOUTUBE_OAUTH_REFRESH_TOKEN")
        ])

        if oauth_available:
            try:
                print("Fetching recent videos (last 14 days)...")
                recent_videos = yt.get_recent_videos(channel_id, max_days=14)
                
                if recent_videos:
                    print(f"Found {len(recent_videos)} recent videos. Fetching detailed metrics...")
                    from src.youtube_analytics_client import YouTubeAnalyticsClient
                    yt_analytics = YouTubeAnalyticsClient(
                        client_id=os.getenv("YOUTUBE_OAUTH_CLIENT_ID"),
                        client_secret=os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET"),
                        refresh_token=os.getenv("YOUTUBE_OAUTH_REFRESH_TOKEN")
                    )
                    
                    video_ids = [v["video_id"] for v in recent_videos]
                    
                    from datetime import datetime, timedelta
                    start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
                    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                    
                    print(f"Fetching video metrics from Analytics API ({start_date} ~ {end_date})...")
                    metrics_data = yt_analytics.get_video_metrics(video_ids, start_date, end_date)
                    
                    print("Fetching impressions and CTR from Reporting API...")
                    impressions_data = yt_analytics.get_impressions_and_ctr(video_ids)
                    
                    for v in recent_videos:
                        v_id = v["video_id"]
                        
                        # Analytics API からデータが取得できているか確認
                        analytics_reflected = v_id in metrics_data
                        v_metrics = metrics_data.get(v_id, {})
                        
                        # リアルタイムの再生数といいね数をマージ
                        v_metrics["views"] = v["realtime_views"]
                        v_metrics["likes"] = v["realtime_likes"]
                        
                        # 遅延する指標は、データ未反映の場合は None とする
                        v_metrics["red_views"] = v_metrics.get("red_views") if analytics_reflected else None
                        v_metrics["subscribers_gained"] = v_metrics.get("subscribers_gained") if analytics_reflected else None
                        v_metrics["average_view_duration"] = v_metrics.get("average_view_duration") if analytics_reflected else None
                        
                        # インプレッション・CTR（Reporting API）もデータがある場合のみマージ
                        v_impr = impressions_data.get(v_id)
                        if v_impr and v_impr.get("impressions", 0) > 0:
                            v_metrics["impressions"] = v_impr["impressions"]
                            v_metrics["ctr"] = v_impr["ctr"]
                        else:
                            v_metrics["impressions"] = None
                            v_metrics["ctr"] = None
                        
                        recent_videos_kpis.append({
                            "video_id": v_id,
                            "title": v["title"],
                            "published_at": v["published_at"],
                            "metrics": v_metrics
                        })
                else:
                    print("No recent videos found in the last 14 days.")
            except Exception as e:
                print(f"Warning: Failed to fetch recent video KPIs: {e}")
                print("Proceeding without recent video KPI report.")
        else:
            print("Warning: OAuth credentials are not fully set. Skipping recent video KPI report.")

        # 5. Slack通知
        print("Sending Slack alert...")
        slack.send_kpi_alert(current_kpi, previous_kpi, recent_videos_kpis if recent_videos_kpis else None)

        print("Daily KPI Monitor completed successfully.")

    except Exception as e:
        print(f"Error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
