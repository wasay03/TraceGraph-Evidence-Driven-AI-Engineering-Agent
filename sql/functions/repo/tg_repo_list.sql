CREATE OR REPLACE FUNCTION tg_repo_list(p_limit integer, p_offset integer)
RETURNS TABLE (id integer, url text, name text, default_branch text, created_at timestamptz, total bigint)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT r.id, r.url, r.name, r.default_branch, r.created_at, count(*) OVER ()
    FROM repo r
    ORDER BY r.id
    LIMIT p_limit OFFSET p_offset;
END;
$$;
