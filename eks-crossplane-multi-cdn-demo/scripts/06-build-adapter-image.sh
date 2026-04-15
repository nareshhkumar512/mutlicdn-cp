#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
IMAGE_NAME="${IMAGE_NAME:-multi-cdn-adapter:latest}"
TARGET_PLATFORM="${TARGET_PLATFORM:-linux/amd64}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to build the adapter image." >&2
  exit 1
fi

# Build an amd64 image by default since EKS worker nodes in this demo are amd64.
if docker buildx version >/dev/null 2>&1; then
  docker buildx build --platform "$TARGET_PLATFORM" --load -t "$IMAGE_NAME" -f Dockerfile .
else
  docker build -t "$IMAGE_NAME" -f Dockerfile .
fi
echo "Built adapter image: $IMAGE_NAME"

if [ -n "${REGISTRY:-}" ]; then
  TAG_NAME="${REGISTRY%/}/$(basename "$IMAGE_NAME")"
  docker tag "$IMAGE_NAME" "$TAG_NAME"
  docker push "$TAG_NAME"
  echo "Pushed adapter image to: $TAG_NAME"
fi
