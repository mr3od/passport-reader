#!/usr/bin/env bash
# deploy.sh — called by the GitHub Actions deploy workflow.
#
# Usage (matches workflow expectations):
#   ./deploy.sh build <tag>    build the Docker image
#   ./deploy.sh push  <tag>    no-op (image stays local; no external registry)
#   ./deploy.sh restart [--reset-db]   docker compose up -d
#   ./deploy.sh status         docker compose ps
#   ./deploy.sh logs  [n]      tail last n lines from all services (default 100)

set -euo pipefail

CMD="${1:-}"
TAG="${2:-latest}"
ENV_FILE=".env.production"

resolve_db_path() {
  if [[ -f "$ENV_FILE" ]]; then
    local configured
    configured="$(sed -n 's/^PASSPORT_PLATFORM_DB_PATH=//p' "$ENV_FILE" | tail -n1)"
    if [[ -n "$configured" ]]; then
      printf '%s\n' "$configured"
      return
    fi
  fi
  printf '/data/platform.sqlite3\n'
}

reset_platform_db() {
  local db_path
  db_path="$(resolve_db_path)"
  echo "▶ Resetting platform DB at ${db_path}"
  docker compose run --rm --no-deps api sh -lc \
    "mkdir -p \"$(dirname "$db_path")\" && rm -f \"$db_path\" \"${db_path}-wal\" \"${db_path}-shm\""
}

case "$CMD" in
  build)
    echo "▶ Building passport-reader:${TAG}"
    docker build -t "passport-reader:${TAG}" .
    ;;

  push)
    # No external registry — image is built and used locally.
    echo "▶ push: no-op (local image)"
    ;;

  restart)
    echo "▶ Restarting services via docker compose"
    docker compose down --remove-orphans
    if [[ "$TAG" == "--reset-db" || "${RESET_PLATFORM_DB_ON_RESTART:-0}" == "1" ]]; then
      reset_platform_db
    fi
    docker compose up -d --remove-orphans
    ;;

  status)
    echo "▶ Service status"
    docker compose ps
    ;;

  logs)
    LINES="${TAG:-100}"   # second arg reused as line count when CMD=logs
    echo "▶ Logs (last ${LINES} lines)"
    docker compose logs --tail="${LINES}"
    ;;

  *)
    echo "Usage: $0 {build|push|restart|status|logs} [arg]" >&2
    echo "  restart arg: --reset-db (or set RESET_PLATFORM_DB_ON_RESTART=1)" >&2
    exit 1
    ;;
esac
