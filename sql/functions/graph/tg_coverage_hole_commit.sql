-- Write the coverage map for snapshot p_seq. For an incremental snapshot, holes of files
-- outside p_scope_files are carried over from p_prev_seq.
-- p_holes: [{node_id, kind, file_path, span_lo, span_hi, detail}]
CREATE OR REPLACE FUNCTION tg_coverage_hole_commit(
    p_repo_id integer, p_seq integer, p_holes jsonb, p_scope_files text[], p_prev_seq integer
)
RETURNS integer
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_count integer;
BEGIN
    DELETE FROM coverage_hole h WHERE h.repo_id = p_repo_id AND h.snapshot_seq = p_seq;

    IF p_scope_files IS NOT NULL AND p_prev_seq IS NOT NULL THEN
        INSERT INTO coverage_hole (repo_id, snapshot_seq, node_id, kind, file_path, span, detail)
        SELECT h.repo_id, p_seq, h.node_id, h.kind, h.file_path, h.span, h.detail
        FROM coverage_hole h
        WHERE h.repo_id = p_repo_id AND h.snapshot_seq = p_prev_seq
          AND (h.file_path IS NULL OR NOT (h.file_path = ANY (p_scope_files)));
    END IF;

    INSERT INTO coverage_hole (repo_id, snapshot_seq, node_id, kind, file_path, span, detail)
    SELECT p_repo_id, p_seq, x.node_id, x.kind, x.file_path,
           CASE WHEN x.span_lo IS NULL THEN NULL ELSE int4range(x.span_lo, x.span_hi, '[]') END,
           coalesce(x.detail, '{}'::jsonb)
    FROM jsonb_to_recordset(coalesce(p_holes, '[]'::jsonb))
         AS x(node_id bigint, kind text, file_path text, span_lo integer, span_hi integer, detail jsonb);

    SELECT count(*) INTO v_count FROM coverage_hole h WHERE h.repo_id = p_repo_id AND h.snapshot_seq = p_seq;
    RETURN v_count;
END;
$$;
