-- Version a batch of edges into snapshot p_seq; scope is by owner_file (the file of the
-- edge's domain-side evidence). Same close/insert semantics as tg_node_commit.
-- p_edges: [{id, type_id, src, dst, props, tier, confidence, owner_file}]
CREATE OR REPLACE FUNCTION tg_edge_commit(p_repo_id integer, p_seq integer, p_edges jsonb, p_scope_files text[])
RETURNS TABLE (inserted integer, closed integer)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_closed integer;
    v_inserted integer;
BEGIN
    DROP TABLE IF EXISTS pg_temp.tg_incoming_edge;
    CREATE TEMP TABLE tg_incoming_edge ON COMMIT DROP AS
    SELECT x.id, x.type_id, x.src, x.dst, coalesce(x.props, '{}'::jsonb) AS props, x.tier,
           x.confidence, x.owner_file
    FROM jsonb_to_recordset(coalesce(p_edges, '[]'::jsonb))
         AS x(id bigint, type_id smallint, src bigint, dst bigint, props jsonb, tier tier,
              confidence real, owner_file text);
    CREATE INDEX ON tg_incoming_edge (id);
    ANALYZE tg_incoming_edge;

    UPDATE edge e SET valid_to = p_seq
    WHERE e.repo_id = p_repo_id AND e.valid_to IS NULL
      AND (p_scope_files IS NULL OR e.owner_file = ANY (p_scope_files)
           OR EXISTS (SELECT 1 FROM tg_incoming_edge i WHERE i.id = e.id))
      AND NOT EXISTS (
          SELECT 1 FROM tg_incoming_edge i
          WHERE i.id = e.id AND i.type_id = e.type_id AND i.src = e.src AND i.dst = e.dst
            AND i.props = e.props AND i.tier = e.tier
            AND i.confidence IS NOT DISTINCT FROM e.confidence
            AND i.owner_file IS NOT DISTINCT FROM e.owner_file);
    GET DIAGNOSTICS v_closed = ROW_COUNT;

    INSERT INTO edge (id, repo_id, valid_from, valid_to, type_id, src, dst, props, tier, confidence, owner_file)
    SELECT i.id, p_repo_id, p_seq, NULL, i.type_id, i.src, i.dst, i.props, i.tier, i.confidence, i.owner_file
    FROM tg_incoming_edge i
    WHERE NOT EXISTS (SELECT 1 FROM edge e WHERE e.repo_id = p_repo_id AND e.id = i.id AND e.valid_to IS NULL)
    ON CONFLICT (repo_id, id, valid_from) DO UPDATE
        SET valid_to = NULL, type_id = EXCLUDED.type_id, src = EXCLUDED.src, dst = EXCLUDED.dst,
            props = EXCLUDED.props, tier = EXCLUDED.tier, confidence = EXCLUDED.confidence,
            owner_file = EXCLUDED.owner_file;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    RETURN QUERY SELECT v_inserted, v_closed;
END;
$$;
