-- Nodes of the given types valid at snapshot p_seq (e.g. Module rows for incremental dirty-set detection).
CREATE OR REPLACE FUNCTION tg_node_list_by_type_at(p_repo_id integer, p_seq integer, p_type_ids smallint[])
RETURNS TABLE (id bigint, type_id smallint, natural_key text, props jsonb, file_path text)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT n.id, n.type_id, n.natural_key, n.props, n.file_path
    FROM node n
    WHERE n.repo_id = p_repo_id AND n.type_id = ANY (p_type_ids)
      AND n.valid_from <= p_seq AND (n.valid_to IS NULL OR n.valid_to > p_seq);
END;
$$;
