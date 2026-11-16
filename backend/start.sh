#!/usr/bin/env bash
# Single-container entrypoint: API (uvicorn) + Celery worker with embedded beat.
# Used where one service must run both (Render Starter, 512 MB). Memory budget:
#  - one uvicorn process
#  - one Celery process with a thread pool (no forked children); LLM calls are I/O-bound
#  - the beat scheduler (stale-job reaper, refresh-token cleanup) as a thread inside the
#    worker process (BEAT_IN_THREAD=1) instead of Celery's forked beat process
# If either main process exits, the other is stopped and the container exits non-zero,
# so the platform restarts it instead of leaving the API up with a dead worker.
set -euo pipefail

PORT="${PORT:-8000}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-2}"

BEAT_IN_THREAD=1 celery -A app.worker worker \
    --loglevel=INFO \
    --pool=threads \
    --concurrency="${CELERY_CONCURRENCY}" &
celery_pid=$!

uvicorn app.main:create_app --factory --host 0.0.0.0 --port "${PORT}" --no-proxy-headers &
api_pid=$!

shutdown() {
    kill -TERM "${api_pid}" "${celery_pid}" 2>/dev/null || true
    wait "${api_pid}" "${celery_pid}" 2>/dev/null || true
}
trap 'shutdown; exit 0' TERM INT

# Returns as soon as either process exits.
set +e
wait -n "${api_pid}" "${celery_pid}"
status=$?
set -e
echo "start.sh: a main process exited (status ${status}); stopping the container" >&2
shutdown
exit $(( status == 0 ? 1 : status ))
