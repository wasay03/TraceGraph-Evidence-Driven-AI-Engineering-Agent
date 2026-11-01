-- CI validation query (PRD section 6): returns one row per violation in snapshot p_seq.
--   dangling_endpoint     edge whose src or dst node does not exist at p_seq
--   signature_violation   (src type, dst type) not permitted by edge_signature, honouring the type hierarchy
--   cardinality_violation more than one edge on the "1" side of 1:1, 1:N or N:1
CREATE OR REPLACE FUNCTION tg_graph_validate(p_repo_id integer, p_seq integer)
RETURNS TABLE (violation text, edge_id bigint, edge_type text, src bigint, dst bigint, detail text)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    WITH RECURSIVE ancestors(type_id, ancestor_id) AS (
        SELECT t.id, t.id FROM node_type t
        UNION
        SELECT a.type_id, t.parent_id FROM ancestors a JOIN node_type t ON t.id = a.ancestor_id
        WHERE t.parent_id IS NOT NULL
    ),
    nodes_at AS (
        SELECT n.id, n.type_id FROM node n
        WHERE n.repo_id = p_repo_id AND n.valid_from <= p_seq AND (n.valid_to IS NULL OR n.valid_to > p_seq)
    ),
    edges_at AS (
        SELECT e.id, e.type_id, e.src, e.dst FROM edge e
        WHERE e.repo_id = p_repo_id AND e.valid_from <= p_seq AND (e.valid_to IS NULL OR e.valid_to > p_seq)
    ),
    typed AS (
        SELECT e.id, e.type_id, e.src, e.dst, s.type_id AS src_type, d.type_id AS dst_type
        FROM edges_at e LEFT JOIN nodes_at s ON s.id = e.src LEFT JOIN nodes_at d ON d.id = e.dst
    )
    SELECT 'dangling_endpoint'::text, t.id, et.name, t.src, t.dst,
           CASE WHEN t.src_type IS NULL THEN 'missing src' ELSE 'missing dst' END
    FROM typed t JOIN edge_type et ON et.id = t.type_id
    WHERE t.src_type IS NULL OR t.dst_type IS NULL
    UNION ALL
    SELECT 'signature_violation', t.id, et.name, t.src, t.dst,
           format('%s -> %s', sn.name, dn.name)
    FROM typed t
    JOIN edge_type et ON et.id = t.type_id
    JOIN node_type sn ON sn.id = t.src_type
    JOIN node_type dn ON dn.id = t.dst_type
    WHERE NOT EXISTS (
        SELECT 1 FROM edge_signature sig
        JOIN ancestors sa ON sa.type_id = t.src_type AND sa.ancestor_id = sig.domain_type_id
        JOIN ancestors da ON da.type_id = t.dst_type AND da.ancestor_id = sig.range_type_id
        WHERE sig.edge_type_id = t.type_id)
    UNION ALL
    SELECT 'cardinality_violation', NULL::bigint, et.name, c.src, NULL::bigint,
           format('%s outgoing edges, cardinality %s', c.n, et.cardinality)
    FROM (SELECT e.type_id, e.src, count(*) AS n FROM edges_at e GROUP BY e.type_id, e.src HAVING count(*) > 1) c
    JOIN edge_type et ON et.id = c.type_id AND et.cardinality IN ('1:1', 'N:1')
    UNION ALL
    SELECT 'cardinality_violation', NULL::bigint, et.name, NULL::bigint, c.dst,
           format('%s incoming edges, cardinality %s', c.n, et.cardinality)
    FROM (SELECT e.type_id, e.dst, count(*) AS n FROM edges_at e GROUP BY e.type_id, e.dst HAVING count(*) > 1) c
    JOIN edge_type et ON et.id = c.type_id AND et.cardinality IN ('1:1', '1:N');
END;
$$;
