import os
from google.cloud import bigquery
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

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
        (Streaming insertは無料枠で制限されているため、DML INSERTを使用する)
        """
        table_id = f"`{self.project_id}.{self.dataset_id}.channel_kpis`"
        
        query = f"""
            INSERT INTO {table_id} (
                dt, channel_id, channel_title, subscriber_count, 
                view_count, video_count, total_like_count, updated_at
            )
            VALUES (
                CURRENT_DATE('Asia/Tokyo'),
                @channel_id,
                @channel_title,
                @subscriber_count,
                @view_count,
                @video_count,
                @total_like_count,
                CURRENT_TIMESTAMP()
            )
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("channel_id", "STRING", kpi_data["channel_id"]),
                bigquery.ScalarQueryParameter("channel_title", "STRING", kpi_data["channel_title"]),
                bigquery.ScalarQueryParameter("subscriber_count", "INT64", kpi_data["subscriber_count"]),
                bigquery.ScalarQueryParameter("view_count", "INT64", kpi_data["view_count"]),
                bigquery.ScalarQueryParameter("video_count", "INT64", kpi_data["video_count"]),
                bigquery.ScalarQueryParameter("total_like_count", "INT64", kpi_data["total_like_count"]),
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        query_job.result()  # 実行完了を待機

    def fetch_previous_kpi(self, channel_id, today_str=None):
        """
        指定したチャンネルの、今日より前の最新KPIデータを取得する。
        """
        if not today_str:
            today_str = datetime.now().strftime("%Y-%m-%d")
            
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
            today_str = datetime.now().strftime("%Y-%m-%d")
            
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
