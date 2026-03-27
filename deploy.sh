#!/usr/bin/env bash
set -euo pipefail

REGISTRY="localhost:32000"
IMAGE="$REGISTRY/passport-reader:latest"

echo "==> Building $IMAGE"
docker build -t "$IMAGE" .

echo "==> Pushing to MicroK8s registry"
docker push "$IMAGE"

echo "==> Applying k8s manifests"
microk8s kubectl apply -f k8s/namespace.yaml
microk8s kubectl apply -f k8s/pvc.yaml
microk8s kubectl apply -f k8s/api-service.yaml
microk8s kubectl apply -f k8s/api-deployment.yaml
microk8s kubectl apply -f k8s/telegram-deployment.yaml

echo "==> Rolling restart"
microk8s kubectl -n passport-reader rollout restart deploy/passport-api deploy/passport-telegram

echo "==> Waiting for rollout"
microk8s kubectl -n passport-reader rollout status deploy/passport-api
microk8s kubectl -n passport-reader rollout status deploy/passport-telegram

echo "==> Done"
microk8s kubectl get pods -n passport-reader
