#!/usr/bin/env python3
"""
2026-10-05 直近動画メトリクス補正ワンタイムスクリプト:
2026-10-05 のデイリーバッチ実行時に NameError により欠損（NULL）となってしまった
直近公開動画のメトリクス（engaged_views, subscribers_gained, average_view_duration, impressions, ctr）
を YouTube Analytics API および Reporting API から再取得し、BigQuery の video_kpis テーブルを補正する。
"""

import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google.cloud import bigquery

# プロジェクトルートをインポートパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def main():
    parser = argparse.ArgumentParser(
        description="2026-10-05 の直近動画メトリクス欠損を補正するスクリプト"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際の更新を行わず、更新対象レコードと補正値のプレビューのみを表示します。"
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="確認プロンプトをスキップして更新を実行します。"
    )
    args = parser.parse_args()

    project_id = os.getenv("GCP_PROJECT_ID")
    dataset_id = os.getenv("GCP_DATASET_ID")
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
    oauth_client_id = os.getenv("YOUTUBE_OAUTH_CLIENT_ID")
    oauth_client_secret = os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET")
    oauth_refresh_token = os.getenv("YOUTUBE_OAUTH_REFRESH_TOKEN")

    if not all([project_id, dataset_id, channel_id, oauth_client_id, oauth_client_secret, oauth_refresh_token]):
        print("Error: Missing required environment variables (GCP_* or YOUTUBE_*).")
        sys.exit(1)

    from src.youtube_client import YouTubeClient
    from src.youtube_analytics_client import YouTubeAnalyticsClient

    yt = YouTubeClient()
    yt_analytics = YouTubeAnalyticsClient(
        client_id=oauth_client_id,
        client_secret=oauth_client_secret,
        refresh_token=oauth_refresh_token
    )
    client = bigquery.Client(project=project_id)

    print(f"Target Channel ID: {channel_id}")
    print(f"Target BigQuery Dataset: {project_id}.{dataset_id}")
    print(f"Mode: {'DRY-RUN (プレビューのみ)' if args.dry_run else '本番更新'}")
    print("=" * 75)

    # 1. 2026-10-05 時点での直近14日動画の特定（公開日 2026-09-21 〜 2026-10-04）
    JST = timezone(timedelta(hours=9))
    target_dt = "2026-10-05"
    simulated_now = datetime(2026, 10, 5, 0, 48, 0, tzinfo=JST)

    print("Fetching recent videos from YouTube...")
    recent_videos = yt.get_recent_videos(channel_id, max_days=14)
    if not recent_videos:
        print("No recent videos found.")
        return

    video_ids = [v["video_id"] for v in recent_videos]
    start_date = (simulated_now - timedelta(days=14)).strftime("%Y-%m-%d")
    end_date = (simulated_now - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Fetching video metrics ({start_date} ~ {end_date})...")
    metrics_data = yt_analytics.get_video_metrics(video_ids, start_date, end_date)
    print(f"Fetching impressions and CTR...")
    impressions_data = yt_analytics.get_impressions_and_ctr(video_ids)

    # 2. 差分プレビューの作成
    print(f"\nTarget records for video_kpis (dt = '{target_dt}'):\n")
    print(f"{'Video ID':<12} | {'EngViews':<8} | {'SubGained':<9} | {'AVD(s)':<6} | {'IMP':<6} | {'CTR(%)':<6} | {'Title'}")
    print("-" * 75)

    update_payloads = []
    for v in recent_videos:
        v_id = v["video_id"]
        v_metrics = metrics_data.get(v_id, {})
        v_impr = impressions_data.get(v_id, {})

        eng_v = v_metrics.get("engaged_views")
        sub_g = v_metrics.get("subscribers_gained")
        avd = v_metrics.get("average_view_duration")
        imp = v_impr.get("impressions")
        ctr = v_impr.get("ctr")

        update_payloads.append({
            "video_id": v_id,
            "title": v["title"],
            "engaged_views": eng_v,
            "subscribers_gained": sub_g,
            "average_view_duration": avd,
            "impressions": imp,
            "ctr": ctr
        })

        eng_str = str(eng_v) if eng_v is not None else "-"
        sub_str = str(sub_g) if sub_g is not None else "-"
        avd_str = str(avd) if avd is not None else "-"
        imp_str = str(imp) if imp is not None else "-"
        ctr_str = f"{ctr:.2f}" if ctr is not None else "-"
        print(f"{v_id:<12} | {eng_str:<8} | {sub_str:<9} | {avd_str:<6} | {imp_str:<6} | {ctr_str:<6} | {v['title'][:25]}")

    print("=" * 75)

    if args.dry_run:
        print("\n[DRY-RUN] No changes were made to BigQuery.")
        return

    if not args.yes:
        confirm = input(f"\nProceed with UPDATE on BigQuery for {len(update_payloads)} videos? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted by user.")
            return

    # 3. BigQuery UPDATE の実行
    print("\nExecuting UPDATE on video_kpis...")
    total_updated = 0
    for p in update_payloads:
        update_sql = f"""
        UPDATE `{project_id}.{dataset_id}.video_kpis`
        SET
            engaged_views = @engaged_views,
            subscribers_gained = @subscribers_gained,
            average_view_duration = @average_view_duration,
            impressions = @impressions,
            ctr = @ctr
        WHERE
            dt = @dt
            AND video_id = @video_id;
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("engaged_views", "INT64", p["engaged_views"]),
                bigquery.ScalarQueryParameter("subscribers_gained", "INT64", p["subscribers_gained"]),
                bigquery.ScalarQueryParameter("average_view_duration", "INT64", p["average_view_duration"]),
                bigquery.ScalarQueryParameter("impressions", "INT64", p["impressions"]),
                bigquery.ScalarQueryParameter("ctr", "FLOAT64", p["ctr"]),
                bigquery.ScalarQueryParameter("dt", "DATE", target_dt),
                bigquery.ScalarQueryParameter("video_id", "STRING", p["video_id"]),
            ]
        )
        job = client.query(update_sql, job_config=job_config)
        job.result()
        total_updated += job.num_dml_affected_rows

    print(f"\nSuccessfully backfilled! Updated {total_updated} rows in video_kpis (dt = '{target_dt}').")

if __name__ == "__main__":
    main()
