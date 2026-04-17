#!/bin/sh
set -euo pipefail

if command -v terraform >/dev/null 2>&1; then
  echo "Terraform already installed: $(terraform version | head -n 1)"
  exec "$@"
fi

TERRAFORM_VERSION="${TERRAFORM_VERSION:-1.7.8}"
TERRAFORM_URL="https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip"
TMP_DIR="$(mktemp -d)"
ZIP_FILE="$TMP_DIR/terraform.zip"

echo "Downloading Terraform ${TERRAFORM_VERSION}..."
curl -fsSL -o "$ZIP_FILE" "$TERRAFORM_URL"
unzip -q "$ZIP_FILE" -d "$TMP_DIR"
install -m 0755 "$TMP_DIR/terraform" /usr/local/bin/terraform
rm -rf "$TMP_DIR"

echo "Terraform installed to /usr/local/bin/terraform"
exec "$@"
