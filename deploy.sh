#!/usr/bin/env bash
set -euo pipefail

IMAGE="passport-reader:deploy"
TAR="/tmp/passport-reader-deploy.tar"

echo "==> Building $IMAGE"
docker build -t "$IMAGE" .

echo "==> Saving image"
docker save "$IMAGE" -o "$TAR"

echo "==> Importing into MicroK8s containerd"
sudo /snap/microk8s/current/bin/ctr -n k8s.io images import "$TAR"

echo "==> Verifying image"
sudo /snap/microk8s/current/bin/ctr -n k8s.io images ls | grep "passport-reader:deploy"

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

echo "==> Cleaning up tar"
rm -f "$TAR"

echo "==> Done"
microk8s kubectl get pods -n passport-reader
