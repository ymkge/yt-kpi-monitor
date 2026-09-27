#!/usr/bin/env python3
"""
過去データ補正ワンタイムスクリプト:
YouTube Reporting API の再発行重複をデデュープした日別データに基づき、
video_kpis テーブルの直近の各日スナップショットにおける impressions と ctr を適正値に一括補正する。
"""

import os
import sys
import io
import csv
import gzip
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google.cloud import bigquery
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

def _safe_int(val, default=0):
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _safe_float(val, default=0.0):
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def _parse_create_time(r):
    ct = r.get("createTime", "")
    if not ct:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ct.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)

def fetch_deduped_daily_reporting_data(credentials, target_video_ids):
    """
    Reporting API から直近14日分のレポートを取得し、
    (video_id, YYYY-MM-DD) -> {"impressions": imprs, "ctr": ctr}
    のデデュープ済み日別ディクショナリを生成する。
    """
    reporting = build("youtubeReporting", "v1", credentials=credentials, static_discovery=False)
    
    jobs_response = reporting.jobs().list().execute()
    jobs = jobs_response.get("jobs", [])
    job_id = None
    for job in jobs:
        if job.get("reportTypeId") == "channel_reach_basic_a1":
            job_id = job.get("id")
            break

    if not job_id:
        print("Error: channel_reach_basic_a1 job not found.")
        return {}

    created_after = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat().replace("+00:00", "Z")
    reports_response = reporting.jobs().reports().list(
        jobId=job_id,
        createdAfter=created_after
    ).execute()
    reports = reports_response.get("reports", [])

    reports.sort(key=_parse_create_time)

    import requests
    headers = {"Authorization": f"Bearer {credentials.token}"}
    daily_records = {} # (video_id, "YYYY-MM-DD") -> {"impressions": int, "ctr": float}

    for report in reports:
        download_url = report.get("downloadUrl")
        if not download_url:
            continue
        try:
            if credentials.expired:
                credentials.refresh(Request())
                headers["Authorization"] = f"Bearer {credentials.token}"

            response = requests.get(download_url, headers=headers)
            response.raise_for_status()

            if response.content.startswith(b'\x1f\x8b'):
                f = gzip.open(io.BytesIO(response.content), "rt", encoding="utf-8")
            else:
                f = io.StringIO(response.content.decode("utf-8"))

            with f:
                reader = csv.DictReader(f)
                for row in reader:
                    v_id = row.get("video_id")
                    if v_id in target_video_ids:
                        raw_date = str(row.get("date", "")).strip().replace("-", "")
                        if len(raw_date) == 8:
                            formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                        else:
                            continue
                        imprs = _safe_int(row.get("video_thumbnail_impressions"))
                        ctr = _safe_float(row.get("video_thumbnail_impressions_ctr"))
                        daily_records[(v_id, formatted_date)] = {
                            "impressions": imprs,
                            "ctr": ctr
                        }
        except Exception as err:
            print(f"Warning: Failed to process report {report.get('id')}: {err}")

    return daily_records

