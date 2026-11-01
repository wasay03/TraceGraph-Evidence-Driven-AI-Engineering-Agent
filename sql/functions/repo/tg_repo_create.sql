CREATE OR REPLACE FUNCTION tg_repo_create(p_url text, p_name text, p_default_branch text)
RETURNS TABLE (id integer, url text, name text, default_branch text, created_at timestamptz)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
BEGIN
    IF EXISTS (SELECT 1 FROM repo r WHERE r.url = p_url) THEN
        RAISE EXCEPTION 'Repository % is already registered', p_url USING ERRCODE = 'TG409';
    END IF;

    RETURN QUERY
    INSERT INTO repo AS r (url, name, default_branch)
    VALUES (p_url, p_name, coalesce(p_default_branch, 'main'))
    RETURNING r.id, r.url, r.name, r.default_branch, r.created_at;
END;
$$;
