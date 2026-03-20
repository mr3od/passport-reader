#!/usr/bin/env bash
# deploy.sh — called by the GitHub Actions deploy workflow.
#
# Usage (matches workflow expectations):
#   ./deploy.sh build <tag>    build the Docker image
#   ./deploy.sh push  <tag>    no-op (image stays local; no external registry)
#   ./deploy.sh restart        docker compose up -d (pull new image)
#   ./deploy.sh status         docker compose ps
#   ./deploy.sh logs  [n]      tail last n lines from all services (default 100)

set -euo pipefail

CMD="${1:-}"
TAG="${2:-latest}"

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
    exit 1
    ;;
esac