def main():
    parser = argparse.ArgumentParser(
        description="YouTube Reporting API のデデュープ結果に基づき video_kpis の impressions / ctr を一括補正するスクリプト"
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
    client_id = os.getenv("YOUTUBE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_OAUTH_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_OAUTH_REFRESH_TOKEN")

    if not all([project_id, dataset_id, client_id, client_secret, refresh_token]):
        print("Error: GCP_PROJECT_ID, GCP_DATASET_ID, and YouTube OAuth credentials must be set.")
        sys.exit(1)

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )
    credentials.refresh(Request())

    bq_client = bigquery.Client(project=project_id)

    print(f"Target BigQuery Dataset: {project_id}.{dataset_id}.video_kpis")
    print(f"Mode: {'DRY-RUN (プレビューのみ)' if args.dry_run else '本番更新'}")
    print("=" * 80)

    # 1. 直近14日間の video_kpis レコードのうち、impressions が記録されている対象を取得
    query = f"""
    SELECT
        dt,
        video_id,
        title,
        impressions,
        ctr
    FROM
        `{project_id}.{dataset_id}.video_kpis`
    WHERE
        dt >= DATE_SUB(CURRENT_DATE("Asia/Tokyo"), INTERVAL 14 DAY)
        AND impressions IS NOT NULL
    ORDER BY
        dt ASC,
        video_id ASC;
    """
    rows = list(bq_client.query(query).result())
    if not rows:
        print("直近14日間の video_kpis レコードが存在しません。")
        return

    target_video_ids = set(r.video_id for r in rows)
    print(f"対象動画数: {len(target_video_ids)} 本, 対象スナップショット数: {len(rows)} 行")
    print("YouTube Reporting API からデデュープ日別データを取得中...")

    daily_records = fetch_deduped_daily_reporting_data(credentials, target_video_ids)
    print(f"取得済み日別データ件数: {len(daily_records)} 件")

    # 2. 各 (dt, video_id) について、date <= dt の範囲で累積集計
    updates = []
    diff_rows = []

    for row in rows:
        dt_str = str(row.dt)
        v_id = row.video_id

        # date <= dt_str のレコードを抽出
        tot_impr = 0
        clicks_acc = 0.0
        for (vid, rec_date), stats in daily_records.items():
            if vid == v_id and rec_date <= dt_str:
                tot_impr += stats["impressions"]
                clicks_acc += stats["impressions"] * stats["ctr"]

        corr_ctr = round((clicks_acc / tot_impr * 100), 2) if tot_impr > 0 else 0.0

        curr_impr = row.impressions
        curr_ctr = round(row.ctr, 2) if row.ctr is not None else None

        # 差分があるか判定（None または 数値の不一致）
        impr_diff = (tot_impr - curr_impr) if curr_impr is not None else tot_impr
        if curr_impr != tot_impr or curr_ctr != corr_ctr:
            diff_rows.append({
                "dt": dt_str,
                "video_id": v_id,
                "title": row.title or v_id,
                "curr_impr": curr_impr,
                "corr_impr": tot_impr,
                "impr_diff": impr_diff,
                "curr_ctr": curr_ctr,
                "corr_ctr": corr_ctr
            })
            updates.append({
                "dt": dt_str,
                "video_id": v_id,
                "impressions": tot_impr,
                "ctr": corr_ctr
            })

    if not diff_rows:
        print("補正が必要なレコードは見つかりませんでした（すでに適正値と整合しています）。")
        return

    print(f"\n補正対象レコード: {len(diff_rows)} 件")
    print("-" * 100)
    print(f"{'日付':<10} {'動画ID':<12} {'現在のIMP':>10} {'補正後IMP':>10} {'差分':>10} {'現CTR':>8} {'新CTR':>8} {'タイトル'}")
    print("-" * 100)
    for d in diff_rows:
        curr_i_str = f"{d['curr_impr']:,}" if d['curr_impr'] is not None else "NULL"
        corr_i_str = f"{d['corr_impr']:,}"
        diff_i_str = f"{d['impr_diff']:+,}" if d['curr_impr'] is not None else "NEW"
        curr_c_str = f"{d['curr_ctr']:.2f}%" if d['curr_ctr'] is not None else "NULL"
        corr_c_str = f"{d['corr_ctr']:.2f}%"
        short_title = (d['title'][:25] + "...") if len(d['title']) > 25 else d['title']
        print(f"{d['dt']:<10} {d['video_id']:<12} {curr_i_str:>10} {corr_i_str:>10} {diff_i_str:>10} {curr_c_str:>8} {corr_c_str:>8} {short_title}")
    print("-" * 100)

    if args.dry_run:
        print("\nDry-run モードのため、BigQuery のデータは変更されていません。")
        return

    # 3. 本番更新の確認
    if not args.yes:
        confirm = input(f"\n上記の {len(updates)} 件のレコードを補正更新しますか？ [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("更新処理をキャンセルしました。")
            return

    # 4. MERGE クエリの実行
    print("\nExecuting MERGE query on BigQuery...")
    merge_query = f"""
    MERGE `{project_id}.{dataset_id}.video_kpis` AS target
    USING UNNEST(@updates) AS source
    ON target.dt = PARSE_DATE('%Y-%m-%d', source.dt) AND target.video_id = source.video_id
    WHEN MATCHED THEN
        UPDATE SET
            target.impressions = source.impressions,
            target.ctr = source.ctr,
            target.updated_at = CURRENT_TIMESTAMP();
    """

    query_params = [
        bigquery.ArrayQueryParameter(
            "updates",
            "RECORD",
            [
                bigquery.StructQueryParameter(
                    "",
                    bigquery.ScalarQueryParameter("dt", "STRING", u["dt"]),
                    bigquery.ScalarQueryParameter("video_id", "STRING", u["video_id"]),
                    bigquery.ScalarQueryParameter("impressions", "INT64", u["impressions"]),
                    bigquery.ScalarQueryParameter("ctr", "FLOAT64", u["ctr"]),
                )
                for u in updates
            ]
        )
    ]

    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    try:
        merge_job = bq_client.query(merge_query, job_config=job_config)
        merge_job.result()
        affected_rows = merge_job.num_dml_affected_rows
        print(f"Success! {affected_rows} 件のレコードが正常に補正更新されました。")
    except Exception as e:
        print(f"Error executing MERGE query: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
