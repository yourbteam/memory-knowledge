#!/usr/bin/env bash
#
# Incrementally redeploy memory-knowledge to its existing Azure Web App via
# Azure Container Registry remote builds.
#
# Adapted from mcp-agents-workflow/infra/azure-push.sh. The build runs from a
# clean temp context containing ONLY what the Dockerfile needs — .env and other
# secrets are never sent to the registry.
#
# Prerequisites:
#   - Azure CLI (`az`) installed and logged in
#   - Existing resource group, ACR, App Service plan, and Web App
#
# Usage:
#   ./infra/azure-push.sh
#   ./infra/azure-push.sh --tag release-2026-06-13
#   ./infra/azure-push.sh --dry-run

set -euo pipefail

RG="${AZURE_RG:-workflow-orch-rg}"
ACR_NAME="${AZURE_ACR:-workfloworchreg}"
APP_NAME="${AZURE_APP_NAME:-memory-knowledge}"
IMAGE_REPO="${AZURE_IMAGE_REPO:-memory-knowledge}"
CUSTOM_TAG="${IMAGE_TAG:-}"
HEALTH_PATH="${AZURE_HEALTH_PATH:-/health}"
HEALTH_TIMEOUT_SECONDS="${AZURE_HEALTH_TIMEOUT_SECONDS:-180}"
HEALTH_INTERVAL_SECONDS="${AZURE_HEALTH_INTERVAL_SECONDS:-5}"
SKIP_HEALTH_CHECK=false
DRY_RUN=false

usage() {
    cat <<'EOF'
Usage: ./infra/azure-push.sh [options]

Build the current repo through Azure Container Registry (from a clean,
secret-free context), update the existing Azure Web App container image,
restart the app, and verify health.

Options:
  --resource-group NAME     Azure resource group (default: workflow-orch-rg)
  --acr NAME                Azure Container Registry name (default: workfloworchreg)
  --app NAME                Azure Web App name (default: memory-knowledge)
  --image-repo NAME         Image repository name inside ACR (default: memory-knowledge)
  --tag TAG                 Additional custom image tag
  --health-path PATH        Health endpoint path (default: /health)
  --health-timeout SEC      Total health-check timeout in seconds (default: 180)
  --health-interval SEC     Health-check retry interval in seconds (default: 5)
  --skip-health-check       Skip post-deploy health verification
  --dry-run                 Print commands without executing them
  --help                    Show this help text

Environment variable defaults: AZURE_RG, AZURE_ACR, AZURE_APP_NAME,
AZURE_IMAGE_REPO, IMAGE_TAG, AZURE_HEALTH_PATH, AZURE_HEALTH_TIMEOUT_SECONDS,
AZURE_HEALTH_INTERVAL_SECONDS
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --resource-group) RG="$2"; shift 2 ;;
        --acr) ACR_NAME="$2"; shift 2 ;;
        --app) APP_NAME="$2"; shift 2 ;;
        --image-repo) IMAGE_REPO="$2"; shift 2 ;;
        --tag) CUSTOM_TAG="$2"; shift 2 ;;
        --health-path) HEALTH_PATH="$2"; shift 2 ;;
        --health-timeout) HEALTH_TIMEOUT_SECONDS="$2"; shift 2 ;;
        --health-interval) HEALTH_INTERVAL_SECONDS="$2"; shift 2 ;;
        --skip-health-check) SKIP_HEALTH_CHECK=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
    esac
done

run_cmd() {
    if [[ "$DRY_RUN" == true ]]; then
        printf '+'; printf ' %q' "$@"; printf '\n'
        return 0
    fi
    "$@"
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || { echo "ERROR: Required command not found: $1" >&2; exit 1; }
}

require_cmd az
require_cmd git
require_cmd curl

git rev-parse --show-toplevel >/dev/null 2>&1 || { echo "ERROR: Must run inside the git repository." >&2; exit 1; }
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

GIT_SHA="$(git rev-parse --short HEAD)"
SHA_TAG="sha-${GIT_SHA}"
MAIN_TAG="main"
ACR_URL="${ACR_NAME}.azurecr.io"
PRIMARY_IMAGE="${ACR_URL}/${IMAGE_REPO}:${SHA_TAG}"
BUILD_CONTEXT=""

cleanup() {
    if [[ -n "${BUILD_CONTEXT}" && "${BUILD_CONTEXT}" != "." && -d "${BUILD_CONTEXT}" ]]; then
        rm -rf "${BUILD_CONTEXT}"
    fi
}
trap cleanup EXIT

