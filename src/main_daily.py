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
        
        # 1.5. 全動画の簡易スタッツ取得と総いいね数の算出
        print("Fetching all videos stats...")
        all_videos_stats = yt.get_all_videos_stats(channel_id)
        current_kpi["total_like_count"] = sum(v["likes"] for v in all_videos_stats)

        # 2. 前回のKPIを取得
        print("Fetching previous KPI from BigQuery...")
        previous_kpi = bq.fetch_previous_kpi(channel_id)
        previous_video_kpis = bq.fetch_previous_video_kpis()

        # 3. 今回のKPIを保存
        print("Saving current KPI to BigQuery...")
        bq.save_kpi(current_kpi)

        # 3.5. いいね数が増加した動画の抽出と分類
        increased_like_videos = []
        from datetime import datetime, timezone, timedelta
        JST = timezone(timedelta(hours=9))
        now_jst = datetime.now(JST)

        for v in all_videos_stats:
            v_id = v["video_id"]
            current_likes = v["likes"]
            
            # 前回のいいね数を取得（過去データがない場合は 0 とする）
            prev_likes = previous_video_kpis.get(v_id, {}).get("likes", 0)
            
            is_new_video = v_id not in previous_video_kpis
            
            # 新規動画判定（過去データがない、または公開から3日以内）
            is_new = is_new_video
            if v.get("published_at"):
                try:
                    pub_time = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
                    is_new = (now_jst - pub_time) <= timedelta(days=3)
                except Exception as parse_err:
                    print(f"Warning: Failed to parse published_at for video {v_id}: {parse_err}")

            if is_new_video:
                if current_likes > 0:
                    increased_like_videos.append({
                        "video_id": v_id,
                        "title": v["title"],
                        "diff": current_likes,
                        "current_likes": current_likes,
                        "is_new": True,
                        "published_at": v["published_at"]
                    })
            else:
                diff = current_likes - prev_likes
                if diff > 0:
                    increased_like_videos.append({
                        "video_id": v_id,
                        "title": v["title"],
                        "diff": diff,
                        "current_likes": current_likes,
                        "is_new": is_new,
                        "published_at": v["published_at"]
                    })

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
                    
                    start_date = (now_jst - timedelta(days=14)).strftime("%Y-%m-%d")
                    end_date = (now_jst - timedelta(days=1)).strftime("%Y-%m-%d")
                    
                    print(f"Fetching video metrics from Analytics API ({start_date} ~ {end_date})...")
                    metrics_data = yt_analytics.get_video_metrics(video_ids, start_date, end_date)
                    
                    print("Fetching impressions and CTR from Reporting API...")
                    impressions_data = yt_analytics.get_impressions_and_ctr(video_ids)
                    
                    for v in recent_videos:
                        v_id = v["video_id"]
                        
                        analytics_reflected = v_id in metrics_data
                        v_metrics = metrics_data.get(v_id, {})
                        
                        v_metrics["views"] = v["realtime_views"]
                        v_metrics["likes"] = v["realtime_likes"]
                        
                        v_metrics["red_views"] = v_metrics.get("red_views") if analytics_reflected else None
                        v_metrics["subscribers_gained"] = v_metrics.get("subscribers_gained") if analytics_reflected else None
                        v_metrics["average_view_duration"] = v_metrics.get("average_view_duration") if analytics_reflected else None
                        
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
                print(f"::warning::Failed to fetch recent video KPIs: {e}")
                print("Proceeding without recent video KPI report.")
        else:
            print("::warning::OAuth credentials are not fully set. Skipping recent video KPI report.")

        # 4.5. 全動画のKPIをBigQueryに保存
        recent_lookup = {v["video_id"]: v for v in recent_videos_kpis} if recent_videos_kpis else {}
        all_videos_to_save = []
        for v in all_videos_stats:
            v_id = v["video_id"]
            if v_id in recent_lookup:
                all_videos_to_save.append(recent_lookup[v_id])
            else:
                all_videos_to_save.append({
                    "video_id": v_id,
                    "title": v["title"],
                    "published_at": v["published_at"],
                    "metrics": {
                        "views": v["views"],
                        "likes": v["likes"],
                        "subscribers_gained": None,
                        "average_view_duration": None,
                        "impressions": None,
                        "ctr": None
                    }
                })

        if all_videos_to_save:
            try:
                print("Saving all video KPIs to BigQuery...")
                bq.save_video_kpis(all_videos_to_save)
            except Exception as bq_video_err:
                print(f"::warning::Failed to save video KPIs to BigQuery: {bq_video_err}")
                print("Proceeding to Slack notification.")

        # 5. Slack通知
        print("Sending Slack alert...")
        thread_ts = slack.send_kpi_alert(
            current_kpi,
            previous_kpi,
            recent_videos_kpis if recent_videos_kpis else None,
            increased_like_videos if increased_like_videos else None
        )

        
        if thread_ts and recent_videos_kpis:
            print("Sending recent video KPIs to the thread...")
            slack.send_recent_video_kpis_to_thread(thread_ts, recent_videos_kpis)

        print("Daily KPI Monitor completed successfully.")

    except Exception as e:
        print(f"Error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
