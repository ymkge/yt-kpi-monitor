SELECT
    channel_id,
    MAX(channel_title) AS channel_title,
    MIN(dt) AS start_date,
    MAX(dt) AS end_date,
    MAX(subscriber_count) - MIN(subscriber_count) AS subscriber_growth,
    MAX(view_count) - MIN(view_count) AS view_growth,
    MAX(total_like_count) - MIN(total_like_count) AS like_growth,
    MAX(subscriber_count) AS current_subscribers,
    MAX(view_count) AS current_views,
    MAX(total_like_count) AS current_likes
FROM
    `{{project_id}}.{{dataset_id}}.channel_kpis`
WHERE
    channel_id = @channel_id
    AND dt >= DATE_SUB(@today, INTERVAL 7 DAY)
GROUP BY
    channel_id;
