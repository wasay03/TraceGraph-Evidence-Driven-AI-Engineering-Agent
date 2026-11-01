CREATE OR REPLACE FUNCTION tg_snapshot_list(p_repo_id integer, p_limit integer, p_offset integer)
RETURNS TABLE (
    id integer, repo_id integer, seq integer, commit_sha text, ontology_version_id integer,
    status snapshot_status, extractor_versions jsonb, stats jsonb, error text,
    created_at timestamptz, finished_at timestamptz, total bigint
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT s.id, s.repo_id, s.seq, s.commit_sha, s.ontology_version_id, s.status,
           s.extractor_versions, s.stats, s.error, s.created_at, s.finished_at, count(*) OVER ()
    FROM snapshot s
    WHERE s.repo_id = p_repo_id
    ORDER BY s.seq DESC
    LIMIT p_limit OFFSET p_offset;
END;
$$;
