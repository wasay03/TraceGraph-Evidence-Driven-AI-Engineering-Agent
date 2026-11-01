-- Most recently loaded ontology version, or no row if the catalog was never synced.
CREATE OR REPLACE FUNCTION tg_ontology_get_current()
RETURNS TABLE (id integer, semver text, loaded_at timestamptz)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT v.id, v.semver, v.loaded_at
    FROM ontology_version v
    ORDER BY v.loaded_at DESC, v.id DESC
    LIMIT 1;
END;
$$;
