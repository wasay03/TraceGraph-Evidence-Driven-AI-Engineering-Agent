-- Append one audit event; seq is per run and gap-free (the run row lock serialises appenders).
CREATE OR REPLACE FUNCTION tg_run_event_append(p_run_id bigint, p_kind text, p_phase text, p_payload jsonb)
RETURNS integer
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_seq integer;
BEGIN
    PERFORM 1 FROM agent_run r WHERE r.id = p_run_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Run % not found', p_run_id USING ERRCODE = 'TG404';
    END IF;
    SELECT coalesce(max(e.seq), 0) + 1 INTO v_seq FROM agent_run_event e WHERE e.run_id = p_run_id;
    INSERT INTO agent_run_event (run_id, seq, kind, phase, payload)
    VALUES (p_run_id, v_seq, p_kind, p_phase, coalesce(p_payload, '{}'::jsonb));
    RETURN v_seq;
END;
$$;
