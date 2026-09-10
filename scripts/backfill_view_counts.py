#!/usr/bin/env python3
"""
過去データ補正ワンタイムスクリプト:
video_kpis テーブルの各日時点の全動画再生数合計を算出し、
channel_kpis テーブルの view_count を一括補正して不整合・前日比スパイクを解消する。
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

def main():
    parser = argparse.ArgumentParser(
        description="video_kpis の各日全動画再生数合計に基づき channel_kpis の view_count を一括補正するスクリプト"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際の更新を行わず、更新対象レコードと差分のプレビューのみを表示します。"
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

    # 1. 更新対象レコードの事前確認クエリ（プレビュー用）
    preview_query = f"""
    SELECT
        t.dt,
        t.channel_id,
        t.view_count AS current_view_count,
        s.corrected_view_count,
        (s.corrected_view_count - t.view_count) AS diff
    FROM
        `{project_id}.{dataset_id}.channel_kpis` AS t
    JOIN (
        SELECT
            dt,
            SUM(COALESCE(views, 0)) AS corrected_view_count
        FROM
            `{project_id}.{dataset_id}.video_kpis`
        GROUP BY
            dt
    ) AS s
    ON t.dt = s.dt AND t.channel_id = @channel_id
    WHERE
        t.view_count IS NULL OR s.corrected_view_count > t.view_count
    ORDER BY
        t.dt ASC;
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("channel_id", "STRING", channel_id),
        ]
    )

    try:
        preview_job = client.query(preview_query, job_config=job_config)
        rows = list(preview_job.result())
    except Exception as e:
        print(f"Error querying preview data: {e}")
        sys.exit(1)

    if not rows:
        print("補正が必要なレコードは見つかりませんでした（すでに最新の合算値と整合しています）。")
        return

    print(f"補正対象レコード: {len(rows)} 件")
    print("-" * 65)
    print(f"{'日付 (dt)':<12} {'現在の再生数':>15} {'補正後の再生数':>16} {'差分':>15}")
    print("-" * 65)
    for row in rows:
        dt_str = str(row.dt)
        curr_v = f"{row.current_view_count:,}" if row.current_view_count is not None else "NULL"
        corr_v = f"{row.corrected_view_count:,}"
        diff_v = f"+{row.diff:,}" if row.diff is not None and row.diff >= 0 else str(row.diff)
        print(f"{dt_str:<12} {curr_v:>15} {corr_v:>16} {diff_v:>15}")
    print("-" * 65)

    if args.dry_run:
        print("Dry-run モードのため、BigQuery のデータは変更されていません。")
        return

    # 2. 本番更新の確認
    if not args.yes:
        confirm = input(f"\n上記の {len(rows)} 件のレコードを補正更新しますか？ [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("更新処理をキャンセルしました。")
            return

    # 3. MERGE クエリの実行
    merge_query = f"""
    MERGE `{project_id}.{dataset_id}.channel_kpis` AS target
    USING (
        SELECT
            dt,
            SUM(COALESCE(views, 0)) AS corrected_view_count
        FROM
            `{project_id}.{dataset_id}.video_kpis`
        GROUP BY
            dt
    ) AS source
    ON target.dt = source.dt AND target.channel_id = @channel_id
    WHEN MATCHED AND (target.view_count IS NULL OR source.corrected_view_count > target.view_count) THEN
        UPDATE SET
            target.view_count = source.corrected_view_count,
            target.updated_at = CURRENT_TIMESTAMP();
    """

    print("\nExecuting MERGE query on BigQuery...")
    try:
        merge_job = client.query(merge_query, job_config=job_config)
        merge_job.result()  # 完了待機
        affected_rows = merge_job.num_dml_affected_rows
        print(f"Success! {affected_rows} 件のレコードが正常に補正更新されました。")
    except Exception as e:
        print(f"Error executing MERGE query: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
