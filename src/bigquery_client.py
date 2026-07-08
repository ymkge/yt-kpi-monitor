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

    def save_video_kpis(self, videos_kpis):
        """
        直近動画のKPIデータをBigQueryに保存する。
        同一日付・同一動画IDの既存レコードがある場合は削除（上書き）する。
        """
        table_id = f"{self.project_id}.{self.dataset_id}.video_kpis"
        now = datetime.now(JST)
        today_str = now.strftime("%Y-%m-%d")
        
        try:
            # 1. 既存レコードの削除
            delete_sql_path = os.path.join("config", "query", "delete_video_kpi.sql")
            with open(delete_sql_path, "r") as f:
                query_template = f.read()
                
            query = query_template.replace("{{project_id}}", self.project_id).replace("{{dataset_id}}", self.dataset_id)
            
            for v_kpi in videos_kpis:
                print(f"Deleting existing video record for date: {today_str}, video: {v_kpi['video_id']}")
                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("video_id", "STRING", v_kpi["video_id"]),
                        bigquery.ScalarQueryParameter("today", "DATE", today_str),
                    ]
                )
                query_job = self.client.query(query, job_config=job_config)
                query_job.result()  # 削除完了を待機
            
            # 2. 新規データの保存
            rows = []
            for v_kpi in videos_kpis:
                metrics = v_kpi.get("metrics", {})
                pub_time_str = v_kpi["published_at"]
                
                rows.append({
                    "dt": today_str,
                    "video_id": v_kpi["video_id"],
                    "title": v_kpi["title"],
                    "published_at": pub_time_str,
                    "views": metrics.get("views"),
                    "likes": metrics.get("likes"),
                    "subscribers_gained": metrics.get("subscribers_gained"),
                    "average_view_duration": metrics.get("average_view_duration"),
                    "impressions": metrics.get("impressions"),
                    "ctr": metrics.get("ctr"),
                    "updated_at": now.isoformat(),
                })
            
            if rows:
                print(f"Inserting {len(rows)} new video records for date: {today_str}")
                load_job_config = bigquery.LoadJobConfig(
                    source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                    schema=[
                        bigquery.SchemaField("dt", "DATE", mode="REQUIRED"),
                        bigquery.SchemaField("video_id", "STRING", mode="REQUIRED"),
                        bigquery.SchemaField("title", "STRING"),
                        bigquery.SchemaField("published_at", "TIMESTAMP"),
                        bigquery.SchemaField("views", "INT64"),
                        bigquery.SchemaField("likes", "INT64"),
                        bigquery.SchemaField("subscribers_gained", "INT64"),
                        bigquery.SchemaField("average_view_duration", "INT64"),
                        bigquery.SchemaField("impressions", "INT64"),
                        bigquery.SchemaField("ctr", "FLOAT64"),
                        bigquery.SchemaField("updated_at", "TIMESTAMP"),
                    ],
                )
                
                load_job = self.client.load_table_from_json(
                    rows, table_id, job_config=load_job_config
                )
                load_job.result()  # 実行完了を待機
                
        except Exception as e:
            print(f"Error in save_video_kpis: {e}")
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

    def fetch_monthly_summary(self, channel_id, start_date_str, end_date_str):
        """
        指定期間のKPIサマリをBigQueryから取得する。
        """
        sql_path = os.path.join("config", "query", "aggregate_monthly_summary.sql")
        with open(sql_path, "r") as f:
            query_template = f.read()
            
        query = query_template.replace("{{project_id}}", self.project_id).replace("{{dataset_id}}", self.dataset_id)
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("channel_id", "STRING", channel_id),
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date_str),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date_str),
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = query_job.result()
        
        for row in results:
            return dict(row)
        
        return None

    def fetch_video_initial_performance(self, video_id):
        """
        指定した動画の公開1日後および7日後のパフォーマンスを、過去の動画平均と比較して取得する。
        """
        sql_path = os.path.join("config", "query", "fetch_video_initial_performance.sql")
        with open(sql_path, "r") as f:
            query_template = f.read()
            
        query = query_template.replace("{{project_id}}", self.project_id).replace("{{dataset_id}}", self.dataset_id)
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("video_id", "STRING", video_id),
            ]
        )
        
        query_job = self.client.query(query, job_config=job_config)
        results = query_job.result()
        
        performance_list = []
        for row in results:
            performance_list.append(dict(row))
            
        return performance_list

    def fetch_previous_video_kpis(self, today_str=None):
        """
        前回の各動画のKPIデータ（いいね数など）を取得する。
        """
        if not today_str:
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            
        sql_path = os.path.join("config", "query", "fetch_previous_video_kpis.sql")
        with open(sql_path, "r") as f:
            query_template = f.read()
            
        query = query_template.replace("{{project_id}}", self.project_id).replace("{{dataset_id}}", self.dataset_id)
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("today", "DATE", today_str),
            ]
        )
        
        try:
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result()
            
            previous_video_kpis = {}
            for row in results:
                row_dict = dict(row)
                previous_video_kpis[row_dict["video_id"]] = {
                    "likes": row_dict["likes"],
                    "title": row_dict["title"]
                }
            return previous_video_kpis
        except Exception as e:
            print(f"Warning: Failed to fetch previous video KPIs: {e}")
            return {}


