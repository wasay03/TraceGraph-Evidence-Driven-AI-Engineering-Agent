CREATE OR REPLACE FUNCTION tg_coverage_hole_list(p_repo_id integer, p_seq integer)
RETURNS TABLE (node_id bigint, kind text, file_path text, line_start integer, line_end integer, detail jsonb)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT h.node_id, h.kind, h.file_path, lower(h.span), upper(h.span) - 1, h.detail
    FROM coverage_hole h
    WHERE h.repo_id = p_repo_id AND h.snapshot_seq = p_seq
    ORDER BY h.file_path, lower(h.span);
END;
$$;
