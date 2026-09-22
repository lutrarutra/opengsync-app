-- Creates (or refreshes) the read-only role that postgres_exporter connects as,
-- and that pgbouncer_exporter uses for PgBouncer's console.
--
-- Idempotent, and intended to be: `make prod-monitoring-role` runs it against
-- an existing cluster, because services/db/init.sh only executes when the data
-- directory is first created. Running it twice is a no-op apart from resetting
-- the password.
--
-- Everything it needs comes from the container environment via \getenv, so
-- nothing has to be expanded by Make or passed on the command line - which also
-- keeps the password out of `ps` output and this host's shell history.
--
-- Run it with no -U/-d: as the postgres OS user over the local socket the
-- defaults already resolve to superuser on the `postgres` database.
\getenv monitoring_user POSTGRES_MONITORING_USER
\getenv monitoring_password POSTGRES_MONITORING_PASSWORD
\getenv app_database POSTGRES_DB

-- CREATE only if absent, so re-running cannot fail on a role that already
-- exists. \gexec runs whatever the SELECT returns, and does nothing on no rows.
SELECT format('CREATE ROLE %I LOGIN', :'monitoring_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'monitoring_user')
\gexec

-- Always reset the password: this is what makes rotation a re-run rather than
-- a migration.
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'monitoring_user', :'monitoring_password')
\gexec

-- pg_monitor covers the pg_stat* views. pg_read_all_stats is granted as well
-- because on current releases pg_monitor alone does not expose other sessions'
-- state in pg_stat_activity - the exporter then reports nulls for exactly the
-- columns the dashboard and any "who is holding a connection open" question
-- depend on. Granting both is cheap and avoids a confusing partial failure.
SELECT format('GRANT pg_monitor, pg_read_all_stats TO %I', :'monitoring_user')
\gexec

-- The exporter connects to the application database, so CONNECT is needed on
-- that database specifically. No schema or table grants: statistics views are
-- all it reads.
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'app_database', :'monitoring_user')
\gexec
