import os
import sys
from dotenv import load_dotenv
from src.bigquery_client import BigQueryClient
from src.gemini_client import GeminiClient
from src.slack_client import SlackClient

load_dotenv()

def main():
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
    if not channel_id:
        print("Error: YOUTUBE_CHANNEL_ID is not set.")
        sys.exit(1)

    print(f"Starting Weekly Strategy Report for channel: {channel_id}")

    try:
        # クライアントの初期化
        bq = BigQueryClient()
        gemini = GeminiClient()
        slack = SlackClient()

        # 1. 週次サマリデータをBigQueryから取得
        print("Fetching weekly summary from BigQuery...")
        summary_data = bq.fetch_weekly_summary(channel_id)
        if not summary_data:
            print("No data found for the last 7 days. Skipping report.")
            return

        # 2. Geminiに送るテキストを整形
        kpi_summary_text = f"""
- 期間: {summary_data['start_date']} 〜 {summary_data['end_date']}
- 登録者数増加: +{summary_data['subscriber_growth']:,} (現在: {summary_data['current_subscribers']:,})
- 総再生数増加: +{summary_data['view_growth']:,} (現在: {summary_data['current_views']:,})
- いいね数増加: +{summary_data['like_growth']:,} (現在: {summary_data['current_likes']:,})
"""

        # 3. Geminiで戦略アドバイスを生成
        print("Generating strategy advice using Gemini API...")
        advice = gemini.generate_strategy_advice(kpi_summary_text)

        # 4. Slackにレポートを送信
        print("Sending weekly report to Slack...")
        slack.send_weekly_report(summary_data, advice)

        print("Weekly Strategy Report completed successfully.")

    except Exception as e:
        print(f"Error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
