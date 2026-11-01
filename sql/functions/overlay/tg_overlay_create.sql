-- Persist a what-if overlay and its ordered ops.
-- p_ops: [{op, target_id, payload}]
CREATE OR REPLACE FUNCTION tg_overlay_create(p_repo_id integer, p_base_seq integer, p_change_spec jsonb, p_ops jsonb)
RETURNS bigint
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_id bigint;
BEGIN
    INSERT INTO overlay AS o (repo_id, base_seq, change_spec)
    VALUES (p_repo_id, p_base_seq, p_change_spec)
    RETURNING o.id INTO v_id;

    INSERT INTO overlay_op (overlay_id, position, op, target_id, payload)
    SELECT v_id, x.ordinality::integer, (x.value ->> 'op')::overlay_op_kind,
           (x.value ->> 'target_id')::bigint, coalesce(x.value -> 'payload', '{}'::jsonb)
    FROM jsonb_array_elements(coalesce(p_ops, '[]'::jsonb)) WITH ORDINALITY AS x(value, ordinality);

    RETURN v_id;
END;
$$;
