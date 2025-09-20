#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

export PROJECT_ID=${PROJECT_ID:-marta-webapp}
export REGION=${REGION:-europe-west1}
export REPO_NAME=${REPO_NAME:-webapp}
export SERVICE_NAME=${SERVICE_NAME:-api-builder-webapp}
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

# Configure project and required APIs
gcloud config set project "${PROJECT_ID}"

gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  --project "${PROJECT_ID}"

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
  SECRET_ENV_VARS+=("${env_var_name}=projects/${SECRET_PROJECT_ID}/secrets/${secret_name}/versions/${SECRET_VERSION}")
done

JOINED_SECRET_ENV_VARS=$(IFS=,; printf '%s' "${SECRET_ENV_VARS[*]}")

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

if [[ -n "${JOINED_SECRET_ENV_VARS}" ]]; then
  DEPLOY_ARGS+=(--set-env-vars "${JOINED_SECRET_ENV_VARS}")
fi

"${DEPLOY_ARGS[@]}"

gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --format='value(status.url)'
