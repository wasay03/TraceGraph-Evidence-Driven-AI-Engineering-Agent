CREATE OR REPLACE FUNCTION tg_health_check()
RETURNS TABLE (status text, server_version text)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY SELECT 'ok'::text, current_setting('server_version');
END;
$$;
