#!/usr/bin/env bash
set -euo pipefail

REGISTRY="registry.mohammed-alkebsi.dev/mohammed"
SHA=$(git rev-parse --short HEAD)
IMAGE="${REGISTRY}/passport-reader:${SHA}"
LATEST="${REGISTRY}/passport-reader:latest"

echo "==> Building ${IMAGE}"
docker build -t "${IMAGE}" -t "${LATEST}" .

echo "==> Pushing to registry"
docker push "${IMAGE}"
docker push "${LATEST}"

echo "==> Deploying to MicroK8s"
microk8s kubectl -n passport-reader set image deploy/passport-api passport-api="${IMAGE}"
microk8s kubectl -n passport-reader set image deploy/passport-telegram passport-telegram="${IMAGE}"

echo "==> Waiting for rollout"
microk8s kubectl -n passport-reader rollout status deploy/passport-api --timeout=120s
microk8s kubectl -n passport-reader rollout status deploy/passport-telegram --timeout=120s

echo "==> Done"
microk8s kubectl get pods -n passport-reader
