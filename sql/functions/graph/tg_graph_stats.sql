-- Counts of nodes and edges per type, and coverage holes per kind, at snapshot p_seq.
CREATE OR REPLACE FUNCTION tg_graph_stats(p_repo_id integer, p_seq integer)
RETURNS TABLE (kind text, type_name text, total bigint)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT 'node'::text, t.name, count(*)
    FROM node n JOIN node_type t ON t.id = n.type_id
    WHERE n.repo_id = p_repo_id AND n.valid_from <= p_seq AND (n.valid_to IS NULL OR n.valid_to > p_seq)
    GROUP BY t.name
    UNION ALL
    SELECT 'edge'::text, t.name, count(*)
    FROM edge e JOIN edge_type t ON t.id = e.type_id
    WHERE e.repo_id = p_repo_id AND e.valid_from <= p_seq AND (e.valid_to IS NULL OR e.valid_to > p_seq)
    GROUP BY t.name
    UNION ALL
    SELECT 'coverage_hole'::text, h.kind, count(*)
    FROM coverage_hole h
    WHERE h.repo_id = p_repo_id AND h.snapshot_seq = p_seq
    GROUP BY h.kind
    ORDER BY 1, 2;
END;
$$;
