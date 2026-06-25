import os
import requests
from dotenv import load_dotenv

load_dotenv()

class SlackClient:
    def __init__(self, webhook_url=None, bot_token=None, channel=None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")
        self.channel = channel or os.getenv("SLACK_CHANNEL")
        
        if not all([self.bot_token, self.channel]) and not self.webhook_url:
            raise ValueError("Either (SLACK_BOT_TOKEN and SLACK_CHANNEL) or SLACK_WEBHOOK_URL must be set.")

    def send_kpi_alert(self, current_kpi, previous_kpi=None, recent_videos_kpis=None):
        """
        KPIの増分を含めたSlackアラートを送信する。
        Bot Tokenが利用可能な場合は、親メッセージ(Block Kit)を送信し、スレID(ts)を返す。
        """
        channel_title = current_kpi["channel_title"]
        from datetime import datetime, timezone, timedelta
        JST = timezone(timedelta(hours=9))
        
        def format_diff(curr, prev):
            if prev is None:
                return f"{curr:,}"
            diff = curr - prev
            sign = "+" if diff >= 0 else ""
            return f"{curr:,} ({sign}{diff:,})"

        sub_text = format_diff(current_kpi["subscriber_count"], previous_kpi.get("subscriber_count") if previous_kpi else None)
        view_text = format_diff(current_kpi["view_count"], previous_kpi.get("view_count") if previous_kpi else None)
        like_text = format_diff(current_kpi["total_like_count"], previous_kpi.get("total_like_count") if previous_kpi else None)

        now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

        # 1. Block Kit による親メッセージサマリーの構築
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 YouTube KPI デイリーレポート",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*チャンネル*: `{channel_title}`\n*計測日時*: {now_str} (JST)"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*👥 登録者数*\n{sub_text}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*👁️ 再生数*\n{view_text}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*👍 いいね数*\n{like_text}"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]

        # 2. 送信方法の判別（Bot Token優先、Webhookフォールバック）
        use_bot = all([self.bot_token, self.channel])

        if use_bot:
            try:
                # Bot Tokenを利用して親メッセージを送信
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💬 *直近14日以内に公開された動画の詳細KPIは、このメッセージのスレッドに投稿されています。*"
                        }
                    ]
                })

                headers = {
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json; charset=utf-8"
                }
                payload = {
                    "channel": self.channel,
                    "blocks": blocks,
                    "text": f"📊 YouTube KPI デイリーレポート: {channel_title}",
                    "username": "クロBOT",
                    "icon_emoji": ":kuro:"
                }
                
                response = requests.post(
                    "https://slack.com/api/chat.postMessage",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                res_json = response.json()
                if not res_json.get("ok"):
                    raise ValueError(f"Slack API error: {res_json.get('error')}")
                
                # 親メッセージのタイムスタンプ(ts)を返却
                return res_json.get("ts")
            except Exception as bot_err:
                print(f"Warning: Bot Token sending failed ({bot_err}). Falling back to Webhook...")
                use_bot = False

        if not use_bot:
            # Webhookによるフォールバック送信 (地続きで動画アタッチメントも結合)
            # アタッチメントの構築
            attachments = []
            if recent_videos_kpis:
                for idx, video in enumerate(recent_videos_kpis, 1):
                    metrics = video["metrics"]
                    
                    avg_sec = metrics.get("average_view_duration")
                    if avg_sec is not None and avg_sec > 0:
                        m, s = divmod(avg_sec, 60)
                        duration_text = f"{m}分{s}秒" if m > 0 else f"{s}秒"
                    else:
                        duration_text = "集計中"

                    sub_gained = metrics.get("subscribers_gained")
                    sub_gained_text = f"+{sub_gained:,}" if sub_gained is not None else "集計中"

                    red_views = metrics.get("red_views")
                    red_views_text = f"Premium: {red_views:,} 回" if red_views is not None else "Premium: 集計中"

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

                attachments.append({
                    "color": "#a4b0be",
                    "footer": "※インプレッション数・CTRはReporting APIの仕様上、通常2〜3日前のデータが最新となります。その他の指標は通常1〜2日前のデータが最新です。"
                })

            payload = {
                "text": f"📊 *YouTube KPI Daily Alert: {channel_title}*",
                "blocks": blocks,
                "attachments": attachments,
                "username": "クロBOT",
                "icon_emoji": ":kuro:"
            }
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()
            return None

    def send_recent_video_kpis_to_thread(self, thread_ts, recent_videos_kpis):
        """
        直近動画のKPI一覧を、指定された親メッセージのスレッドに投稿する。
        """
        if not self.bot_token or not self.channel or not recent_videos_kpis:
            return

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        attachments = []
        for idx, video in enumerate(recent_videos_kpis, 1):
            metrics = video["metrics"]
            
            avg_sec = metrics.get("average_view_duration")
            if avg_sec is not None and avg_sec > 0:
                m, s = divmod(avg_sec, 60)
                duration_text = f"{m}分{s}秒" if m > 0 else f"{s}秒"
            else:
                duration_text = "集計中"

            sub_gained = metrics.get("subscribers_gained")
            sub_gained_text = f"+{sub_gained:,}" if sub_gained is not None else "集計中"

            red_views = metrics.get("red_views")
            red_views_text = f"Premium: {red_views:,} 回" if red_views is not None else "Premium: 集計中"

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

        attachments.append({
            "color": "#a4b0be",
            "footer": "※インプレッション数・CTRはReporting APIの仕様上、通常2〜3日前のデータが最新となります。その他の指標は通常1〜2日前のデータが最新です。"
        })

        payload = {
            "channel": self.channel,
            "thread_ts": thread_ts,
            "attachments": attachments,
            "username": "クロBOT",
            "icon_emoji": ":kuro:"
        }
        
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        res_json = response.json()
        if not res_json.get("ok"):
            raise ValueError(f"Slack API error: {res_json.get('error')}")

    def send_weekly_report(self, summary_data, advice_text, top_views_videos=None, top_likes_videos=None):
        """
        週次集計データとGeminiの分析結果を含めたレポートを送信する。
        数値サマリは親メッセージ(Block Kit)として送信し、
        動画ランキングやGeminiアドバイスはスレッドに投稿する。
        """
        channel_title = summary_data.get("channel_title") or summary_data["channel_id"]
        start_date = summary_data["start_date"]
        end_date = summary_data["end_date"]

        # 1. 親メッセージ (Block Kit) の構築
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📅 YouTube 週次戦略レポート",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*チャンネル*: `{channel_title}`\n*集計期間*: {start_date} 〜 {end_date} (JST)"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*👥 登録者数増分*\n+{summary_data['subscriber_growth']:,} (現在: {summary_data['current_subscribers']:,} 人)"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*👁️ 再生数増分*\n+{summary_data['view_growth']:,} 回"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*👍 いいね数増分*\n+{summary_data['like_growth']:,} 回"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]

        # 2. スレッド用の詳細アタッチメントの構築
        thread_attachments = []

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

            thread_attachments.append({
                "title": "🎬 動画パフォーマンスランキング",
                "color": "#ff9900",
                "text": ranking_text.strip(),
                "mrkdwn_in": ["text"]
            })

        # Geminiアドバイスの追加
        thread_attachments.append({
            "title": "🤖 Gemini AI 戦略アドバイス",
            "color": "#4385f4",
            "text": advice_text,
            "mrkdwn_in": ["text"]
        })

        use_bot = all([self.bot_token, self.channel])

        if use_bot:
            try:
                # スレッド誘導文を親メッセージに追加
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💬 *動画パフォーマンスランキングおよび Gemini AI 戦略アドバイスは、このメッセージのスレッドに投稿されています。*"
                        }
                    ]
                })

                headers = {
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json; charset=utf-8"
                }
                
                # 親メッセージの送信
                payload = {
                    "channel": self.channel,
                    "blocks": blocks,
                    "text": f"📅 YouTube 週次戦略レポート: {channel_title}",
                    "username": "クロBOT",
                    "icon_emoji": ":kuro:"
                }
                response = requests.post(
                    "https://slack.com/api/chat.postMessage",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                res_json = response.json()
                if not res_json.get("ok"):
                    raise ValueError(f"Slack API error: {res_json.get('error')}")
                
                thread_ts = res_json.get("ts")

                # スレッド内への投稿
                if thread_ts and thread_attachments:
                    thread_payload = {
                        "channel": self.channel,
                        "thread_ts": thread_ts,
                        "attachments": thread_attachments,
                        "username": "クロBOT",
                        "icon_emoji": ":kuro:"
                    }
                    thread_response = requests.post(
                        "https://slack.com/api/chat.postMessage",
                        headers=headers,
                        json=thread_payload
                    )
                    thread_response.raise_for_status()
                    thread_res_json = thread_response.json()
                    if not thread_res_json.get("ok"):
                        raise ValueError(f"Slack API thread error: {thread_res_json.get('error')}")

            except Exception as bot_err:
                print(f"Warning: Bot Token weekly report sending failed ({bot_err}). Falling back to Webhook...")
                use_bot = False

        if not use_bot:
            # Webhookによるフォールバック送信 (地続きで結合)
            payload = {
                "text": f"📅 *YouTube 週次戦略レポート: {channel_title}*",
                "blocks": blocks,
                "attachments": thread_attachments,
                "username": "クロBOT",
                "icon_emoji": ":kuro:"
            }
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()

