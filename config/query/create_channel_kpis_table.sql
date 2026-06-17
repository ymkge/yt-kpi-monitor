CREATE TABLE IF NOT EXISTS `{{project_id}}.{{dataset_id}}.channel_kpis` (
    dt DATE NOT NULL,
    channel_id STRING NOT NULL,
    channel_title STRING,
    subscriber_count INT64,
    view_count INT64,
    video_count INT64,
    total_like_count INT64,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY dt
CLUSTER BY channel_id;
