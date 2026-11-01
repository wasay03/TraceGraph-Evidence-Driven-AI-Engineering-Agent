CREATE OR REPLACE FUNCTION tg_run_event_list(p_run_id bigint, p_after_seq integer, p_limit integer)
RETURNS TABLE (seq integer, kind text, phase text, payload jsonb, created_at timestamptz)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT e.seq, e.kind, e.phase, e.payload, e.created_at
    FROM agent_run_event e
    WHERE e.run_id = p_run_id AND e.seq > coalesce(p_after_seq, 0)
    ORDER BY e.seq
    LIMIT p_limit;
END;
$$;
