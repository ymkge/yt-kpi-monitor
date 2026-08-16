SELECT
    video_id,
    title,
    views,
    likes,
    subscribers_gained,
    average_view_duration,
    impressions,
    ctr
FROM
    `{{project_id}}.{{dataset_id}}.video_kpis`
WHERE
    dt = (
        SELECT
            MAX(dt)
        FROM
            `{{project_id}}.{{dataset_id}}.video_kpis`
        WHERE
            dt < @today
    );
