CREATE OR REPLACE FUNCTION tg_answer_get(p_handle text)
RETURNS TABLE (
    handle text, repo_id integer, snapshot_seq integer, overlay_id bigint, query_hash text, query_ir jsonb,
    truth text, result jsonb, derivation jsonb, min_tier tier, latency_ms integer, created_at timestamptz
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT a.handle, a.repo_id, a.snapshot_seq, a.overlay_id, a.query_hash, a.query_ir, a.truth,
           a.result, a.derivation, a.min_tier, a.latency_ms, a.created_at
    FROM answer a WHERE a.handle = p_handle;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Answer % not found', p_handle USING ERRCODE = 'TG404';
    END IF;
END;
$$;
