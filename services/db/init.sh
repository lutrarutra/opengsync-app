#!/bin/sh
set -e

# Use the environment variables passed to the container
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER "$POSTGRES_APP_USER" WITH PASSWORD '$POSTGRES_APP_PASSWORD';
    
    GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO "$POSTGRES_APP_USER";
    GRANT USAGE ON SCHEMA public TO "$POSTGRES_APP_USER";
    
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "$POSTGRES_APP_USER";
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "$POSTGRES_APP_USER";
    
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$POSTGRES_APP_USER";
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "$POSTGRES_APP_USER";
EOSQL

# Read-only role for postgres_exporter. This script only runs when the data
# directory is first created, so on a cluster that already exists use
# `make prod-monitoring-role` instead - see docs/setups/monitoring.md.
#
# Guarded so the image still initializes when monitoring is not configured;
# POSTGRES_MONITORING_PASSWORD is required by compose.prod.yaml, but this script
# is also used outside that path.
if [ -n "${POSTGRES_MONITORING_USER:-}" ] && [ -n "${POSTGRES_MONITORING_PASSWORD:-}" ]; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE USER "$POSTGRES_MONITORING_USER" WITH PASSWORD '$POSTGRES_MONITORING_PASSWORD';

        -- Both roles: pg_monitor alone leaves other sessions' state null in
        -- pg_stat_activity on current releases.
        GRANT pg_monitor, pg_read_all_stats TO "$POSTGRES_MONITORING_USER";
        GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO "$POSTGRES_MONITORING_USER";
EOSQL
fi