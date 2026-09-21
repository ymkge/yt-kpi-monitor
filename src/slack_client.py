import os
import requests
from dotenv import load_dotenv

load_dotenv()

class SlackClient:
    # CTR評価の閾値定数 (音楽BGMチャンネル向け調整)
    CTR_THRESHOLD_EXCELLENT = 4.0
    CTR_THRESHOLD_STANDARD = 2.0
    # 統計量閾値定数 (環境変数で上書き可能、デフォルト1500回: CTR 2%で約30再生水準)
    try:
        CTR_MIN_SAMPLE_IMPRESSIONS = int(os.getenv("CTR_MIN_SAMPLE_IMPRESSIONS", "1500"))
    except (ValueError, TypeError):
        CTR_MIN_SAMPLE_IMPRESSIONS = 1500

    def __init__(self, webhook_url=None, bot_token=None, channel=None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")
        self.channel = channel or os.getenv("SLACK_CHANNEL")
        
        if not all([self.bot_token, self.channel]) and not self.webhook_url:
            raise ValueError("Either (SLACK_BOT_TOKEN and SLACK_CHANNEL) or SLACK_WEBHOOK_URL must be set.")

    def _clean_slack_mrkdwn(self, text):
        """
        Geminiなどの出力テキストから、Slack非対応のMarkdown記法 (### や **) をSlack用のmrkdwn記法 (*太字*) に変換する。
        """
        import re
        if not text:
            return ""
        # 1. ### や ## などの見出し記法を除去
        cleaned = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
        # 2. **太字** を *太字* に置換
        cleaned = re.sub(r'\*\*(.*?)\*\*', r'*\1*', cleaned)
        return cleaned.strip()

    def _get_ctr_evaluation(self, ctr, impressions=None):
        """
        CTRの値から評価ラベルと絵文字を返す。
        インプレッション数が閾値未満の場合は「参考値」として扱う。
        """
        if ctr is None:
            return ""
        
        # 統計量が不足している場合のガード判定 (impressions が指定されている場合のみ)
        if impressions is not None and impressions < self.CTR_MIN_SAMPLE_IMPRESSIONS:
            return " ⚪️ *参考値* (サンプル蓄積中・登録者中心)"

        if ctr >= self.CTR_THRESHOLD_EXCELLENT:
            return " 🟢 *優秀* (優秀なサムネイル)"
        elif ctr >= self.CTR_THRESHOLD_STANDARD:
            return " 🟡 *標準* (標準的なサムネイル)"
        else:
            return " 🔴 *要改善* (ターゲット層に届いていない)"

    def _build_like_diff_block(self, title_header, video_list, is_increase=True, max_display=3):
        """
        いいねの増減があった動画リストからSlack Block Kitセクションを生成する。
        表示上限(max_display=3)と1行インライン表示で折りたたみ(Show more)を防止する。
        """
        if not video_list:
            return None
        
        # 差分の絶対値が大きい順に並び替え
        sorted_list = sorted(video_list, key=lambda x: abs(x["diff"]), reverse=True)
        display_list = sorted_list[:max_display]
        remaining_count = len(sorted_list) - max_display
        
        details = []
        for v in display_list:
            tag = "🆕" if v.get("is_new") else "🎬"
            raw_title = v.get("title", "")
            truncated_title = raw_title[:22] + "..." if len(raw_title) > 25 else raw_title
            diff_str = f"+{v['diff']:,}" if is_increase else f"{v['diff']:,}"
            details.append(f"• {tag} *{truncated_title}*: 前日比 *{diff_str}* (計{v['current_likes']:,})")
        
        if remaining_count > 0:
            action_label = "増加" if is_increase else "減少"
            details.append(f"_...他 {remaining_count} 件の動画でいいねが{action_label}_")
        
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title_header}*\n" + "\n".join(details)
            }
        }

    def send_kpi_alert(self, current_kpi, previous_kpi=None, recent_videos_kpis=None, increased_like_videos=None, decreased_like_videos=None):
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

        inc_block = self._build_like_diff_block("👍 いいね数が増加した動画", increased_like_videos, is_increase=True)
        if inc_block:
            blocks.append(inc_block)
            blocks.append({"type": "divider"})

        dec_block = self._build_like_diff_block("👎 いいねが減少（取り消し）した動画", decreased_like_videos, is_increase=False)
        if dec_block:
            blocks.append(dec_block)
            blocks.append({"type": "divider"})

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
            attachments = self._build_recent_video_attachments(recent_videos_kpis)
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

    def _format_diff_str(self, diff_val, unit=""):
        if diff_val is None:
            return ""
        sign = "+" if diff_val >= 0 else ""
        return f"({sign}{diff_val:,}{unit})"

    def _format_duration_diff(self, diff_sec):
        if diff_sec is None:
            return ""
        if diff_sec == 0:
            return "(±0秒)"
        sign = "+" if diff_sec > 0 else "-"
        abs_sec = abs(diff_sec)
        m, s = divmod(abs_sec, 60)
        if m > 0 and s > 0:
            time_str = f"{m}分{s}秒"
        elif m > 0:
            time_str = f"{m}分"
        else:
            time_str = f"{s}秒"
        return f"({sign}{time_str})"

    def _format_ctr_diff(self, diff_ctr):
        if diff_ctr is None:
            return ""
        sign = "+" if diff_ctr >= 0 else ""
        return f"({sign}{diff_ctr:.2f}%)"

    def _build_recent_video_attachments(self, recent_videos_kpis):
        if not recent_videos_kpis:
            return []
        
        attachments = []
        for idx, video in enumerate(recent_videos_kpis, 1):
            metrics = video["metrics"]
            diffs = metrics.get("diff", {})
            
            # 公開日 (YYYY-MM-DD) & 経過日数
            pub_raw = video.get("published_at", "")
            pub_date = pub_raw[:10] if len(pub_raw) >= 10 else ""
            
            initial_info = metrics.get("initial_analysis", {})
            age_days = initial_info.get("age_days")
            age_text = f"({age_days}日目)" if age_days is not None else ""
            
            # 初速ペース (星+乖離率)
            pace_score = initial_info.get("pace_score")
            ratio_pct = initial_info.get("ratio_pct")
            pace_part = ""
            if pace_score and ratio_pct is not None:
                stars = pace_score.count("★")
                sign = "+" if ratio_pct >= 0 else ""
                pace_part = f" | 🚀 ★{stars}({sign}{ratio_pct:.0f}%)"

            line1 = f"📅 {pub_date} {age_text}{pace_part}".strip()

            # 再生数 & Premium
            views = metrics.get("views", 0)
            views_diff_str = self._format_diff_str(diffs.get("views"), unit="")
            red_views = metrics.get("red_views")
            red_part = f" (Pre:{red_views:,})" if red_views is not None and red_views > 0 else ""
            views_part = f"👁️ {views:,}{views_diff_str}{red_part}"

            # エンゲージビュー & エンゲージ率
            engaged_views = metrics.get("engaged_views")
            eng_diff_str = self._format_diff_str(diffs.get("engaged_views"), unit="")
            engage_rate = metrics.get("engage_rate")
            if engaged_views is not None:
                rate_text = f"({engage_rate:.0f}%)" if engage_rate is not None else ""
                eng_part = f"✨ EnView: {engaged_views:,}{eng_diff_str}{rate_text}"
            else:
                eng_part = "✨ EnView: -"

            line2 = f"{views_part} | {eng_part}"

            # インプレッション
            impressions = metrics.get("impressions")
            impr_diff_str = self._format_diff_str(diffs.get("impressions"), unit="")
            if impressions is not None and impressions > 0:
                impr_part = f"📢 IMP: {impressions:,}{impr_diff_str}"
            else:
                impr_part = "📢 IMP: -"

            # CTR & 簡易アイコン
            ctr = metrics.get("ctr")
            ctr_diff_str = self._format_ctr_diff(diffs.get("ctr"))
            if impressions is not None and impressions > 0 and ctr is not None:
                if ctr >= self.CTR_THRESHOLD_EXCELLENT:
                    eval_icon = "🟢"
                elif ctr >= self.CTR_THRESHOLD_STANDARD:
                    eval_icon = "🟡"
                else:
                    eval_icon = "🔴"
                ctr_part = f"🎯 CTR: {ctr:.2f}%{ctr_diff_str} {eval_icon}"
            else:
                ctr_part = "🎯 CTR: -"

            line3 = f"{impr_part} | {ctr_part}"

            # 平均視聴時間
            avg_sec = metrics.get("average_view_duration")
            dur_diff_str = self._format_duration_diff(diffs.get("average_view_duration"))
            if avg_sec is not None and avg_sec > 0:
                m, s = divmod(avg_sec, 60)
                dur_str = f"{m}分{s}秒" if m > 0 and s > 0 else (f"{m}分" if m > 0 else f"{s}秒")
                duration_part = f"⏱️ AVD: {dur_str}{dur_diff_str}"
            else:
                duration_part = "⏱️ AVD: -"

            # 登録者増 (差分0は冗長な(+0)を省略)
            sub_gained = metrics.get("subscribers_gained")
            sub_diff_val = diffs.get("subscribers_gained")
            sub_diff_str = self._format_diff_str(sub_diff_val) if sub_diff_val != 0 else ""
            sub_part = f"👥 +{sub_gained}{sub_diff_str}" if sub_gained is not None else "👥 -"

            # いいね数 (差分0は冗長な(+0)を省略)
            likes = metrics.get("likes", 0)
            likes_diff_val = diffs.get("likes")
            likes_diff_str = self._format_diff_str(likes_diff_val) if likes_diff_val != 0 else ""
            likes_part = f"👍 {likes:,}{likes_diff_str}"

            line4 = f"{duration_part} | {sub_part} | {likes_part}"

            # 4行ウルトラスリム構成 (改行数: 3固定)
            video_text = f"{line1}\n{line2}\n{line3}\n{line4}"

            # タイトルを全角22文字前後にトリミングして複数行化を防止
            raw_title = video.get("title", "")
            truncated_title = raw_title[:22] + "..." if len(raw_title) > 25 else raw_title

            attachments.append({
                "title": f"🎬 {idx}. {truncated_title}",
                "color": "#70a1ff" if idx % 2 == 0 else "#1e90ff",
                "text": video_text,
                "mrkdwn_in": ["text"]
            })

        attachments.append({
            "color": "#a4b0be",
            "footer": "※インプレッション数・CTRはReporting APIの仕様上、通常2〜3日前のデータが最新となります。その他の指標は通常1〜2日前のデータが最新です。"
        })
        return attachments

    def send_recent_video_kpis_to_thread(self, thread_ts: str, recent_videos_kpis: list) -> bool:
        """
        直近14日動画の詳細KPIアタッチメントを、親メッセージのスレッド(thread_ts)へ送信する。
        """
        if not recent_videos_kpis or not thread_ts or not self.bot_token or not self.channel:
            return False

        attachments = self._build_recent_video_attachments(recent_videos_kpis)
        if not attachments:
            return False

        # Slack API制限: 1リクエストあたりの attachments 最大件数は10件
        if len(attachments) > 10:
            footer = attachments[-1]
            video_atts = attachments[:-1][:9]
            attachments = video_atts + [footer]

        try:
            headers = {
                "Authorization": f"Bearer {self.bot_token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            payload = {
                "channel": self.channel,
                "thread_ts": thread_ts,
                "text": "🎬 直近14日間に公開された動画の詳細KPI",
                "attachments": attachments,
                "username": "クロBOT",
                "icon_emoji": ":kuro:"
            }
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            res_json = response.json()
            if not res_json.get("ok"):
                print(f"::warning::Slack thread API error: {res_json.get('error')}")
                return False
            return True
        except Exception as e:
            print(f"::warning::Failed to send recent video KPIs to thread: {e}")
            return False

    def _format_signed_val(self, val, unit=""):
        if val is None:
            return f"0{unit}"
        return f"{val:+,}{unit}"

    def send_weekly_report(self, summary_data, advice_text, top_views_videos=None, top_likes_videos=None, top_ctr_videos=None):
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
                    "text": "📊 YouTube 週次戦略レポート",
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
                        "text": f"*👥 登録者数増分*\n{self._format_signed_val(summary_data['subscriber_growth'])} (現在: {summary_data['current_subscribers']:,} 人)"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*👁️ 再生数増分*\n{self._format_signed_val(summary_data['view_growth'], ' 回')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*👍 いいね数増分*\n{self._format_signed_val(summary_data['like_growth'], ' 回')}"
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
        if top_views_videos or top_likes_videos or top_ctr_videos:
            ranking_text = ""
            if top_views_videos:
                ranking_text += "*🔥 再生数ランキング (直近28日間)*\n"
                for idx, video in enumerate(top_views_videos, 1):
                    ctr_val = video.get('ctr', 0.0)
                    ctr_text = f", CTR: {ctr_val:.2f}%" if ctr_val > 0 else ""
                    ranking_text += f"{idx}. {video['title']} (再生数: {video['views']:,}回, いいね数: {video['likes']:,}回{ctr_text})\n"
                ranking_text += "\n"

            if top_likes_videos:
                ranking_text += "*👍 高評価（いいね）数ランキング (直近28日間)*\n"
                for idx, video in enumerate(top_likes_videos, 1):
                    ctr_val = video.get('ctr', 0.0)
                    ctr_text = f", CTR: {ctr_val:.2f}%" if ctr_val > 0 else ""
                    ranking_text += f"{idx}. {video['title']} (いいね数: {video['likes']:,}回, 再生数: {video['views']:,}回{ctr_text})\n"
                ranking_text += "\n"

            if top_ctr_videos:
                ranking_text += "*🎯 クリック率 (CTR) ランキング (直近28日間)*\n"
                for idx, video in enumerate(top_ctr_videos, 1):
                    impr_val = video.get('impressions', 0)
                    ranking_text += f"{idx}. {video['title']} (CTR: {video['ctr']:.2f}%, インプレッション: {impr_val:,}回, 再生数: {video['views']:,}回)\n"

            thread_attachments.append({
                "title": "🎬 動画パフォーマンスランキング",
                "color": "#ff9900",
                "text": ranking_text.strip(),
                "mrkdwn_in": ["text"]
            })

        # Geminiアドバイスの追加
        cleaned_advice = self._clean_slack_mrkdwn(advice_text)
        thread_attachments.append({
            "title": ":kuro: の打改善アドバイス",
            "color": "#4385f4",
            "text": cleaned_advice,
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
                            "text": "💬 *動画パフォーマンスランキングおよび :kuro: の打改善アドバイスは、このメッセージのスレッドに投稿されています。*"
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

    def send_monthly_report(self, summary_data, prev_summary_data, advice_text, traffic_sources=None, subscriber_views=None, top_videos_rankings=None, initial_performances=None, retentions=None, comment_analyses=None):
        """
        月次集計データと各種分析結果を含めたレポートを送信する。
        数値サマリは親メッセージ(Block Kit)として送信し、
        詳細な分析（動画ランキング、トラフィックソース、視聴維持率、Geminiアドバイス、コメント要約など）はスレッドに投稿する。
        """
        channel_title = summary_data.get("channel_title") or summary_data["channel_id"]
        start_date = summary_data["start_date"]
        end_date = summary_data["end_date"]

        # 前月比（％）の算出用ヘルパー
        def calc_ratio_text(curr_growth, prev_growth):
            if prev_growth is None or prev_growth <= 0:
                return "前月比: --"
            ratio = (curr_growth / prev_growth - 1) * 100
            sign = "+" if ratio >= 0 else ""
            return f"前月比: {sign}{ratio:.1f}%"

        sub_growth = summary_data["subscriber_growth"]
        view_growth = summary_data["view_growth"]
        like_growth = summary_data["like_growth"]
        uploaded_count = summary_data.get("uploaded_video_count", 0)
        cvr = summary_data.get("cvr", 0.0)

        prev_sub_growth = prev_summary_data["subscriber_growth"] if prev_summary_data else 0
        prev_view_growth = prev_summary_data["view_growth"] if prev_summary_data else 0
        prev_like_growth = prev_summary_data["like_growth"] if prev_summary_data else 0

        sub_ratio_text = calc_ratio_text(sub_growth, prev_sub_growth)
        view_ratio_text = calc_ratio_text(view_growth, prev_view_growth)
        like_ratio_text = calc_ratio_text(like_growth, prev_like_growth)

        # 1. 親メッセージ (Block Kit) の構築
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 YouTube 月次戦略レポート",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*チャンネル*: `{channel_title}`\n*対象月*: {start_date} 〜 {end_date} (JST)"
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
                        "text": f"*👥 登録者数増分*\n{self._format_signed_val(sub_growth, ' 人')}\n_({sub_ratio_text})_\n現在: {summary_data['current_subscribers']:,} 人"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*👁️ 再生数増分*\n{self._format_signed_val(view_growth, ' 回')}\n_({view_ratio_text})_"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*👍 いいね数増分*\n{self._format_signed_val(like_growth, ' 回')}\n_({like_ratio_text})_"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*🎬 当月の公開動画*\n{uploaded_count} 本"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*🎯 登録転換率 (CVR)*\n{cvr:.2f}%{' (※純減)' if sub_growth < 0 else ''}\n_(登録増 / 再生数増)_"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]

        # 2. スレッド用の詳細アタッチメントの構築
        thread_attachments = []

        # ① 動画ランキングと初動分析
        if top_videos_rankings:
            ranking_text = ""
            if top_videos_rankings.get("views"):
                ranking_text += "*🔥 再生数 Top 3*\n"
                for idx, v in enumerate(top_videos_rankings["views"][:3], 1):
                    ranking_text += f"{idx}. {v['title']} (再生: {v['views']:,}回)\n"
            if top_videos_rankings.get("ctr"):
                ranking_text += "\n*🎯 クリック率 (CTR) Top 3*\n"
                for idx, v in enumerate(top_videos_rankings["ctr"][:3], 1):
                    impr_val = v.get('impressions', 0)
                    ranking_text += f"{idx}. {v['title']} (CTR: {v['ctr']:.2f}%, インプレッション: {impr_val:,}回)\n"
            if top_videos_rankings.get("duration"):
                ranking_text += "\n*⏱️ 平均視聴時間 Top 3*\n"
                for idx, v in enumerate(top_videos_rankings["duration"][:3], 1):
                    m, s = divmod(v['averageViewDuration'], 60)
                    ranking_text += f"{idx}. {v['title']} (平均: {m}分{s}秒)\n"
            
            if ranking_text:
                thread_attachments.append({
                    "title": "🎬 動画パフォーマンスランキング（前月）",
                    "color": "#ff9900",
                    "text": ranking_text.strip(),
                    "mrkdwn_in": ["text"]
                })

        # ② 初動比較分析
        if initial_performances:
            init_text = ""
            for v_id, perf in initial_performances.items():
                if not perf.get("performances"):
                    continue
                init_text += f"*【{perf['title']}】*\n"
                for p in perf["performances"]:
                    days = "24時間" if p["age_days"] == 1 else "7日間"
                    ratio = (p["target_views"] / p["avg_views"] - 1) * 100 if p["avg_views"] > 0 else 0
                    sign = "+" if ratio >= 0 else ""
                    init_text += f" - 公開{days}再生数: {p['target_views']:,}回 (過去平均比: {sign}{ratio:.1f}%)\n"
            
            if init_text:
                thread_attachments.append({
                    "title": "📈 新着動画の初動パフォーマンス比較",
                    "color": "#36a64f",
                    "text": init_text.strip(),
                    "mrkdwn_in": ["text"]
                })

        # ③ 流入元と視聴者層分析
        audience_and_traffic_text = ""
        if traffic_sources:
            audience_and_traffic_text += "*🚦 トラフィックソース割合*\n"
            total_views = sum(s["views"] for s in traffic_sources)
            for s in traffic_sources[:3]:
                percentage = (s["views"] / total_views * 100) if total_views > 0 else 0
                audience_and_traffic_text += f" - {s['source_type']}: {percentage:.1f}% ({s['views']:,}回)\n"
        
        if subscriber_views:
            audience_and_traffic_text += "\n*👥 登録状況別の視聴者割合*\n"
            sub_views = subscriber_views.get("SUBSCRIBED", {}).get("views", 0)
            unsub_views = subscriber_views.get("UNSUBSCRIBED", {}).get("views", 0)
            total_sub_views = sub_views + unsub_views
            if total_sub_views > 0:
                sub_pct = sub_views / total_sub_views * 100
                unsub_pct = unsub_views / total_sub_views * 100
                audience_and_traffic_text += f" - 登録者: {sub_pct:.1f}% / 未登録者: {unsub_pct:.1f}%\n"

        if audience_and_traffic_text:
            thread_attachments.append({
                "title": "📊 視聴者流入元 ＆ 登録者視聴比率",
                "color": "#1abc9c",
                "text": audience_and_traffic_text.strip(),
                "mrkdwn_in": ["text"]
            })

        # ④ 視聴維持率（離脱・リピート）分析
        if retentions:
            ret_text = ""
            for v_id, ret in retentions.items():
                if not ret.get("drop_points") and not ret.get("repeat_points"):
                    continue
                ret_text += f"*【{ret['title']}】*\n"
                if ret.get("drop_points"):
                    ret_text += " ⚠️ *離脱注意ポイント*:\n"
                    for dp in ret["drop_points"]:
                        ret_text += f"   - 動画の {dp['percent']}% 地点 (前区間比 -{dp['diff']:.1f}%)\n"
                if ret.get("repeat_points"):
                    ret_text += " ✨ *繰り返し再生・維持ポイント*:\n"
                    for rp in ret["repeat_points"]:
                        ret_text += f"   - 動画の {rp['percent']}% 地点 (前区間比 +{rp['diff']:.1f}%)\n"
            
            if ret_text:
                thread_attachments.append({
                    "title": "⏱️ 視聴維持率（離脱・リピート）分析",
                    "color": "#9b59b6",
                    "text": ret_text.strip(),
                    "mrkdwn_in": ["text"]
                })

        # ⑤ コメント要約（存在する場合のみ）
        if comment_analyses:
            comm_text = ""
            for v_id, comm in comment_analyses.items():
                if comm.get("summary"):
                    comm_text += f"*【{comm['title']}】*\n{comm['summary']}\n\n"
            
            if comm_text:
                thread_attachments.append({
                    "title": "💬 視聴者コメント分析・要約",
                    "color": "#e74c3c",
                    "text": comm_text.strip(),
                    "mrkdwn_in": ["text"]
                })

        # ⑥ Geminiアドバイスの追加
        cleaned_advice = self._clean_slack_mrkdwn(advice_text)
        thread_attachments.append({
            "title": "🤖 Gemini AI 月次戦略アドバイス",
            "color": "#4385f4",
            "text": cleaned_advice,
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
                            "text": "💬 *動画ランキング、流入分析、視聴維持率、Geminiアドバイス、コメント要約などは、このメッセージのスレッドに投稿されています。*"
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
                    "text": f"📊 YouTube 月次戦略レポート: {channel_title}",
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
                print(f"Warning: Bot Token monthly report sending failed ({bot_err}). Falling back to Webhook...")
                use_bot = False

        if not use_bot:
            # Webhookによるフォールバック送信 (地続きで結合)
            payload = {
                "text": f"📊 *YouTube 月次戦略レポート: {channel_title}*",
                "blocks": blocks,
                "attachments": thread_attachments,
                "username": "クロBOT",
                "icon_emoji": ":kuro:"
            }
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()


