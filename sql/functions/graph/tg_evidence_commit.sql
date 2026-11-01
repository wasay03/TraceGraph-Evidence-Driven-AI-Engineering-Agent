-- Store evidence rows (content-addressed, deduplicated) and replace the evidence links of
-- current edges in scope with p_links.
-- p_evidence: [{id, extractor, extractor_version, method, file_path, span_lo, span_hi,
--               snippet_hash, commit_sha, confidence, rationale}]
-- p_links:    [{edge_id, evidence_id}]
CREATE OR REPLACE FUNCTION tg_evidence_commit(p_repo_id integer, p_evidence jsonb, p_links jsonb, p_scope_files text[])
RETURNS TABLE (evidence_inserted integer, links_inserted integer)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_evidence integer;
    v_links integer;
BEGIN
    INSERT INTO evidence (id, repo_id, extractor, extractor_version, method, file_path, span,
                          snippet_hash, commit_sha, confidence, rationale)
    SELECT x.id, p_repo_id, x.extractor, x.extractor_version, x.method, x.file_path,
           CASE WHEN x.span_lo IS NULL THEN NULL ELSE int4range(x.span_lo, x.span_hi, '[]') END,
           x.snippet_hash, x.commit_sha, x.confidence, x.rationale
    FROM jsonb_to_recordset(coalesce(p_evidence, '[]'::jsonb))
         AS x(id bigint, extractor text, extractor_version text, method text, file_path text,
              span_lo integer, span_hi integer, snippet_hash text, commit_sha text,
              confidence real, rationale text)
    ON CONFLICT (id) DO NOTHING;
    GET DIAGNOSTICS v_evidence = ROW_COUNT;

    DELETE FROM edge_evidence ee
    WHERE ee.repo_id = p_repo_id
      AND (ee.edge_id IN (SELECT (l ->> 'edge_id')::bigint FROM jsonb_array_elements(coalesce(p_links, '[]')) l)
           OR ee.edge_id IN (SELECT e.id FROM edge e
                             WHERE e.repo_id = p_repo_id AND e.valid_to IS NULL
                               AND (p_scope_files IS NULL OR e.owner_file = ANY (p_scope_files))));

    INSERT INTO edge_evidence (repo_id, edge_id, evidence_id)
    SELECT DISTINCT p_repo_id, x.edge_id, x.evidence_id
    FROM jsonb_to_recordset(coalesce(p_links, '[]'::jsonb)) AS x(edge_id bigint, evidence_id bigint)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_links = ROW_COUNT;

    RETURN QUERY SELECT v_evidence, v_links;
END;
$$;
