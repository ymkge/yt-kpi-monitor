SELECT
    dt,
    channel_id,
    subscriber_count,
    view_count,
    video_count,
    total_like_count,
    updated_at
FROM
    `{{project_id}}.{{dataset_id}}.channel_kpis`
WHERE
    channel_id = @channel_id
    AND dt < @today
ORDER BY
    dt DESC
LIMIT 1;
