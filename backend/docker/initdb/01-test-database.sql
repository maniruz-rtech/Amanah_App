-- Creates the database used by the pytest suite (tests/conftest.py refuses to
-- run against any database whose name does not end in "_test").
-- Runs once, on first initialisation of the data volume.
SELECT 'CREATE DATABASE amanah_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'amanah_test')\gexec
\connect amanah_test
CREATE EXTENSION IF NOT EXISTS postgis;
