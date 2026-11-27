-- CampusCare uses FastAPI with a server-side PostgreSQL connection.
-- The browser never queries Supabase's Data API directly. Revoke the default
-- table/sequence grants from API roles; the backend's postgres connection
-- retains owner access. RLS remains enabled as defense in depth.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM anon, authenticated, PUBLIC;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated, PUBLIC;

-- Prevent future objects created by the current migration/application role
-- from inheriting API-role grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL PRIVILEGES ON TABLES FROM anon, authenticated, PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon, authenticated, PUBLIC;
