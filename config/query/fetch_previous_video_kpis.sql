SELECT
    video_id,
    likes,
    title
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
