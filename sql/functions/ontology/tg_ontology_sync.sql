-- Mirror the code registry into the catalog tables. Types are append-only; signatures
-- and property definitions are replaced wholesale. Returns the ontology_version id.
CREATE OR REPLACE FUNCTION tg_ontology_sync(p_semver text, p_catalog jsonb)
RETURNS integer
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_version_id integer;
BEGIN
    IF p_semver IS NULL OR p_catalog IS NULL THEN
        RAISE EXCEPTION 'tg_ontology_sync: semver and catalog are required' USING ERRCODE = 'TG400';
    END IF;

    INSERT INTO node_type AS t (id, name, parent_id, is_abstract, natural_key, tiers, owner)
    SELECT x.id, x.name, NULL, x.is_abstract, x.natural_key, x.tiers, x.owner
    FROM jsonb_to_recordset(p_catalog -> 'node_types')
         AS x(id smallint, name text, parent_id smallint, is_abstract boolean, natural_key text[], tiers text[], owner text)
    ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name, is_abstract = EXCLUDED.is_abstract,
            natural_key = EXCLUDED.natural_key, tiers = EXCLUDED.tiers, owner = EXCLUDED.owner;

    UPDATE node_type t SET parent_id = x.parent_id
    FROM jsonb_to_recordset(p_catalog -> 'node_types') AS x(id smallint, parent_id smallint)
    WHERE t.id = x.id AND t.parent_id IS DISTINCT FROM x.parent_id;

    INSERT INTO edge_type AS t (id, name, cardinality, inverse_name, flags, tiers, evidence_policy)
    SELECT x.id, x.name, x.cardinality, x.inverse_name, coalesce(x.flags, '{}'::jsonb), x.tiers, x.evidence_policy
    FROM jsonb_to_recordset(p_catalog -> 'edge_types')
         AS x(id smallint, name text, cardinality text, inverse_name text, flags jsonb, tiers text[], evidence_policy text)
    ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name, cardinality = EXCLUDED.cardinality, inverse_name = EXCLUDED.inverse_name,
            flags = EXCLUDED.flags, tiers = EXCLUDED.tiers, evidence_policy = EXCLUDED.evidence_policy;

    DELETE FROM edge_signature;
    INSERT INTO edge_signature (edge_type_id, domain_type_id, range_type_id)
    SELECT DISTINCT x.edge_type_id, x.domain_type_id, x.range_type_id
    FROM jsonb_to_recordset(p_catalog -> 'signatures')
         AS x(edge_type_id smallint, domain_type_id smallint, range_type_id smallint);

    DELETE FROM prop_def;
    INSERT INTO prop_def (owner_kind, owner_type_id, name, value_type, required, enum_values)
    SELECT x.owner_kind, x.owner_type_id, x.name, x.value_type, x.required, x.enum_values
    FROM jsonb_to_recordset(p_catalog -> 'props')
         AS x(owner_kind text, owner_type_id smallint, name text, value_type text, required boolean, enum_values text[]);

    INSERT INTO ontology_version AS v (semver) VALUES (p_semver)
    ON CONFLICT (semver) DO UPDATE SET loaded_at = now()
    RETURNING v.id INTO v_version_id;

    RETURN v_version_id;
END;
$$;
