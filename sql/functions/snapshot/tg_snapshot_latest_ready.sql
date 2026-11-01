-- Latest ready snapshot of a repo, optionally strictly before a seq (for incremental bases).
CREATE OR REPLACE FUNCTION tg_snapshot_latest_ready(p_repo_id integer, p_before_seq integer)
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
    FROM snapshot s
    WHERE s.repo_id = p_repo_id AND s.status = 'ready'
      AND (p_before_seq IS NULL OR s.seq < p_before_seq)
    ORDER BY s.seq DESC
    LIMIT 1;
END;
$$;
