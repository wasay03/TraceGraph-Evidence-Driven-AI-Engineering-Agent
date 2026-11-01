-- All edges valid at snapshot p_seq; feeds the in-memory graph snapshot.
CREATE OR REPLACE FUNCTION tg_edge_list_at(p_repo_id integer, p_seq integer)
RETURNS TABLE (id bigint, type_id smallint, src bigint, dst bigint, props jsonb, tier tier, confidence real)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT e.id, e.type_id, e.src, e.dst, e.props, e.tier, e.confidence
    FROM edge e
    WHERE e.repo_id = p_repo_id AND e.valid_from <= p_seq AND (e.valid_to IS NULL OR e.valid_to > p_seq);
END;
$$;
