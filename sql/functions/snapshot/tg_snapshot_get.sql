CREATE OR REPLACE FUNCTION tg_snapshot_get(p_id integer)
RETURNS TABLE (
    id integer, repo_id integer, seq integer, commit_sha text, ontology_version_id integer,
    status snapshot_status, extractor_versions jsonb, stats jsonb, error text,
    created_at timestamptz, finished_at timestamptz
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT s.id, s.repo_id, s.seq, s.commit_sha, s.ontology_version_id, s.status,
           s.extractor_versions, s.stats, s.error, s.created_at, s.finished_at
    FROM snapshot s WHERE s.id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Snapshot % not found', p_id USING ERRCODE = 'TG404';
    END IF;
END;
$$;
