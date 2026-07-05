CREATE TABLE IF NOT EXISTS `{{project_id}}.{{dataset_id}}.video_kpis` (
    dt DATE NOT NULL,
    video_id STRING NOT NULL,
    title STRING,
    published_at TIMESTAMP,
    views INT64,
    likes INT64,
    subscribers_gained INT64,
    average_view_duration INT64,
    impressions INT64,
    ctr FLOAT64,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY dt
CLUSTER BY video_id;
