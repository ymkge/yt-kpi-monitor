import os
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
from dotenv import load_dotenv
from src.bigquery_client import BigQueryClient
from src.gemini_client import GeminiClient
from src.slack_client import SlackClient

load_dotenv()

def format_weekly_video_rankings(top_views_videos=None, top_likes_videos=None, top_ctr_videos=None, min_impr=1500) -> str:
    """
    動画パフォーマンスランキングの各リストを重複排除し、1行パイプ区切りテキストに整形する。
    """
    if not (top_views_videos or top_likes_videos or top_ctr_videos):
        return ""

    merged = {}

    def process_list(v_list, rank_name):
        if not v_list:
            return
        for idx, v in enumerate(v_list, 1):
            vid = v.get("video_id") or v.get("title")
            if vid not in merged:
                clean_title = (v.get("title") or "不明なタイトル").replace("|", "｜")
                merged[vid] = {
                    "title": clean_title,
                    "views": v.get("views", 0),
                    "likes": v.get("likes", 0),
                    "impressions": v.get("impressions", 0),
                    "ctr": v.get("ctr", 0.0),
                    "ranks": []
                }
            merged[vid]["ranks"].append(f"{rank_name}{idx}位")
            if v.get("impressions", 0) > merged[vid]["impressions"]:
                merged[vid]["impressions"] = v.get("impressions", 0)
            if v.get("ctr", 0.0) > merged[vid]["ctr"]:
                merged[vid]["ctr"] = v.get("ctr", 0.0)

    process_list(top_views_videos, "再生")
    process_list(top_likes_videos, "いいね")
    process_list(top_ctr_videos, "CTR")

    lines = ["# 動画ランキング (直近28日)"]
    for v in merged.values():
        impr = v["impressions"]
        ctr = v["ctr"]
        if impr >= min_impr and ctr > 0:
            ctr_text = f"CTR: {ctr:.2f}% (imp: {impr:,}回)"
        else:
            ctr_text = "CTR: 対象外"
        ranks_text = " ".join([f"[{r}]" for r in v["ranks"]])
        lines.append(f"- {v['title']} | 再生: {v['views']:,}回 | いいね: {v['likes']:,}回 | {ctr_text} | ランク: {ranks_text}")

    return "\n".join(lines) + "\n"


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

        # 1. 週次サマリデータをBigQueryから取得（前日=日曜日を基準に直近1週間を集計）
        print("Fetching weekly summary from BigQuery...")
        yesterday_str = (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
        summary_data = bq.fetch_weekly_summary(channel_id, today_str=yesterday_str)
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

        try:
            min_impr = int(os.getenv("CTR_MIN_SAMPLE_IMPRESSIONS", "1500"))
        except (ValueError, TypeError):
            min_impr = 1500

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
                # 候補を広げるため、多めに200件取得
                top_views_videos_all, top_likes_videos_all = yt_analytics.get_top_videos(start_date_28, end_date_28, max_results=200)

                # Slack表示やプロンプトの通常ランキング用には上位3件を使用
                top_views_videos = top_views_videos_all[:3]
                top_likes_videos = top_likes_videos_all[:3]

                # 直近28日間に30回以上再生された動画をCTR候補とする（不平等性の解消と統計的最低ラインの担保）
                ctr_candidate_videos = []
                seen_candidates = set()
                # 再生数およびいいね数上位動画すべてからマージして判定
                for v in top_views_videos_all + top_likes_videos_all:
                    vid = v["video_id"]
                    if vid not in seen_candidates:
                        seen_candidates.add(vid)
                        if v.get("views", 0) >= 30:
                            ctr_candidate_videos.append(v)

                video_ids = [v["video_id"] for v in ctr_candidate_videos]
                if video_ids:
                    try:
                        print(f"Fetching impressions and CTR for {len(video_ids)} candidate videos...")
                        ctr_data = yt_analytics.get_impressions_and_ctr(video_ids)

                        # 各動画データにCTR情報をマージ
                        for v in ctr_candidate_videos:
                            v_ctr = ctr_data.get(v["video_id"], {})
                            v["ctr"] = v_ctr.get("ctr", 0.0)
                            v["impressions"] = v_ctr.get("impressions", 0)

                        # 表示用のTOP3動画にもCTR情報を反映する
                        for v in top_views_videos:
                            v_ctr = ctr_data.get(v["video_id"], {})
                            v["ctr"] = v_ctr.get("ctr", 0.0)
                            v["impressions"] = v_ctr.get("impressions", 0)

                        for v in top_likes_videos:
                            v_ctr = ctr_data.get(v["video_id"], {})
                            v["ctr"] = v_ctr.get("ctr", 0.0)
                            v["impressions"] = v_ctr.get("impressions", 0)

                        # CTRでソートして上位3件を抽出（インプレッション1,500回以上の動画のみ対象 #68）
                        top_ctr_videos = sorted(
                            [v for v in ctr_candidate_videos if v.get("ctr", 0.0) > 0 and v.get("impressions", 0) >= min_impr],
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
        sub_g = summary_data['subscriber_growth']
        view_g = summary_data['view_growth']
        like_g = summary_data['like_growth']

        # CVR (登録転換率) の算出（ゼロ除算・純減対策）
        sub_growth_val = sub_g or 0
        view_growth_val = view_g or 0
        cvr = (sub_growth_val / view_growth_val * 100) if view_growth_val > 0 else 0.0
        summary_data["cvr"] = cvr

        cvr_note = " (※登録解除が上回り純減)" if sub_growth_val < 0 else ""

        kpi_summary_text = (
            f"[期間] {summary_data['start_date']}〜{summary_data['end_date']} | "
            f"登録増: {sub_g:+,}人 (現{summary_data['current_subscribers']:,}人) | "
            f"再生増: {view_g:+,}回 (現{summary_data['current_views']:,}回) | "
            f"いいね増: {like_g:+,}回 (現{summary_data['current_likes']:,}回) | "
            f"CVR: {cvr:.2f}%{cvr_note}\n"
        )

        # ランキング情報がある場合はパイプ区切り1行化して補足
        rankings_text = format_weekly_video_rankings(
            top_views_videos=top_views_videos,
            top_likes_videos=top_likes_videos,
            top_ctr_videos=top_ctr_videos,
            min_impr=min_impr
        )
        if rankings_text:
            kpi_summary_text += "\n" + rankings_text

        # 4. Geminiで戦略アドバイスを生成
        print("Generating strategy advice using Gemini API...")
        try:
            advice = gemini.generate_strategy_advice(
                kpi_summary_text,
                view_growth=summary_data.get('view_growth'),
                current_subscribers=summary_data.get('current_subscribers')
            )
        except Exception as e:
            print(f"::warning::Gemini API failed to generate advice: {e}")
            advice = "🤖 *Gemini AI 週次戦略アドバイス*\n現在Gemini APIが高負荷または一時的な障害のため、AIアドバイスの生成をスキップしましたみゃ。"

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
