#!/usr/bin/env python3
"""
2026-10-04 データ補正ワンタイムスクリプト:
YouTube API の一時的なサイレント欠落により 2026-10-04 に likes=0 （一部 views=0）
として保存された 18 件の動画データを、前日 2026-10-03 の正常値で補正し、
併せて channel_kpis の total_like_count も正規の合計値に補正する。
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

def main():
    parser = argparse.ArgumentParser(
        description="2026-10-04 の欠落いいね数・再生数を補正するスクリプト"
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

    if not all([project_id, dataset_id, channel_id]):
        print("Error: GCP_PROJECT_ID, GCP_DATASET_ID, and YOUTUBE_CHANNEL_ID must be set.")
        sys.exit(1)

    client = bigquery.Client(project=project_id)

    print(f"Target Channel ID: {channel_id}")
    print(f"Target BigQuery Dataset: {project_id}.{dataset_id}")
    print(f"Mode: {'DRY-RUN (プレビューのみ)' if args.dry_run else '本番更新'}")
    print("=" * 65)

    # 1. video_kpis の補正対象プレビュー
    preview_query = f"""
    SELECT
        t.video_id,
        t.title,
        t.views AS current_views,
        s.views AS prev_views,
        t.likes AS current_likes,
        s.likes AS prev_likes
    FROM
        `{project_id}.{dataset_id}.video_kpis` AS t
    JOIN
        `{project_id}.{dataset_id}.video_kpis` AS s
    ON
        t.video_id = s.video_id
    WHERE
        t.dt = '2026-10-04'
        AND s.dt = '2026-10-03'
        AND t.likes = 0
        AND s.likes > 0
    ORDER BY
        s.likes DESC;
    """

    results = list(client.query(preview_query).result())
    print(f"Found {len(results)} videos to correct in video_kpis (dt = '2026-10-04'):\n")
    if not results:
        print("No records found requiring correction. Everything looks good!")
        return

    print(f"{'Video ID':<12} | {'Likes':<12} | {'Views':<14} | {'Title'}")
    print("-" * 65)
    for row in results:
        likes_diff = f"{row.current_likes} -> {row.prev_likes}"
        views_diff = f"{row.current_views} -> {row.prev_views}"
        print(f"{row.video_id:<12} | {likes_diff:<12} | {views_diff:<14} | {row.title[:30]}")
    print("=" * 65)

    # 2. channel_kpis の現状確認
    channel_preview_query = f"""
    SELECT
        dt,
        total_like_count
    FROM
        `{project_id}.{dataset_id}.channel_kpis`
    WHERE
        dt = '2026-10-04'
        AND channel_id = @channel_id;
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("channel_id", "STRING", channel_id),
        ]
    )
    ch_rows = list(client.query(channel_preview_query, job_config=job_config).result())
    current_total_likes = ch_rows[0].total_like_count if ch_rows else "N/A"
    print(f"Current channel_kpis total_like_count on 2026-10-04: {current_total_likes}")

    if args.dry_run:
        print("\n[DRY-RUN] No changes were made to BigQuery.")
        return

    if not args.yes:
        confirm = input("\nProceed with UPDATE on BigQuery? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted by user.")
            return

    # 3. video_kpis の UPDATE 実行
    print("\nExecuting UPDATE on video_kpis...")
    update_video_query = f"""
    UPDATE `{project_id}.{dataset_id}.video_kpis` AS t
    SET
        views = s.views,
        likes = s.likes
    FROM `{project_id}.{dataset_id}.video_kpis` AS s
    WHERE
        t.dt = '2026-10-04'
        AND s.dt = '2026-10-03'
        AND t.video_id = s.video_id
        AND t.likes = 0
        AND s.likes > 0;
    """
    video_job = client.query(update_video_query)
    video_job.result()
    print(f"Updated {video_job.num_dml_affected_rows} rows in video_kpis.")

    # 4. channel_kpis の UPDATE 実行
    print("Executing UPDATE on channel_kpis...")
    update_channel_query = f"""
    UPDATE `{project_id}.{dataset_id}.channel_kpis`
    SET
        total_like_count = (
            SELECT
                SUM(likes)
            FROM
                `{project_id}.{dataset_id}.video_kpis`
            WHERE
                dt = '2026-10-04'
        )
    WHERE
        dt = '2026-10-04'
        AND channel_id = @channel_id;
    """
    channel_job = client.query(update_channel_query, job_config=job_config)
    channel_job.result()
    print(f"Updated {channel_job.num_dml_affected_rows} rows in channel_kpis.")

    # 5. 更新後の確認
    ch_after = list(client.query(channel_preview_query, job_config=job_config).result())
    new_total_likes = ch_after[0].total_like_count if ch_after else "N/A"
    print(f"\nSuccessfully backfilled! New channel_kpis total_like_count on 2026-10-04: {new_total_likes}")

if __name__ == "__main__":
    main()
