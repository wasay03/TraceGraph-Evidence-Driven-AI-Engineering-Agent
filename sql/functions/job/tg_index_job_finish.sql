CREATE OR REPLACE FUNCTION tg_index_job_finish(p_id bigint, p_status job_status, p_error text)
RETURNS void
LANGUAGE plpgsql AS $$
#variable_conflict use_column
BEGIN
    IF p_status NOT IN ('succeeded', 'failed') THEN
        RAISE EXCEPTION 'Job can only finish as succeeded or failed, got %', p_status USING ERRCODE = 'TG400';
    END IF;
    UPDATE index_job j SET status = p_status, error = p_error, finished_at = now() WHERE j.id = p_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Index job % not found', p_id USING ERRCODE = 'TG404';
    END IF;
END;
$$;
