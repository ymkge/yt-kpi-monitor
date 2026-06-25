import os
import requests
from dotenv import load_dotenv

load_dotenv()

class SlackClient:
    def __init__(self, webhook_url=None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL is not set.")

    def send_kpi_alert(self, current_kpi, previous_kpi=None, recent_videos_kpis=None):
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

        attachments = [
            {
                "color": "#36a64f",
                "fields": [
                    {"title": "登録者数", "value": sub_text, "short": True},
                    {"title": "再生数", "value": view_text, "short": True},
                    {"title": "いいね数", "value": like_text, "short": True},
                ]
            }
        ]

        if recent_videos_kpis:
            # 直近動画セクションのヘッダーを追加
            attachments.append({
                "title": "🆕 直近14日以内に公開された動画のパフォーマンス",
                "color": "#4385f4",
                "text": "以下は直近14日間に公開された動画の現在のステータスです。"
            })

            for idx, video in enumerate(recent_videos_kpis, 1):
                metrics = video["metrics"]
                
                # 平均視聴時間 (0秒またはNoneの場合は集計中とする)
                avg_sec = metrics.get("average_view_duration")
                if avg_sec is not None and avg_sec > 0:
                    m, s = divmod(avg_sec, 60)
                    duration_text = f"{m}分{s}秒" if m > 0 else f"{s}秒"
                else:
                    duration_text = "集計中"

                # 登録者増分
                sub_gained = metrics.get("subscribers_gained")
                sub_gained_text = f"+{sub_gained:,}" if sub_gained is not None else "集計中"

                # Premium視聴回数
                red_views = metrics.get("red_views")
                red_views_text = f"Premium: {red_views:,} 回" if red_views is not None else "Premium: 集計中"

                # インプレッション数・CTRの文字列整形
                impressions = metrics.get("impressions")
                ctr = metrics.get("ctr")
                
                if impressions is not None and impressions > 0:
                    impressions_text = f"{impressions:,} 回"
                    ctr_text = f"{ctr:.2f}%"
                else:
                    impressions_text = "集計中 またはデータなし"
                    ctr_text = "集計中"

                pub_time = video["published_at"].replace("T", " ").replace("Z", "")[:16]

                video_text = (
                    f"📅 *公開日時*: {pub_time} (UTC)\n"
                    f"👁️ *再生数*: {metrics.get('views', 0):,} 回 ({red_views_text})\n"
                    f"👍 *いいね数*: {metrics.get('likes', 0):,}  /  👥 *登録者増*: {sub_gained_text}\n"
                    f"⏱️ *平均視聴時間*: {duration_text}\n"
                    f"📢 *インプレッション数*: {impressions_text}\n"
                    f"🎯 *クリック率 (CTR)*: {ctr_text}"
                )

                attachments.append({
                    "title": f"🎬 {idx}. {video['title']}",
                    "color": "#70a1ff" if idx % 2 == 0 else "#1e90ff",
                    "text": video_text,
                    "mrkdwn_in": ["text"]
                })

            # 注記を独立したアタッチメントとして末尾に追加
            attachments.append({
                "color": "#a4b0be",
                "footer": "※インプレッション数・CTRはReporting APIの仕様上、通常2〜3日前のデータが最新となります。その他の指標は通常1〜2日前のデータが最新です。"
            })

        payload = {
            "text": f"📊 *YouTube KPI Daily Alert: {channel_title}*",
            "attachments": attachments
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

