-- Version a batch of nodes into snapshot p_seq.
-- Current rows in scope (p_scope_files, or everything when NULL) that are absent from the batch
-- or differ from it are closed (valid_to = p_seq); new or changed rows are inserted with valid_from = p_seq.
-- p_nodes: [{id, type_id, natural_key, props, tier, file_path, span_lo, span_hi}]
CREATE OR REPLACE FUNCTION tg_node_commit(p_repo_id integer, p_seq integer, p_nodes jsonb, p_scope_files text[])
RETURNS TABLE (inserted integer, closed integer)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_closed integer;
    v_inserted integer;
BEGIN
    DROP TABLE IF EXISTS pg_temp.tg_incoming_node;
    CREATE TEMP TABLE tg_incoming_node ON COMMIT DROP AS
    SELECT x.id, x.type_id, x.natural_key, coalesce(x.props, '{}'::jsonb) AS props, x.tier, x.file_path,
           CASE WHEN x.span_lo IS NULL THEN NULL ELSE int4range(x.span_lo, x.span_hi, '[]') END AS span
    FROM jsonb_to_recordset(coalesce(p_nodes, '[]'::jsonb))
         AS x(id bigint, type_id smallint, natural_key text, props jsonb, tier tier,
              file_path text, span_lo integer, span_hi integer);
    CREATE INDEX ON tg_incoming_node (id);
    ANALYZE tg_incoming_node;

    UPDATE node n SET valid_to = p_seq
    WHERE n.repo_id = p_repo_id AND n.valid_to IS NULL
      AND (p_scope_files IS NULL OR n.file_path = ANY (p_scope_files)
           OR EXISTS (SELECT 1 FROM tg_incoming_node i WHERE i.id = n.id))
      AND NOT EXISTS (
          SELECT 1 FROM tg_incoming_node i
          WHERE i.id = n.id AND i.type_id = n.type_id AND i.natural_key = n.natural_key
            AND i.props = n.props AND i.tier = n.tier
            AND i.file_path IS NOT DISTINCT FROM n.file_path AND i.span IS NOT DISTINCT FROM n.span);
    GET DIAGNOSTICS v_closed = ROW_COUNT;

    INSERT INTO node (id, repo_id, valid_from, valid_to, type_id, natural_key, props, tier, file_path, span)
    SELECT i.id, p_repo_id, p_seq, NULL, i.type_id, i.natural_key, i.props, i.tier, i.file_path, i.span
    FROM tg_incoming_node i
    WHERE NOT EXISTS (SELECT 1 FROM node n WHERE n.repo_id = p_repo_id AND n.id = i.id AND n.valid_to IS NULL)
    ON CONFLICT (repo_id, id, valid_from) DO UPDATE
        SET valid_to = NULL, type_id = EXCLUDED.type_id, natural_key = EXCLUDED.natural_key,
            props = EXCLUDED.props, tier = EXCLUDED.tier, file_path = EXCLUDED.file_path, span = EXCLUDED.span;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    RETURN QUERY SELECT v_inserted, v_closed;
END;
$$;
