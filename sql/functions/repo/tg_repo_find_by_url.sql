-- Repository registered under p_url, or no row.
CREATE OR REPLACE FUNCTION tg_repo_find_by_url(p_url text)
RETURNS TABLE (id integer, url text, name text, default_branch text, created_at timestamptz)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT r.id, r.url, r.name, r.default_branch, r.created_at FROM repo r WHERE r.url = p_url;
END;
$$;
