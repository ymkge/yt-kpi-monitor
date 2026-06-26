DELETE FROM
    `{{project_id}}.{{dataset_id}}.channel_kpis`
WHERE
    channel_id = @channel_id
    AND dt = @today;
