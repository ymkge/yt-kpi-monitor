WITH video_ages AS (
    SELECT
        video_id,
        title,
        DATE(published_at) AS pub_date,
        dt,
        DATE_DIFF(dt, DATE(published_at), DAY) AS age_days,
        views,
        likes
    FROM
        `{{project_id}}.{{dataset_id}}.video_kpis`
),
average_performance AS (
    SELECT
        age_days,
        AVG(views) AS avg_views,
        AVG(likes) AS avg_likes,
        COUNT(DISTINCT video_id) AS video_count
    FROM
        video_ages
    WHERE
        age_days IN (1, 7)
    GROUP BY
        age_days
),
target_video_performance AS (
    SELECT
        video_id,
        title,
        age_days,
        views,
        likes
    FROM
        video_ages
    WHERE
        video_id = @video_id
        AND age_days IN (1, 7)
)
SELECT
    t.video_id,
    t.title,
    t.age_days,
    t.views AS target_views,
    t.likes AS target_likes,
    a.avg_views,
    a.avg_likes
FROM
    target_video_performance AS t
INNER JOIN
    average_performance AS a
ON
    t.age_days = a.age_days;