echo "==> Incremental Azure redeploy for memory-knowledge"
echo "    Resource Group: $RG"
echo "    ACR:            $ACR_NAME"
echo "    Web App:        $APP_NAME"
echo "    Image Repo:     $IMAGE_REPO"
echo "    SHA Tag:        $SHA_TAG"
[[ -n "$CUSTOM_TAG" ]] && echo "    Custom Tag:     $CUSTOM_TAG"
[[ "$DRY_RUN" == true ]] && echo "    Mode:           dry-run"

echo "==> Verifying Azure resources exist..."
run_cmd az group show --name "$RG" --output none
run_cmd az acr show --resource-group "$RG" --name "$ACR_NAME" --output none
run_cmd az webapp show --resource-group "$RG" --name "$APP_NAME" --output none

APP_HOSTNAME_CMD=(az webapp show --resource-group "$RG" --name "$APP_NAME" --query defaultHostName --output tsv)
if [[ "$DRY_RUN" == true ]]; then
    run_cmd "${APP_HOSTNAME_CMD[@]}"
    APP_HOSTNAME="<default-hostname>"
else
    APP_HOSTNAME="$("${APP_HOSTNAME_CMD[@]}")"
    [[ -n "$APP_HOSTNAME" ]] || { echo "ERROR: Could not resolve Web App default hostname." >&2; exit 1; }
fi
APP_URL="https://${APP_HOSTNAME}"
HEALTH_URL="${APP_URL}${HEALTH_PATH}"
echo "    App URL:        $APP_URL"
echo "    Health URL:     $HEALTH_URL"

# Clean, secret-free build context: only what the Dockerfile COPYs.
echo "==> Assembling clean build context..."
if [[ "$DRY_RUN" == true ]]; then
    BUILD_CONTEXT="."
else
    BUILD_CONTEXT="$(mktemp -d "${TMPDIR:-/tmp}/memory-knowledge-acr-build.XXXXXX")"
    cp Dockerfile pyproject.toml alembic.ini "${BUILD_CONTEXT}/"
    cp -R src "${BUILD_CONTEXT}/src"
    cp -R migrations "${BUILD_CONTEXT}/migrations"
    cp -R docker "${BUILD_CONTEXT}/docker"
fi

echo "==> Building and pushing image via ACR..."
ACR_BUILD_CMD=(
    az acr build
    --resource-group "$RG"
    --registry "$ACR_NAME"
    --image "${IMAGE_REPO}:${MAIN_TAG}"
    --image "${IMAGE_REPO}:${SHA_TAG}"
    --file Dockerfile
    "$BUILD_CONTEXT"
)
[[ -n "$CUSTOM_TAG" ]] && ACR_BUILD_CMD+=(--image "${IMAGE_REPO}:${CUSTOM_TAG}")
run_cmd "${ACR_BUILD_CMD[@]}"

echo "==> Fetching registry credentials..."
ACR_PASSWORD_CMD=(az acr credential show --name "$ACR_NAME" --query 'passwords[0].value' --output tsv)
if [[ "$DRY_RUN" == true ]]; then
    run_cmd "${ACR_PASSWORD_CMD[@]}"
    ACR_PASSWORD="<acr-password>"
else
    ACR_PASSWORD="$("${ACR_PASSWORD_CMD[@]}")"
fi

echo "==> Updating Web App container image..."
run_cmd az webapp config container set \
    --resource-group "$RG" \
    --name "$APP_NAME" \
    --container-image-name "$PRIMARY_IMAGE" \
    --container-registry-url "https://${ACR_URL}" \
    --container-registry-user "$ACR_NAME" \
    --container-registry-password "$ACR_PASSWORD" \
    --output none

echo "==> Restarting Web App..."
run_cmd az webapp restart --resource-group "$RG" --name "$APP_NAME" --output none

if [[ "$SKIP_HEALTH_CHECK" == true ]]; then
    echo "==> Skipping health check."
    exit 0
fi

echo "==> Waiting for health check..."
if [[ "$DRY_RUN" == true ]]; then
    run_cmd curl --fail --silent --show-error "$HEALTH_URL"
    exit 0
fi

deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
while true; do
    if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null; then
        echo "==> Health check passed."
        echo "    App URL: $APP_URL"
        echo "    Image:   $PRIMARY_IMAGE"
        exit 0
    fi
    if (( SECONDS >= deadline )); then
        echo "ERROR: Health check did not pass within ${HEALTH_TIMEOUT_SECONDS}s." >&2
        echo "       URL: $HEALTH_URL" >&2
        exit 1
    fi
    sleep "$HEALTH_INTERVAL_SECONDS"
done
