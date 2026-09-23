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

    def _build_video_diff_block(self, title_header, video_list, is_increase=True, max_display=3,
                                metric_name="いいね", total_prefix="計", total_field="current_likes", total_plus_sign=False):
        """
        動画の増減リストからSlack Block Kitセクションを生成する汎用メソッド。
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
            
            total_val = v.get(total_field)
            if total_val is not None:
                plus = "+" if total_plus_sign and total_val > 0 else ""
                total_str = f" ({total_prefix}{plus}{total_val:,})"
            else:
                total_str = ""
                
            details.append(f"• {tag} *{truncated_title}*: 前日比 *{diff_str}*{total_str}")
        
        if remaining_count > 0:
            action_label = "増加" if is_increase else "減少"
            details.append(f"_...他 {remaining_count} 件の動画で{metric_name}が{action_label}_")
        
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title_header}*\n" + "\n".join(details)
            }
        }

    def _build_like_diff_block(self, title_header, video_list, is_increase=True, max_display=3):
        """いいねの増減があった動画リストからSlack Block Kitセクションを生成する。"""
        return self._build_video_diff_block(
            title_header=title_header,
            video_list=video_list,
            is_increase=is_increase,
            max_display=max_display,
            metric_name="いいね",
            total_prefix="計",
            total_field="current_likes",
            total_plus_sign=False
        )

    def _build_subscriber_diff_block(self, title_header, video_list, is_increase=True, max_display=3):
        """登録者の増減があった動画リストからSlack Block Kitセクションを生成する。"""
        return self._build_video_diff_block(
            title_header=title_header,
            video_list=video_list,
            is_increase=is_increase,
            max_display=max_display,
            metric_name="登録者",
            total_prefix="累計",
            total_field="current_subscribers",
            total_plus_sign=True
        )

    def send_kpi_alert(self, current_kpi, previous_kpi=None, recent_videos_kpis=None,
                       increased_like_videos=None, decreased_like_videos=None,
                       increased_subscriber_videos=None, decreased_subscriber_videos=None):
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

        # 登録者増減ブロック（サマリの並び順に合わせて「登録者」→「いいね」の順）
        sub_inc_block = self._build_subscriber_diff_block("👥 登録者が増加した動画", increased_subscriber_videos, is_increase=True)
        if sub_inc_block:
            blocks.append(sub_inc_block)
            blocks.append({"type": "divider"})

        sub_dec_block = self._build_subscriber_diff_block("👤 登録者が減少（補正）した動画", decreased_subscriber_videos, is_increase=False)
        if sub_dec_block:
            blocks.append(sub_dec_block)
            blocks.append({"type": "divider"})

        # いいね数増減ブロック
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
                context_elements = [
                    {
                        "type": "mrkdwn",
                        "text": "💬 *直近14日以内に公開された動画の詳細KPIは、このメッセージのスレッドに投稿されています。*"
                    }
                ]
                if sub_inc_block or sub_dec_block:
                    context_elements.append({
                        "type": "mrkdwn",
                        "text": "※動画別登録者数は動画再生ページ経由の直接登録を集計（ホーム画面等からの登録は全体サマリに反映）。"
                    })

                blocks.append({
                    "type": "context",
                    "elements": context_elements
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

    def _format_compact_title(self, title: str, max_chars: int = 22) -> str:
        """
        タイトル内の改行文字を除去し、安全にトリミング（超過時は...を付与）する。
        """
        if not title:
            return ""
        clean_title = title.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        if len(clean_title) > max_chars + 3:
            return clean_title[:max_chars] + "..."
        return clean_title

    def _format_duration(self, seconds) -> str:
        """
        秒数を「⏱️ AVD: X分Y秒」形式に変換する。Noneや0以下の場合は「⏱️ AVD: -」を返す。
        """
        if seconds is None:
            return "⏱️ AVD: -"
        try:
            sec_val = int(round(float(seconds)))
            if sec_val <= 0:
                return "⏱️ AVD: -"
            m, s = divmod(sec_val, 60)
            if m > 0 and s > 0:
                time_str = f"{m}分{s}秒"
            elif m > 0:
                time_str = f"{m}分"
            else:
                time_str = f"{s}秒"
            return f"⏱️ AVD: {time_str}"
        except (ValueError, TypeError):
            return "⏱️ AVD: -"

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
                    "text": f"*チャンネル*: `{channel_title}`\n📅 *集計期間*: {start_date} 〜 {end_date} (JST)"
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

        # 動画ランキングの追加（折りたたみ防止のため種別ごとにアタッチメント分割）
        if top_views_videos:
            lines = []
            for video in top_views_videos[:3]:
                title = self._format_compact_title(video.get("title", ""))
                views_val = video.get("views", 0)
                likes_val = video.get("likes", 0)
                ctr_val = video.get("ctr", 0.0)
                ctr_part = f" | 🎯 CTR: {ctr_val:.2f}%" if ctr_val > 0 else ""
                lines.append(f"• 🎬 *{title}*: 👁️ {views_val:,} | 👍 {likes_val:,}{ctr_part}")
            thread_attachments.append({
                "title": "🔥 再生数 Top 3 (直近28日間)",
                "color": "#ff4757",
                "text": "\n".join(lines),
                "mrkdwn_in": ["text"]
            })

        if top_likes_videos:
            lines = []
            for video in top_likes_videos[:3]:
                title = self._format_compact_title(video.get("title", ""))
                likes_val = video.get("likes", 0)
                views_val = video.get("views", 0)
                ctr_val = video.get("ctr", 0.0)
                ctr_part = f" | 🎯 CTR: {ctr_val:.2f}%" if ctr_val > 0 else ""
                lines.append(f"• 🎬 *{title}*: 👍 {likes_val:,} | 👁️ {views_val:,}{ctr_part}")
            thread_attachments.append({
                "title": "👍 いいね数 Top 3 (直近28日間)",
                "color": "#2ed573",
                "text": "\n".join(lines),
                "mrkdwn_in": ["text"]
            })

        if top_ctr_videos:
            lines = []
            for video in top_ctr_videos[:3]:
                title = self._format_compact_title(video.get("title", ""))
                ctr_val = video.get("ctr", 0.0)
                impr_val = video.get("impressions", 0)
                views_val = video.get("views", 0)
                lines.append(f"• 🎬 *{title}*: 🎯 CTR: {ctr_val:.2f}% | 📢 IMP: {impr_val:,} | 👁️ {views_val:,}")
            thread_attachments.append({
                "title": "🎯 CTR Top 3 (直近28日間)",
                "color": "#1e90ff",
                "text": "\n".join(lines),
                "mrkdwn_in": ["text"]
            })

        # Geminiアドバイスの追加
        cleaned_advice = self._clean_slack_mrkdwn(advice_text)
        thread_attachments.append({
            "title": ":kuro: の改善アドバイス",
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
                            "text": "💬 *動画パフォーマンスランキングおよび :kuro: の改善アドバイスは、このメッセージのスレッドに投稿されています。*"
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
                    "text": f"*チャンネル*: `{channel_title}`\n📅 *集計期間*: {start_date} 〜 {end_date} (JST)"
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
                        "text": f"*🎯 CVR (登録転換率)*\n{cvr:.2f}%{' (※純減)' if sub_growth < 0 else ''}\n_(登録増 / 再生数増)_"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]

        # 2. スレッド用の詳細アタッチメントの構築
        thread_attachments = []

        # ① 動画ランキング（折りたたみ防止のため種別ごとにアタッチメント分割）
        if top_videos_rankings:
            if top_videos_rankings.get("views"):
                lines = []
                for v in top_videos_rankings["views"][:3]:
                    title = self._format_compact_title(v.get("title", ""))
                    views_val = v.get("views", 0)
                    lines.append(f"• 🎬 *{title}*: 👁️ {views_val:,}")
                thread_attachments.append({
                    "title": "🔥 再生数 Top 3（前月）",
                    "color": "#ff4757",
                    "text": "\n".join(lines),
                    "mrkdwn_in": ["text"]
                })

            if top_videos_rankings.get("ctr"):
                lines = []
                for v in top_videos_rankings["ctr"][:3]:
                    title = self._format_compact_title(v.get("title", ""))
                    ctr_val = v.get("ctr", 0.0)
                    impr_val = v.get("impressions", 0)
                    lines.append(f"• 🎬 *{title}*: 🎯 CTR: {ctr_val:.2f}% | 📢 IMP: {impr_val:,}")
                thread_attachments.append({
                    "title": "🎯 CTR Top 3（前月）",
                    "color": "#1e90ff",
                    "text": "\n".join(lines),
                    "mrkdwn_in": ["text"]
                })

            if top_videos_rankings.get("duration"):
                lines = []
                for v in top_videos_rankings["duration"][:3]:
                    title = self._format_compact_title(v.get("title", ""))
                    dur_str = self._format_duration(v.get("averageViewDuration"))
                    lines.append(f"• 🎬 *{title}*: {dur_str}")
                thread_attachments.append({
                    "title": "⏱️ AVD Top 3（前月）",
                    "color": "#a55eea",
                    "text": "\n".join(lines),
                    "mrkdwn_in": ["text"]
                })

        # ② 初動比較分析
        if initial_performances:
            lines = []
            for v_id, perf in initial_performances.items():
                if not perf.get("performances"):
                    continue
                title = self._format_compact_title(perf.get("title", ""))
                lines.append(f"*🎬 {title}*")
                for p in perf["performances"]:
                    days = "24時間" if p["age_days"] == 1 else "7日間"
                    ratio = (p["target_views"] / p["avg_views"] - 1) * 100 if p["avg_views"] > 0 else 0
                    sign = "+" if ratio >= 0 else ""
                    t_views = p.get("target_views", 0)
                    lines.append(f" • 🚀 {days}: 👁️ {t_views:,} (過去平均比: {sign}{ratio:.1f}%)")
            
            if lines:
                thread_attachments.append({
                    "title": "📈 新着動画の初動パフォーマンス比較",
                    "color": "#36a64f",
                    "text": "\n".join(lines),
                    "mrkdwn_in": ["text"]
                })

        # ③ 流入元と視聴者層分析
        audience_and_traffic_text = ""
        if traffic_sources:
            traffic_lines = ["*🚦 トラフィックソース Top 3*"]
            total_views = sum(s["views"] for s in traffic_sources)
            for s in traffic_sources[:3]:
                percentage = (s["views"] / total_views * 100) if total_views > 0 else 0
                views_val = s.get("views", 0)
                traffic_lines.append(f"• {s['source_type']}: {percentage:.1f}% (👁️ {views_val:,})")
            audience_and_traffic_text += "\n".join(traffic_lines)
        
        if subscriber_views:
            sub_lines = []
            sub_views = subscriber_views.get("SUBSCRIBED", {}).get("views", 0)
            unsub_views = subscriber_views.get("UNSUBSCRIBED", {}).get("views", 0)
            total_sub_views = sub_views + unsub_views
            if total_sub_views > 0:
                sub_pct = sub_views / total_sub_views * 100
                unsub_pct = unsub_views / total_sub_views * 100
                prefix = "\n\n" if audience_and_traffic_text else ""
                sub_lines.append(f"{prefix}*👥 視聴者の登録状況*")
                sub_lines.append(f"• 登録済: {sub_pct:.1f}% | 未登録: {unsub_pct:.1f}%")
                audience_and_traffic_text += "\n".join(sub_lines)

        if audience_and_traffic_text.strip():
            thread_attachments.append({
                "title": "📊 視聴者流入元 ＆ 登録者視聴比率",
                "color": "#1abc9c",
                "text": audience_and_traffic_text.strip(),
                "mrkdwn_in": ["text"]
            })

        # ④ 視聴維持率（離脱・リピート）分析
        if retentions:
            ret_lines = []
            for v_id, ret in retentions.items():
                if not ret.get("drop_points") and not ret.get("repeat_points"):
                    continue
                title = self._format_compact_title(ret.get("title", ""))
                ret_lines.append(f"*🎬 {title}*")
                if ret.get("drop_points"):
                    for dp in ret["drop_points"]:
                        ret_lines.append(f" • ⚠️ 離脱注意: {dp['percent']}%地点 (前区間比 -{dp['diff']:.1f}%)")
                if ret.get("repeat_points"):
                    for rp in ret["repeat_points"]:
                        ret_lines.append(f" • ✨ 再生維持: {rp['percent']}%地点 (前区間比 +{rp['diff']:.1f}%)")
            
            if ret_lines:
                thread_attachments.append({
                    "title": "⏱️ 視聴維持率（離脱・リピート）分析",
                    "color": "#9b59b6",
                    "text": "\n".join(ret_lines),
                    "mrkdwn_in": ["text"]
                })

        # ⑤ コメント要約（存在する場合のみ）
        if comment_analyses:
            comm_lines = []
            for v_id, comm in comment_analyses.items():
                if comm.get("summary"):
                    title = self._format_compact_title(comm.get("title", ""))
                    comm_lines.append(f"*🎬 {title}*\n{comm['summary']}")
            
            if comm_lines:
                thread_attachments.append({
                    "title": "💬 視聴者コメント分析・要約",
                    "color": "#e74c3c",
                    "text": "\n\n".join(comm_lines),
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


