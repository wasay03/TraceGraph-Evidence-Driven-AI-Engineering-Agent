CREATE OR REPLACE FUNCTION tg_answer_insert(
    p_handle text, p_repo_id integer, p_snapshot_seq integer, p_overlay_id bigint, p_query_hash text,
    p_query_ir jsonb, p_truth text, p_result jsonb, p_derivation jsonb, p_min_tier tier, p_latency_ms integer
)
RETURNS bigint
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_id bigint;
BEGIN
    INSERT INTO answer AS a (handle, repo_id, snapshot_seq, overlay_id, query_hash, query_ir, truth,
                             result, derivation, min_tier, latency_ms)
    VALUES (p_handle, p_repo_id, p_snapshot_seq, p_overlay_id, p_query_hash, p_query_ir, p_truth,
            p_result, coalesce(p_derivation, '[]'::jsonb), p_min_tier, p_latency_ms)
    RETURNING a.id INTO v_id;
    RETURN v_id;
END;
$$;
