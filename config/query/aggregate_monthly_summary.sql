WITH aggregated AS (
    SELECT
        channel_id,
        MIN(dt) AS start_date,
        MAX(dt) AS end_date,
        ARRAY_AGG(
            STRUCT(
                channel_title,
                subscriber_count,
                view_count,
                total_like_count
            )
            ORDER BY dt ASC, updated_at ASC
            LIMIT 1
        )[OFFSET(0)] AS first_record,
        ARRAY_AGG(
            STRUCT(
                channel_title,
                subscriber_count,
                view_count,
                total_like_count
            )
            ORDER BY dt DESC, updated_at DESC
            LIMIT 1
        )[OFFSET(0)] AS last_record
    FROM
        `{{project_id}}.{{dataset_id}}.channel_kpis`
    WHERE
        channel_id = @channel_id
        AND dt >= @start_date
        AND dt <= @end_date
    GROUP BY
        channel_id
)
SELECT
    channel_id,
    last_record.channel_title AS channel_title,
    start_date,
    end_date,
    last_record.subscriber_count - first_record.subscriber_count AS subscriber_growth,
    last_record.view_count - first_record.view_count AS view_growth,
    last_record.total_like_count - first_record.total_like_count AS like_growth,
    last_record.subscriber_count AS current_subscribers,
    last_record.view_count AS current_views,
    last_record.total_like_count AS current_likes
FROM
    aggregated;
