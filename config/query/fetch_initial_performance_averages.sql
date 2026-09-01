WITH video_ages AS (
    SELECT
        video_id,
        DATE_DIFF(dt, DATE(published_at, 'Asia/Tokyo'), DAY) AS age_days,
        views,
        likes
    FROM
        `{{project_id}}.{{dataset_id}}.video_kpis`
    WHERE
        published_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
)
SELECT
    age_days,
    ROUND(AVG(views), 1) AS avg_views,
    ROUND(AVG(likes), 1) AS avg_likes,
    COUNT(DISTINCT video_id) AS sample_video_count
FROM
    video_ages
WHERE
    age_days IN (1, 3, 7)
GROUP BY
    age_days;
