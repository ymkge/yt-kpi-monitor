DELETE FROM
    `{{project_id}}.{{dataset_id}}.video_kpis`
WHERE
    video_id = @video_id
    AND dt = @today;
