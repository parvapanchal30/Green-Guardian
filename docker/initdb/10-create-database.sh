#!/bin/sh
# Runs once when the PostGIS container initialises an empty data directory.
# The application database is created from template0 (NOT the image's default template, which already installs PostGIS
# into `public`): the first migration installs PostGIS into the dedicated `extensions` schema, exactly as on hosted
# providers (docs/DATABASE_SETUP.md).
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -c "CREATE DATABASE greenguardian TEMPLATE template0"
