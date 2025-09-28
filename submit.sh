#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

usage() {
  echo "Usage: ${BASH_SOURCE[0]} [dev|prod]" >&2
  exit 1
}

ORIGINAL_ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
restore_original_account() {
  if [[ -n "${ORIGINAL_ACCOUNT}" ]]; then
    gcloud config set account "${ORIGINAL_ACCOUNT}" >/dev/null 2>&1 || true
  fi
}
trap restore_original_account EXIT

resolve_path() {
  local path="${1:-}"
  if [[ -z "${path}" ]]; then
    return 1
  fi
  if [[ "${path}" == /* ]]; then
    printf '%s\n' "${path}"
  else
    printf '%s/%s\n' "${SCRIPT_DIR}" "${path}"
  fi
}

ENVIRONMENT=${1:-prod}
case "${ENVIRONMENT}" in
  dev|prod) ;;
  -h|--help) usage ;;
  *)
    echo "Unknown environment '${ENVIRONMENT}'." >&2
    usage
    ;;
esac

ENVIRONMENT_LOWER=${ENVIRONMENT,,}
ENV_FILE="${SCRIPT_DIR}/env.${ENVIRONMENT_LOWER}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file '${ENV_FILE}' not found." >&2
  exit 1
fi

mapfile -t ENV_FILE_VARS < <(python3 - "$ENV_FILE" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    sys.exit(1)

pattern = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)')
values = []

for raw_line in path.read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#'):
        continue
    match = pattern.match(line)
    if not match:
        continue
    key, value = match.groups()
    value = value.strip()
    if value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) >= 2:
        value = value[1:-1]
    values.append(f"{key}={value}")

print('\n'.join(values))
PY
)

if ((${#ENV_FILE_VARS[@]})); then
  for assignment in "${ENV_FILE_VARS[@]}"; do
    [[ -z "${assignment}" ]] && continue
    export "${assignment}"
  done
fi

if [[ -z "${PROJECT_ID:-}" && -n "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
  PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"
fi
export PROJECT_ID=${PROJECT_ID:-doc2json-dev}
export REGION=${REGION:-europe-west1}
export REPO_NAME=${REPO_NAME:-webapp}
export SERVICE_NAME=${SERVICE_NAME:-api-builder-webapp}
echo "Deploying '${SERVICE_NAME}' using '${ENVIRONMENT_LOWER}' environment." >&2
export IMAGE_TAG=${IMAGE_TAG:-latest}
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:${IMAGE_TAG}"
export CACHE_REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/cache"

export CACHE_IMAGE_NAME=${CACHE_IMAGE_NAME:-webapp-cache}
export CACHE_IMAGE_TAG=${CACHE_IMAGE_TAG:-latest}
export CACHE_IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${CACHE_IMAGE_NAME}:${CACHE_IMAGE_TAG}"
export REBUILD_CACHE_IMAGE=${REBUILD_CACHE_IMAGE:-0}

SECRET_PROJECT_ID=${SECRET_PROJECT_ID:-${PROJECT_ID}}
SECRET_VERSION=${SECRET_VERSION:-latest}
SECRET_NAMES=${SECRET_NAMES:-"GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET STRIPE_SECRET_KEY STRIPE_PRICE_ID_STARTER STRIPE_PRICE_ID_MEDIUM STRIPE_PRICE_ID_PRO STRIPE_WEBHOOK_SECRET GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT INSTANCE_CONNECTION_NAME DB_NAME DB_USER DB_PASS CREDITS_PER_CENT ENV SESSION_SECRET"}
USE_SERVICE_ACCOUNT=${GCLOUD_USE_SERVICE_ACCOUNT:-0}

# Configure project and required APIs
OWNER_ACCOUNT=${GCLOUD_OWNER_ACCOUNT:-}
if [[ -z "${OWNER_ACCOUNT}" && -n "${ORIGINAL_ACCOUNT}" && "${ORIGINAL_ACCOUNT}" != *"gserviceaccount.com" ]]; then
  OWNER_ACCOUNT="${ORIGINAL_ACCOUNT}"
fi

if [[ -n "${OWNER_ACCOUNT}" ]]; then
  if [[ "${OWNER_ACCOUNT}" != "${ORIGINAL_ACCOUNT}" ]]; then
    gcloud config set account "${OWNER_ACCOUNT}"
  fi
  echo "Using '${OWNER_ACCOUNT}' to enable required services." >&2
else
  echo "No owner account available to enable services. Set GCLOUD_OWNER_ACCOUNT or ensure current account can manage service usage." >&2
fi

gcloud config set project "${PROJECT_ID}"

gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  --project "${PROJECT_ID}"

if [[ "${USE_SERVICE_ACCOUNT}" == "1" ]]; then
  SERVICE_ACCOUNT_KEY_FILE=${GCLOUD_SERVICE_ACCOUNT_KEY_FILE:-${GOOGLE_APPLICATION_CREDENTIALS:-}}
  if [[ -n "${SERVICE_ACCOUNT_KEY_FILE}" ]]; then
    if KEY_PATH=$(resolve_path "${SERVICE_ACCOUNT_KEY_FILE}"); then
      if [[ -f "${KEY_PATH}" ]]; then
        gcloud auth activate-service-account --key-file "${KEY_PATH}" --project "${PROJECT_ID}"
      else
        echo "Service account key file '${SERVICE_ACCOUNT_KEY_FILE}' not found (resolved to '${KEY_PATH}'); skipping service account activation." >&2
      fi
    fi
  else
    echo "USE_SERVICE_ACCOUNT=1 but no key file provided; skipping service account activation." >&2
  fi
else
  echo "Skipping service account activation (USE_SERVICE_ACCOUNT=${USE_SERVICE_ACCOUNT})." >&2
fi

gcloud config set project "${PROJECT_ID}"

gcloud auth configure-docker "${REGION}-docker.pkg.dev"

if ! gcloud artifacts repositories describe "${REPO_NAME}" \
  --location "${REGION}" \
  --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location "${REGION}" \
    --description "Container images for ${SERVICE_NAME}"
fi

if ! gcloud artifacts repositories describe cache \
  --location "${REGION}" \
  --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud artifacts repositories create cache \
    --repository-format=docker \
    --location "${REGION}" \
    --description "Kaniko layer cache for ${SERVICE_NAME}"
fi

ensure_cache_image() {
  if [[ ${REBUILD_CACHE_IMAGE} != 0 ]]; then
    echo "Forcing rebuild of ${CACHE_IMAGE_URI}"
  else
    if gcloud artifacts docker images describe "${CACHE_IMAGE_URI}" \
      --project "${PROJECT_ID}" >/dev/null 2>&1; then
      echo "Found existing cache image ${CACHE_IMAGE_URI}; reusing."
      return 0
    fi
  fi

  local tmpdir
  tmpdir=$(mktemp -d)
  echo "Building cache image context in ${tmpdir}"

  cp "${SCRIPT_DIR}/Dockerfile.cache" "${tmpdir}/"
  cp "${SCRIPT_DIR}/requirements.txt" "${tmpdir}/"
  cp "${SCRIPT_DIR}/scripts/cloudbuild.webapp-cache.yaml" "${tmpdir}/"
  cp -a "${SCRIPT_DIR}/secrets" "${tmpdir}/"

  if ! gcloud builds submit "${tmpdir}" \
    --config "${tmpdir}/cloudbuild.webapp-cache.yaml" \
    --substitutions "_CACHE_IMAGE_URI=${CACHE_IMAGE_URI},_CACHE_REPO=${CACHE_REPO}" \
    --project "${PROJECT_ID}"; then
    status=$?
    rm -rf "${tmpdir}"
    return ${status}
  fi

  rm -rf "${tmpdir}"
}

ensure_cache_image || exit 1

gcloud builds submit "${SCRIPT_DIR}" \
  --config "${SCRIPT_DIR}/scripts/cloudbuild.webapp.yaml" \
  --substitutions "_IMAGE_URI=${IMAGE_URI},_CACHE_REPO=${CACHE_REPO},_CACHE_IMAGE_URI=${CACHE_IMAGE_URI}" \
  --project "${PROJECT_ID}"

SECRET_ENV_VARS=()
read -r -a SECRET_NAME_LIST <<< "${SECRET_NAMES}"
for name in "${SECRET_NAME_LIST[@]}"; do
  [[ -z "${name}" ]] && continue
  env_var_name="${name}_RESOURCE"
  secret_name_var="${name}_SECRET_NAME"
  secret_name=${!secret_name_var:-${name}}
  secret_name_lower=$(printf '%s' "${secret_name}" | tr '[:upper:]' '[:lower:]')

  if [[ "${ENVIRONMENT_LOWER}" == "dev" && "${secret_name_lower}" == *"_prod_"* ]]; then
    continue
  fi

  if [[ "${ENVIRONMENT_LOWER}" == "prod" && "${secret_name_lower}" == *"_dev_"* ]]; then
    continue
  fi

  SECRET_ENV_VARS+=("${env_var_name}=projects/${SECRET_PROJECT_ID}/secrets/${secret_name}/versions/${SECRET_VERSION}")
done

JOINED_SECRET_ENV_VARS=$(IFS=,; printf '%s' "${SECRET_ENV_VARS[*]}")
JOINED_ENV_FILE_VARS=$(IFS=,; printf '%s' "${ENV_FILE_VARS[*]}")

DEPLOY_ARGS=(
  gcloud run deploy "${SERVICE_NAME}"
  --image "${IMAGE_URI}"
  --project "${PROJECT_ID}"
  --region "${REGION}"
  --platform managed
  --allow-unauthenticated
  --port 8080
  --cpu 2
  --memory 4Gi
  --min-instances 0
  --max-instances 3
  --concurrency 80
)

if [[ -n "${JOINED_ENV_FILE_VARS}" ]]; then
  DEPLOY_ARGS+=(--set-env-vars "${JOINED_ENV_FILE_VARS}")
fi

if [[ -n "${JOINED_SECRET_ENV_VARS}" ]]; then
  DEPLOY_ARGS+=(--set-env-vars "${JOINED_SECRET_ENV_VARS}")
fi

"${DEPLOY_ARGS[@]}"

gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --format='value(status.url)'
