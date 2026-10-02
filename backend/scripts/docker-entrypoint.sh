#!/bin/sh
# Entry point of the backend image.
#   api       upgrade the database schema, then serve the API on port 8000
#   worker    run the background worker (crawls, analysis, AI, reports, imports)
#   cli ...   run an administrative command, for example: cli create-admin --email ...
set -e
case "$1" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    exec python -m app.worker
    ;;
  cli)
    shift
    exec python -m app.cli "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
