import os
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
from dotenv import load_dotenv
from src.youtube_client import YouTubeClient
from src.bigquery_client import BigQueryClient
from src.gemini_client import GeminiClient
from src.slack_client import SlackClient

load_dotenv()

def get_prev_month_range(base_date):
    """
    指定された日付から、前月および前々月の開始日と終了日を計算する。
    """
    first_day_of_curr_month = base_date.replace(day=1)
    last_day_of_prev_month = first_day_of_curr_month - timedelta(days=1)
    first_day_of_prev_month = last_day_of_prev_month.replace(day=1)
    
    last_day_of_prev_prev_month = first_day_of_prev_month - timedelta(days=1)
    first_day_of_prev_prev_month = last_day_of_prev_prev_month.replace(day=1)
    
    return (
        first_day_of_prev_month.strftime("%Y-%m-%d"),
        last_day_of_prev_month.strftime("%Y-%m-%d"),
        first_day_of_prev_prev_month.strftime("%Y-%m-%d"),
        last_day_of_prev_prev_month.strftime("%Y-%m-%d")
    )

def analyze_video_retention(retention_data):
    """
    視聴維持率データから、離脱の激しい区間と、維持・リピートされている区間を抽出する。
    """
    drops = []
    repeats = []
    
    for i in range(1, len(retention_data)):
        prev = retention_data[i-1]["retention_percentage"]
        curr = retention_data[i]["retention_percentage"]
        diff = curr - prev  # 負なら減少、正なら増加
        
        percent_position = int(retention_data[i]["ratio"] * 100)
        
        # 0%地点と100%地点（動画終了時）は除外
        if percent_position <= 5 or percent_position >= 95:
            continue
            
        if diff <= -2.0:  # 2%以上の減少を離脱傾向とする
            drops.append({"percent": percent_position, "diff": abs(diff)})
        elif diff >= 0.2:  # 0.2%以上の増加または横ばい維持
            repeats.append({"percent": percent_position, "diff": diff})
            
    # 影響度（差分の絶対値）の大きい順にソートして最大2件を返す
    drops = sorted(drops, key=lambda x: x["diff"], reverse=True)[:2]
    repeats = sorted(repeats, key=lambda x: x["diff"], reverse=True)[:2]
    
    return drops, repeats

