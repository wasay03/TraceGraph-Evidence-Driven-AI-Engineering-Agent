-- Allocate the next snapshot seq for a repo. The repo row lock serialises concurrent creates.
CREATE OR REPLACE FUNCTION tg_snapshot_create(p_repo_id integer, p_commit_sha text, p_ontology_version_id integer)
RETURNS TABLE (
    id integer, repo_id integer, seq integer, commit_sha text, ontology_version_id integer,
    status snapshot_status, extractor_versions jsonb, stats jsonb, error text,
    created_at timestamptz, finished_at timestamptz
)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_seq integer;
BEGIN
    PERFORM 1 FROM repo r WHERE r.id = p_repo_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Repository % not found', p_repo_id USING ERRCODE = 'TG404';
    END IF;

    SELECT coalesce(max(s.seq), 0) + 1 INTO v_seq FROM snapshot s WHERE s.repo_id = p_repo_id;

    RETURN QUERY
    INSERT INTO snapshot AS s (repo_id, seq, commit_sha, ontology_version_id)
    VALUES (p_repo_id, v_seq, p_commit_sha, p_ontology_version_id)
    RETURNING s.id, s.repo_id, s.seq, s.commit_sha, s.ontology_version_id, s.status,
              s.extractor_versions, s.stats, s.error, s.created_at, s.finished_at;
END;
$$;
