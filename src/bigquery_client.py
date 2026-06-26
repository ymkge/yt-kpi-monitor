import os
from google.cloud import bigquery
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv()

JST = timezone(timedelta(hours=9))

class BigQueryClient:
    def __init__(self, project_id=None, dataset_id=None):
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self.dataset_id = dataset_id or os.getenv("GCP_DATASET_ID")
        if not self.project_id or not self.dataset_id:
            raise ValueError("GCP_PROJECT_ID or GCP_DATASET_ID is not set.")
        self.client = bigquery.Client(project=self.project_id)

    def save_kpi(self, kpi_data):
        """
        KPIデータをBigQueryに保存する。
        同一日付・同一チャンネルIDの既存レコードがある場合は削除（上書き）する。
        """
        table_id = f"{self.project_id}.{self.dataset_id}.channel_kpis"
        now = datetime.now(JST)
        today_str = now.strftime("%Y-%m-%d")
        
        try:
            # 1. 同一日の既存レコードを削除
            print(f"Deleting existing records for date: {today_str}, channel: {kpi_data['channel_id']}")
            delete_sql_path = os.path.join("config", "query", "delete_kpi.sql")
            with open(delete_sql_path, "r") as f:
                query_template = f.read()
                
            query = query_template.replace("{{project_id}}", self.project_id).replace("{{dataset_id}}", self.dataset_id)
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("channel_id", "STRING", kpi_data["channel_id"]),
                    bigquery.ScalarQueryParameter("today", "DATE", today_str),
                ]
            )
            
            query_job = self.client.query(query, job_config=job_config)
            query_job.result()  # 削除完了を待機
            
            # 2. 新規データの保存
            print(f"Inserting new record for date: {today_str}, channel: {kpi_data['channel_id']}")
            row = {
                "dt": today_str,
                "channel_id": kpi_data["channel_id"],
                "channel_title": kpi_data["channel_title"],
                "subscriber_count": kpi_data["subscriber_count"],
                "view_count": kpi_data["view_count"],
                "video_count": kpi_data["video_count"],
                "total_like_count": kpi_data["total_like_count"],
                "updated_at": now.isoformat(),
            }
            
            # Batch Load (JSON形式) の実行
            load_job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                schema=[
                    bigquery.SchemaField("dt", "DATE", mode="REQUIRED"),
                    bigquery.SchemaField("channel_id", "STRING", mode="REQUIRED"),
                    bigquery.SchemaField("channel_title", "STRING"),
                    bigquery.SchemaField("subscriber_count", "INT64"),
                    bigquery.SchemaField("view_count", "INT64"),
                    bigquery.SchemaField("video_count", "INT64"),
                    bigquery.SchemaField("total_like_count", "INT64"),
                    bigquery.SchemaField("updated_at", "TIMESTAMP"),
                ],
            )
            
            load_job = self.client.load_table_from_json(
                [row], table_id, job_config=load_job_config
            )
            load_job.result()  # 実行完了を待機
            
        except Exception as e:
            print(f"Error in save_kpi: {e}")
            raise e

    def fetch_previous_kpi(self, channel_id, today_str=None):
        """
        指定したチャンネルの、今日より前の最新KPIデータを取得する。
        """
        if not today_str:
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            
        sql_path = os.path.join("config", "query", "fetch_previous_kpi.sql")
        with open(sql_path, "r") as f:
            query_template = f.read()
            
        query = query_template.replace("{{project_id}}", self.project_id).replace("{{dataset_id}}", self.dataset_id)
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("channel_id", "STRING", channel_id),
                bigquery.ScalarQueryParameter("today", "DATE", today_str),
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = query_job.result()
        
        for row in results:
            return dict(row)
        
        return None
        
    def fetch_weekly_summary(self, channel_id, today_str=None):
        """
        直近1週間のKPIサマリを取得する。
        """
        if not today_str:
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            
        sql_path = os.path.join("config", "query", "aggregate_weekly_summary.sql")
        with open(sql_path, "r") as f:
            query_template = f.read()
            
        query = query_template.replace("{{project_id}}", self.project_id).replace("{{dataset_id}}", self.dataset_id)
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("channel_id", "STRING", channel_id),
                bigquery.ScalarQueryParameter("today", "DATE", today_str),
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = query_job.result()
        
        for row in results:
            return dict(row)
        
        return None
