import os
import requests
from dotenv import load_dotenv

load_dotenv()

class SlackClient:
    def __init__(self, webhook_url=None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL is not set.")

    def send_kpi_alert(self, current_kpi, previous_kpi=None):
        """
        KPIの増分を含めたSlackアラートを送信する。
        """
        channel_title = current_kpi["channel_title"]
        
        def format_diff(curr, prev):
            if prev is None:
                return f"{curr:,}"
            diff = curr - prev
            sign = "+" if diff >= 0 else ""
            return f"{curr:,} ({sign}{diff:,})"

        sub_text = format_diff(current_kpi["subscriber_count"], previous_kpi.get("subscriber_count") if previous_kpi else None)
        view_text = format_diff(current_kpi["view_count"], previous_kpi.get("view_count") if previous_kpi else None)
        like_text = format_diff(current_kpi["total_like_count"], previous_kpi.get("total_like_count") if previous_kpi else None)

        payload = {
            "text": f"📊 *YouTube KPI Daily Alert: {channel_title}*",
            "attachments": [
                {
                    "color": "#36a64f",
                    "fields": [
                        {"title": "登録者数", "value": sub_text, "short": True},
                        {"title": "再生数", "value": view_text, "short": True},
                        {"title": "いいね数", "value": like_text, "short": True},
                    ]
                }
            ]
        }

        response = requests.post(self.webhook_url, json=payload)
        response.raise_for_status()

    def send_weekly_report(self, summary_data, advice_text, top_views_videos=None, top_likes_videos=None):
        """
        週次集計データとGeminiの分析結果を含めたレポートを送信する。
        """
        channel_id = summary_data["channel_id"]
        start_date = summary_data["start_date"]
        end_date = summary_data["end_date"]

        fields = [
            {"title": "登録者増分", "value": f"+{summary_data['subscriber_growth']:,}", "short": True},
            {"title": "再生数増分", "value": f"+{summary_data['view_growth']:,}", "short": True},
            {"title": "いいね増分", "value": f"+{summary_data['like_growth']:,}", "short": True},
            {"title": "現在登録者数", "value": f"{summary_data['current_subscribers']:,}", "short": True},
        ]

        attachments = [
            {
                "title": "数値サマリ",
                "color": "#36a64f",
                "fields": fields
            }
        ]

        # 動画ランキングの追加
        if top_views_videos or top_likes_videos:
            ranking_text = ""
            if top_views_videos:
                ranking_text += "*🔥 再生数ランキング (直近28日間)*\n"
                for idx, video in enumerate(top_views_videos, 1):
                    ranking_text += f"{idx}. {video['title']} (再生数: {video['views']:,}回, いいね数: {video['likes']:,}回)\n"
                ranking_text += "\n"

            if top_likes_videos:
                ranking_text += "*👍 高評価（いいね）数ランキング (直近28日間)*\n"
                for idx, video in enumerate(top_likes_videos, 1):
                    ranking_text += f"{idx}. {video['title']} (いいね数: {video['likes']:,}回, 再生数: {video['views']:,}回)\n"

            attachments.append({
                "title": "🎬 動画パフォーマンスランキング",
                "color": "#ff9900",
                "text": ranking_text.strip(),
                "mrkdwn_in": ["text"]
            })


        # Geminiアドバイスの追加
        attachments.append({
            "title": "🤖 Gemini AI 戦略アドバイス",
            "color": "#4385f4",
            "text": advice_text,
            "mrkdwn_in": ["text"]
        })

        payload = {
            "text": f"📅 *YouTube Weekly Strategy Report ({start_date} ~ {end_date})*",
            "attachments": attachments
        }

        response = requests.post(self.webhook_url, json=payload)
        response.raise_for_status()

