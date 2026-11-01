-- All nodes valid at snapshot p_seq; feeds the in-memory graph snapshot.
CREATE OR REPLACE FUNCTION tg_node_list_at(p_repo_id integer, p_seq integer)
RETURNS TABLE (
    id bigint, type_id smallint, natural_key text, props jsonb, tier tier,
    file_path text, line_start integer, line_end integer
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT n.id, n.type_id, n.natural_key, n.props, n.tier, n.file_path,
           lower(n.span), upper(n.span) - 1
    FROM node n
    WHERE n.repo_id = p_repo_id AND n.valid_from <= p_seq AND (n.valid_to IS NULL OR n.valid_to > p_seq);
END;
$$;
