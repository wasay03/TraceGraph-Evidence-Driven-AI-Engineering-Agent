CREATE OR REPLACE FUNCTION tg_overlay_get(p_id bigint)
RETURNS TABLE (id bigint, repo_id integer, base_seq integer, change_spec jsonb, ops jsonb, created_at timestamptz)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT o.id, o.repo_id, o.base_seq, o.change_spec,
           coalesce((SELECT jsonb_agg(jsonb_build_object('op', op.op, 'target_id', op.target_id, 'payload', op.payload)
                                      ORDER BY op.position)
                     FROM overlay_op op WHERE op.overlay_id = o.id), '[]'::jsonb),
           o.created_at
    FROM overlay o WHERE o.id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Overlay % not found', p_id USING ERRCODE = 'TG404';
    END IF;
END;
$$;
