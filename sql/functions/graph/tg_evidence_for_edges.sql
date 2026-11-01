-- Evidence currently linked to the given edges, used to expand derivations to source lines.
CREATE OR REPLACE FUNCTION tg_evidence_for_edges(p_repo_id integer, p_edge_ids bigint[])
RETURNS TABLE (
    edge_id bigint, evidence_id bigint, extractor text, extractor_version text, method text,
    file_path text, line_start integer, line_end integer, confidence real, rationale text
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT ee.edge_id, ev.id, ev.extractor, ev.extractor_version, ev.method, ev.file_path,
           lower(ev.span), upper(ev.span) - 1, ev.confidence, ev.rationale
    FROM edge_evidence ee
    JOIN evidence ev ON ev.id = ee.evidence_id
    WHERE ee.repo_id = p_repo_id AND ee.edge_id = ANY (p_edge_ids)
    ORDER BY ee.edge_id, ev.file_path, lower(ev.span);
END;
$$;
