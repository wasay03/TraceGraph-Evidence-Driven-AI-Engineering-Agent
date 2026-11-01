-- Fuzzy entity resolution (Resolve operator): trigram similarity plus substring match on
-- natural_key, restricted to p_type_ids when given. Returns ranked candidates.
CREATE OR REPLACE FUNCTION tg_node_search(
    p_repo_id integer, p_seq integer, p_text text, p_type_ids smallint[], p_limit integer
)
RETURNS TABLE (id bigint, type_id smallint, natural_key text, file_path text, line_start integer, score real)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT n.id, n.type_id, n.natural_key, n.file_path, lower(n.span),
           greatest(similarity(n.natural_key, p_text),
                    CASE WHEN strpos(lower(n.natural_key), lower(p_text)) > 0 THEN 0.5 ELSE 0 END)::real AS score
    FROM node n
    WHERE n.repo_id = p_repo_id AND n.valid_from <= p_seq AND (n.valid_to IS NULL OR n.valid_to > p_seq)
      AND (p_type_ids IS NULL OR n.type_id = ANY (p_type_ids))
      AND (n.natural_key % p_text OR strpos(lower(n.natural_key), lower(p_text)) > 0)
    ORDER BY score DESC, length(n.natural_key), n.natural_key
    LIMIT p_limit;
END;
$$;
