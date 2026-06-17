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

        # 4. Slack通知
        print("Sending Slack alert...")
        slack.send_kpi_alert(current_kpi, previous_kpi)

        print("Daily KPI Monitor completed successfully.")

    except Exception as e:
        print(f"Error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
