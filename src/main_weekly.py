import os
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
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

        # 2. YouTube Analytics APIから詳細指標（動画ランキングなど）を取得
        # 直近28日間の日付範囲を計算
        today = datetime.now(JST)
        start_date_28 = (today - timedelta(days=28)).strftime("%Y-%m-%d")
        end_date_28 = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        top_views_videos = None
        top_likes_videos = None
        top_ctr_videos = []

        oauth_client_id = os.getenv("YOUTUBE_OAUTH_CLIENT_ID")
        oauth_client_secret = os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET")
        oauth_refresh_token = os.getenv("YOUTUBE_OAUTH_REFRESH_TOKEN")

        if oauth_client_id and oauth_client_secret and oauth_refresh_token:
            try:
                print("Initializing YouTube Analytics Client...")
                from src.youtube_analytics_client import YouTubeAnalyticsClient
                yt_analytics = YouTubeAnalyticsClient(
                    client_id=oauth_client_id,
                    client_secret=oauth_client_secret,
                    refresh_token=oauth_refresh_token
                )

                print(f"Fetching top videos data ({start_date_28} ~ {end_date_28})...")
                top_views_videos, top_likes_videos = yt_analytics.get_top_videos(start_date_28, end_date_28)

                # CTRおよびインプレッションの追加取得
                video_ids = list(set(
                    [v["video_id"] for v in top_views_videos] + [v["video_id"] for v in top_likes_videos]
                ))
                if video_ids:
                    try:
                        print("Fetching impressions and CTR for top videos...")
                        ctr_data = yt_analytics.get_impressions_and_ctr(video_ids)

                        # ランキング用データにCTR情報をマージ
                        for v in top_views_videos:
                            v_ctr = ctr_data.get(v["video_id"], {})
                            v["ctr"] = v_ctr.get("ctr", 0.0)
                            v["impressions"] = v_ctr.get("impressions", 0)

                        for v in top_likes_videos:
                            v_ctr = ctr_data.get(v["video_id"], {})
                            v["ctr"] = v_ctr.get("ctr", 0.0)
                            v["impressions"] = v_ctr.get("impressions", 0)

                        # 一意な動画リストを作成してCTRでソート
                        detailed_videos = []
                        seen = set()
                        for v in top_views_videos + top_likes_videos:
                            if v["video_id"] not in seen:
                                seen.add(v["video_id"])
                                detailed_videos.append(v)

                        top_ctr_videos = sorted(
                            [v for v in detailed_videos if v.get("ctr", 0.0) > 0],
                            key=lambda x: x["ctr"],
                            reverse=True
                        )[:3]
                    except Exception as ctr_err:
                        print(f"::warning::Failed to fetch CTR data: {ctr_err}")
                        # フォールバック処理
                        for v in top_views_videos:
                            v["ctr"] = 0.0
                            v["impressions"] = 0
                        for v in top_likes_videos:
                            v["ctr"] = 0.0
                            v["impressions"] = 0
            except Exception as oauth_err:
                print(f"::warning::Failed to fetch analytics data: {oauth_err}")
                print("Proceeding without video ranking data.")
        else:
            print("::warning::YouTube Analytics OAuth credentials are not fully set. Skipping video ranking data.")

        # 3. Geminiに送るテキストを整形
        kpi_summary_text = f"""
- 期間: {summary_data['start_date']} 〜 {summary_data['end_date']}
- 登録者数増加: +{summary_data['subscriber_growth']:,} (現在: {summary_data['current_subscribers']:,})
- 総再生数増加: +{summary_data['view_growth']:,} (現在: {summary_data['current_views']:,})
- いいね数増加: +{summary_data['like_growth']:,} (現在: {summary_data['current_likes']:,})
"""

        # ランキング情報がある場合はプロンプトに補足
        if top_views_videos or top_likes_videos or top_ctr_videos:
            kpi_summary_text += "\n# 動画パフォーマンスランキング（直近28日間）\n"
            if top_views_videos:
                kpi_summary_text += "## 再生数上位動画\n"
                for idx, v in enumerate(top_views_videos, 1):
                    ctr_val = v.get("ctr", 0.0)
                    ctr_text = f", CTR: {ctr_val:.2f}%" if ctr_val > 0 else ""
                    kpi_summary_text += f"{idx}. {v['title']} (再生数: {v['views']:,}回, いいね数: {v['likes']:,}回{ctr_text})\n"
            if top_likes_videos:
                kpi_summary_text += "## 高評価（いいね）数上位動画\n"
                for idx, v in enumerate(top_likes_videos, 1):
                    ctr_val = v.get("ctr", 0.0)
                    ctr_text = f", CTR: {ctr_val:.2f}%" if ctr_val > 0 else ""
                    kpi_summary_text += f"{idx}. {v['title']} (いいね数: {v['likes']:,}回, 再生数: {v['views']:,}回{ctr_text})\n"
            if top_ctr_videos:
                kpi_summary_text += "## クリック率（CTR）上位動画\n"
                for idx, v in enumerate(top_ctr_videos, 1):
                    kpi_summary_text += f"{idx}. {v['title']} (CTR: {v['ctr']:.2f}%, 再生数: {v['views']:,}回)\n"

        # 4. Geminiで戦略アドバイスを生成
        print("Generating strategy advice using Gemini API...")
        advice = gemini.generate_strategy_advice(kpi_summary_text)

        # 5. Slackにレポートを送信
        print("Sending weekly report to Slack...")
        slack.send_weekly_report(
            summary_data=summary_data,
            advice_text=advice,
            top_views_videos=top_views_videos,
            top_likes_videos=top_likes_videos,
            top_ctr_videos=top_ctr_videos
        )

        print("Weekly Strategy Report completed successfully.")

    except Exception as e:
        print(f"Error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
