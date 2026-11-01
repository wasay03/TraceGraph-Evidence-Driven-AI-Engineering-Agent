-- Transition a snapshot's status; stats and extractor_versions are merged when provided.
CREATE OR REPLACE FUNCTION tg_snapshot_set_status(
    p_id integer, p_status snapshot_status, p_stats jsonb, p_extractor_versions jsonb, p_error text
)
RETURNS void
LANGUAGE plpgsql AS $$
#variable_conflict use_column
BEGIN
    UPDATE snapshot s
    SET status = p_status,
        stats = s.stats || coalesce(p_stats, '{}'::jsonb),
        extractor_versions = s.extractor_versions || coalesce(p_extractor_versions, '{}'::jsonb),
        error = p_error,
        finished_at = CASE WHEN p_status IN ('ready', 'failed') THEN now() ELSE s.finished_at END
    WHERE s.id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Snapshot % not found', p_id USING ERRCODE = 'TG404';
    END IF;
END;
$$;