def main():
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
    if not channel_id:
        print("Error: YOUTUBE_CHANNEL_ID is not set.")
        sys.exit(1)

    print(f"Starting Monthly Strategy Report for channel: {channel_id}")

    try:
        # クライアントの初期化
        yt = YouTubeClient()
        bq = BigQueryClient()
        gemini = GeminiClient()
        slack = SlackClient()

        # 1. 対象期間の計算
        today = datetime.now(JST)
        start_prev, end_prev, start_prev_prev, end_prev_prev = get_prev_month_range(today)
        print(f"Reporting Period (Prev Month): {start_prev} ~ {end_prev}")
        print(f"Comparison Period (Prev Prev Month): {start_prev_prev} ~ {end_prev_prev}")

        # 2. BigQuery から前月および前々月のチャンネルKPIサマリを取得
        print("Fetching monthly summaries from BigQuery...")
        summary_data = bq.fetch_monthly_summary(channel_id, start_prev, end_prev)
        prev_summary_data = bq.fetch_monthly_summary(channel_id, start_prev_prev, end_prev_prev)

        if not summary_data:
            print(f"No summary data found for pre month ({start_prev} ~ {end_prev}). Skipping report.")
            return

        # 3. YouTube Analytics & Reporting API からのデータ取得
        oauth_available = all([
            os.getenv("YOUTUBE_OAUTH_CLIENT_ID"),
            os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET"),
            os.getenv("YOUTUBE_OAUTH_REFRESH_TOKEN")
        ])

        traffic_sources = None
        subscriber_views = None
        top_videos_rankings = {}
        initial_performances = {}
        retentions = {}
        comment_analyses = {}

        if oauth_available:
            try:
                print("Initializing YouTube Analytics Client...")
                from src.youtube_analytics_client import YouTubeAnalyticsClient
                yt_analytics = YouTubeAnalyticsClient(
                    client_id=os.getenv("YOUTUBE_OAUTH_CLIENT_ID"),
                    client_secret=os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET"),
                    refresh_token=os.getenv("YOUTUBE_OAUTH_REFRESH_TOKEN")
                )

                # ① トラフィックソースの取得
                print("Fetching traffic sources...")
                traffic_sources = yt_analytics.get_traffic_sources(start_prev, end_prev)

                # ② 登録・未登録者別の割合の取得
                print("Fetching subscriber views...")
                subscriber_views = yt_analytics.get_subscriber_views(start_prev, end_prev)

                # ③ 前月動画ランキング（再生数・高評価数）の取得
                print("Fetching top videos for the period...")
                views_sorted, likes_sorted = yt_analytics.get_top_videos(start_prev, end_prev, max_results=3)
                top_videos_rankings["views"] = views_sorted
                top_videos_rankings["likes"] = likes_sorted

                # CTR / インプレッションおよび平均視聴時間によるランキング用の追加情報収集
                ranking_video_ids = list(set(
                    [v["video_id"] for v in views_sorted] + [v["video_id"] for v in likes_sorted]
                ))

                if ranking_video_ids:
                    print("Fetching metrics for ranking videos...")
                    metrics_data = yt_analytics.get_video_metrics(ranking_video_ids, start_prev, end_prev)
                    impressions_data = yt_analytics.get_impressions_and_ctr(ranking_video_ids)

                    # メトリクスを結合
                    detailed_videos = []
                    for vid in ranking_video_ids:
                        v_metrics = metrics_data.get(vid, {})
                        v_impr = impressions_data.get(vid, {})
                        
                        detailed_videos.append({
                            "video_id": vid,
                            "title": v_metrics.get("title", "不明な動画") if "title" in v_metrics else "", # 後ほど設定
                            "averageViewDuration": v_metrics.get("average_view_duration", 0),
                            "ctr": v_impr.get("ctr", 0.0),
                            "impressions": v_impr.get("impressions", 0)
                        })

                    # タイトルを反映
                    titles = yt_analytics._get_video_titles(ranking_video_ids)
                    for dv in detailed_videos:
                        dv["title"] = titles.get(dv["video_id"], "不明な動画")

                    # CTRランキング
                    top_videos_rankings["ctr"] = sorted(
                        [v for v in detailed_videos if v["ctr"] > 0],
                        key=lambda x: x["ctr"],
                        reverse=True
                    )[:3]

                    # 平均視聴時間ランキング
                    top_videos_rankings["duration"] = sorted(
                        detailed_videos,
                        key=lambda x: x["averageViewDuration"],
                        reverse=True
                    )[:3]

                # ④ 前月公開された動画の抽出と初動パフォーマンス分析
                print("Fetching recent upload list...")
                # Data API を使って前月公開された動画リストを BQ から引っ張るか、Analytics API 経由で取得
                # ここでは BQ の `video_kpis` から前月公開された一意な動画リストを抽出する
                import google.cloud.bigquery as bq_sdk
                bq_raw_client = bq.client
                target_videos_sql = f"""
                SELECT DISTINCT
                    video_id,
                    MAX(title) AS title,
                    MAX(published_at) AS published_at
                FROM
                    `{bq.project_id}.{bq.dataset_id}.video_kpis`
                WHERE
                    DATE(published_at) >= @start_date
                    AND DATE(published_at) <= @end_date
                GROUP BY
                    video_id;
                """
                job_config = bq_sdk.QueryJobConfig(
                    query_parameters=[
                        bq_sdk.ScalarQueryParameter("start_date", "DATE", start_prev),
                        bq_sdk.ScalarQueryParameter("end_date", "DATE", end_prev),
                    ]
                )
                query_job = bq_raw_client.query(target_videos_sql, job_config=job_config)
                uploaded_videos = [dict(row) for row in query_job.result()]

                # 各動画の初動パフォーマンスを比較
                print(f"Analyzing initial performance for {len(uploaded_videos)} videos...")
                for v in uploaded_videos[:5]:  # クォータ制限のため最大5動画に制限
                    v_id = v["video_id"]
                    perf_list = bq.fetch_video_initial_performance(v_id)
                    if perf_list:
                        initial_performances[v_id] = {
                            "title": v["title"],
                            "performances": perf_list
                        }

                # ⑤ 上位動画の視聴維持率（離脱・リピート）分析
                # 分析対象：再生数 Top 3 動画
                print("Analyzing audience retention for top videos...")
                for v in views_sorted[:3]:
                    v_id = v["video_id"]
                    try:
                        ret_data = yt_analytics.get_audience_retention(v_id, start_prev, end_prev)
                        if ret_data:
                            drops, repeats = analyze_video_retention(ret_data)
                            retentions[v_id] = {
                                "title": v["title"],
                                "drop_points": drops,
                                "repeat_points": repeats
                            }
                    except Exception as ret_err:
                        print(f"Warning: Failed to fetch retention for video {v_id}: {ret_err}")

                # ⑥ コメントの取得と感情分析
                # 分析対象：新着動画および再生数 Top 3 のうちコメントがあるもの
                comment_target_ids = list(set([v["video_id"] for v in views_sorted[:3]] + [v["video_id"] for v in uploaded_videos[:3]]))
                print(f"Fetching and analyzing comments for target videos (Max: {len(comment_target_ids)})...")
                
                for v_id in comment_target_ids:
                    # タイトルの特定
                    v_title = titles.get(v_id) if ranking_video_ids and v_id in titles else "不明な動画"
                    if v_title == "不明な動画" and uploaded_videos:
                        for uv in uploaded_videos:
                            if uv["video_id"] == v_id:
                                v_title = uv["title"]
                                break

                    print(f"Fetching comments for video: {v_title} ({v_id})...")
                    comments = yt.get_video_comments(v_id, max_results=50)
                    
                    if comments:
                        print(f"Found {len(comments)} comments. Analyzing with Gemini...")
                        comments_text = "\n".join([f"- {c}" for c in comments])
                        try:
                            analysis = gemini.analyze_comments(comments_text)
                            comment_analyses[v_id] = {
                                "title": v_title,
                                "summary": analysis
                            }
                        except Exception as gemini_comm_err:
                            print(f"Warning: Gemini comment analysis failed for video {v_id}: {gemini_comm_err}")
                    else:
                        print(f"No comments found for video {v_id}. Skipping LLM analysis.")

            except Exception as oauth_err:
                print(f"::warning::Failed to fetch detailed analytics data: {oauth_err}")
                print("Proceeding with BQ summary data only.")

        # 4. Geminiへの分析プロンプト構築とアドバイス生成
        kpi_summary_text = f"""
- 集計対象月: {summary_data['start_date']} 〜 {summary_data['end_date']}
- 登録者数増分: +{summary_data['subscriber_growth']:,} 人 (現在: {summary_data['current_subscribers']:,} 人)
- 総再生数増分: +{summary_data['view_growth']:,} 回 (現在: {summary_data['current_views']:,} 回)
- いいね数増分: +{summary_data['like_growth']:,} 回 (現在: {summary_data['current_likes']:,} 回)
"""
        if prev_summary_data:
            kpi_summary_text += f"""
(前々月比較データ)
- 前々月の登録者数増分: +{prev_summary_data['subscriber_growth']:,} 人
- 前々月の総再生数増分: +{prev_summary_data['view_growth']:,} 回
- 前々月のいいね数増分: +{prev_summary_data['like_growth']:,} 回
"""

        if top_videos_rankings.get("views"):
            kpi_summary_text += "\n# 動画再生数ランキング\n"
            for idx, v in enumerate(top_videos_rankings["views"], 1):
                kpi_summary_text += f"{idx}. {v['title']} (再生数: {v['views']:,}回)\n"

        # 視聴者分析テキスト
        audience_text = "データなし"
        if subscriber_views:
            sub_views = subscriber_views.get("SUBSCRIBED", {}).get("views", 0)
            unsub_views = subscriber_views.get("UNSUBSCRIBED", {}).get("views", 0)
            total_sub_views = sub_views + unsub_views
            if total_sub_views > 0:
                sub_pct = sub_views / total_sub_views * 100
                unsub_pct = unsub_views / total_sub_views * 100
                audience_text = f"登録者: {sub_pct:.1f}% / 未登録者: {unsub_pct:.1f}% (総再生回数: {total_sub_views:,}回)"

        # トラフィックソーステキスト
        traffic_text = "データなし"
        if traffic_sources:
            traffic_text = ""
            total_tr_views = sum(s["views"] for s in traffic_sources)
            for s in traffic_sources:
                pct = (s["views"] / total_tr_views * 100) if total_tr_views > 0 else 0
                traffic_text += f"- {s['source_type']}: {pct:.1f}% ({s['views']:,}回)\n"

        print("Generating monthly strategy advice using Gemini API...")
        advice = gemini.generate_monthly_strategy_advice(kpi_summary_text, audience_text, traffic_text)

        # 5. Slackへの月次レポート送信
        print("Sending monthly report to Slack...")
        slack.send_monthly_report(
            summary_data=summary_data,
            prev_summary_data=prev_summary_data,
            advice_text=advice,
            traffic_sources=traffic_sources,
            subscriber_views=subscriber_views,
            top_videos_rankings=top_videos_rankings,
            initial_performances=initial_performances,
            retentions=retentions,
            comment_analyses=comment_analyses
        )

        print("Monthly Strategy Report completed successfully.")

    except Exception as e:
        print(f"Error occurred in monthly report: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
