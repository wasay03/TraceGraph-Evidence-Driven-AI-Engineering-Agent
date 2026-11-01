CREATE OR REPLACE FUNCTION tg_repo_get(p_id integer)
RETURNS TABLE (id integer, url text, name text, default_branch text, created_at timestamptz)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT r.id, r.url, r.name, r.default_branch, r.created_at FROM repo r WHERE r.id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Repository % not found', p_id USING ERRCODE = 'TG404';
    END IF;
END;
$$;
