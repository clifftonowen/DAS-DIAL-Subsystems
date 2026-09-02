#!/usr/bin/env bash
# One-time Azure Container Apps setup for the DAS D.I.A.L API. Run ONCE, by hand, from the repo
# root. Routine deploys are the `deploy` job in .github/workflows/tests.yml, not this script.
#
# Why Azure and not DigitalOcean or Cloud Run:
#   - DigitalOcean wound down its Student Pack participation; every credit expired 2026-08-01.
#   - Cloud Run's free tier is permanent, but reopening a closed GCP billing account needs a card.
#   - Azure for Students needs NO card (it verifies through GitHub Student), gives $100/year, and
#     is renewable annually while enrolled.
#
# The image comes from ghcr.io, NOT Azure Container Registry. ACR Basic is ~$5/month and would
# eat the credit for nothing: the repo is public, so ghcr is free, and the image carries no
# secrets — .dockerignore excludes .env and every credential arrives as a runtime env var.
#
# Prerequisites: az CLI installed, `az login` done.
set -euo pipefail

RG="${RG:-das-dial-rg}"
# Hong Kong, not Singapore, and not by preference. `southeastasia` is nearer to Supabase, but this
# subscription's Azure for Students policy refuses it:
#
#   (RequestDisallowedByAzure) Resource 'workspace-...' was disallowed by Azure: This policy
#   maintains a set of best available regions where your subscription can deploy resources.
#
# That set is assigned per subscription from spare capacity, so it is not the same for everyone and
# it can change. `eastasia` is the closest one this subscription allows. Note the failure surfaces
# on the Log Analytics workspace the Container Apps environment creates, NOT on the resource group
# — `az group create` is exempt and succeeds, so a blocked region looks like it worked until the
# environment step.
#
# To find the allowed set on another subscription:
#   az policy assignment list --query "[].parameters" -o json   # look for listOfAllowedLocations
LOCATION="${LOCATION:-eastasia}"
ENVIRONMENT="${ENVIRONMENT:-das-dial-env}"
APP="${APP:-das-dial-api}"
REPO="clifftonowen/DAS-DIAL-Subsystems"
IMAGE="ghcr.io/$(echo "$REPO" | tr '[:upper:]' '[:lower:]')-api:bootstrap"

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"

az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

# Every create below is guarded, so a run that died halfway can simply be run again. `az group
# create` is already idempotent; the others are not, and `set -e` turns "already exists" into an
# abort rather than something you can ignore.
az group create --name "$RG" --location "$LOCATION" -o none

if ! az containerapp env show --name "$ENVIRONMENT" --resource-group "$RG" -o none 2>/dev/null; then
  # Takes several minutes and prints nothing while it works. That is normal, not a hang.
  echo "  creating Container Apps environment (this takes a few minutes)..."
  az containerapp env create --name "$ENVIRONMENT" --resource-group "$RG" --location "$LOCATION" -o none
else
  echo "  Container Apps environment $ENVIRONMENT already exists."
fi

# --- the app ----------------------------------------------------------------------------------
# Secrets live in Container Apps' own secret store and are referenced by env vars as
# `secretref:`, so no real value is ever passed on a later deploy command or printed in a log.
#
# --min-replicas 1 is what buys a demo with NO cold start, and it is also the entire running
# cost: roughly $14/month at this size, so the $100 credit covers about seven months. Set it to 0
# to scale to zero and pay almost nothing, at the price of a few seconds on the first request
# after idle. That is a one-flag change; nothing else about the deployment differs.
# Secrets come from the environment when set, and are prompted for otherwise. The env path exists
# because `read` is only safe when this script is RUN as a file: paste it into an interactive
# shell and each `read` consumes the next LINE OF THE SCRIPT as its answer, silently. Running
# `bash azure-bootstrap.sh` is the supported way; the env vars are for anywhere that is awkward.
#
#   SUPABASE_URL=... SUPABASE_KEY=... SUPABASE_JWT_SECRET=... GEMINI_API_KEY=... \
#     bash infra/azure-bootstrap.sh
prompt_for() {
  local var="$1" label="$2" existing="${!1:-}"
  if [ -n "$existing" ]; then
    printf '  %s: taken from the environment\n' "$label" >&2
    printf '%s' "$existing"
    return
  fi
  # Read from the terminal explicitly rather than stdin, so a piped or pasted script cannot
  # answer its own prompt. No terminal (CI, `bash script < /dev/null`) is a clear error rather
  # than a hang or a `set -u` "unbound variable" traceback.
  local value=""
  if [ ! -r /dev/tty ]; then
    echo "ERROR: $var is not set and there is no terminal to prompt on." >&2
    echo "       Pass it in the environment instead:" >&2
    echo "       $var=... bash infra/azure-bootstrap.sh" >&2
    return 1
  fi
  read -rsp "  $label: " value < /dev/tty; echo >&2
  printf '%s' "$value"
}

echo "Secret values (input is not echoed):"
V_URL="$(prompt_for SUPABASE_URL 'SUPABASE_URL')"
V_KEY="$(prompt_for SUPABASE_KEY 'SUPABASE_KEY (service-role)')"
V_JWT="$(prompt_for SUPABASE_JWT_SECRET 'SUPABASE_JWT_SECRET')"
V_GEM="$(prompt_for GEMINI_API_KEY 'GEMINI_API_KEY')"

for pair in "SUPABASE_URL:$V_URL" "SUPABASE_KEY:$V_KEY" "SUPABASE_JWT_SECRET:$V_JWT" "GEMINI_API_KEY:$V_GEM"; do
  if [ -z "${pair#*:}" ]; then
    echo "ERROR: ${pair%%:*} is empty. Aborting before creating anything." >&2
    exit 1
  fi
done

if az containerapp show --name "$APP" --resource-group "$RG" -o none 2>/dev/null; then
  echo "  container app $APP exists — updating its secrets and env instead of recreating."
  az containerapp secret set --name "$APP" --resource-group "$RG" \
    --secrets "supabase-url=$V_URL" "supabase-key=$V_KEY" "jwt-secret=$V_JWT" "gemini-key=$V_GEM" \
    -o none
  az containerapp update --name "$APP" --resource-group "$RG" \
    --set-env-vars \
        SUPABASE_URL=secretref:supabase-url \
        SUPABASE_KEY=secretref:supabase-key \
        SUPABASE_JWT_SECRET=secretref:jwt-secret \
        GEMINI_API_KEY=secretref:gemini-key \
        LLM_PROVIDER=gemini \
        EMBEDDING_PROVIDER=gemini \
        USE_EMBEDDING_ALT=true \
        MIN_SIMILARITY=0.71 \
        SIGNUP_ENABLED=false \
    -o none
else
  az containerapp create \
    --name "$APP" --resource-group "$RG" --environment "$ENVIRONMENT" \
    --image "$IMAGE" \
    --target-port 8000 --ingress external \
    --min-replicas 1 --max-replicas 3 \
    --cpu 0.25 --memory 0.5Gi \
    --secrets "supabase-url=$V_URL" "supabase-key=$V_KEY" "jwt-secret=$V_JWT" "gemini-key=$V_GEM" \
    --env-vars \
        SUPABASE_URL=secretref:supabase-url \
        SUPABASE_KEY=secretref:supabase-key \
        SUPABASE_JWT_SECRET=secretref:jwt-secret \
        GEMINI_API_KEY=secretref:gemini-key \
        LLM_PROVIDER=gemini \
        EMBEDDING_PROVIDER=gemini \
        USE_EMBEDDING_ALT=true \
        MIN_SIMILARITY=0.71 \
        SIGNUP_ENABLED=false \
    -o none
fi

FQDN="$(az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)"

# --- GitHub OIDC ------------------------------------------------------------------------------
# Federated credentials, not a stored client secret: this repo is public and a long-lived
# credential is a thing that can leak. The subject pins it to pushes on main of THIS repo.
#
# LOOK THE APP REGISTRATION UP BEFORE CREATING IT. `az ad app create` does not conflict on an
# existing display name — it happily makes a SECOND registration with the same name and a
# different appId. Re-running a failed bootstrap would then print an AZURE_CLIENT_ID whose
# federated credential and role assignment live on the other one, and the deploy job would fail
# to authenticate with nothing obviously wrong anywhere.
APP_ID="$(az ad app list --display-name das-dial-deployer --query '[0].appId' -o tsv 2>/dev/null || true)"
if [ -z "$APP_ID" ]; then
  APP_ID="$(az ad app create --display-name das-dial-deployer --query appId -o tsv)"
  echo "  created app registration das-dial-deployer"
else
  echo "  reusing existing app registration das-dial-deployer"
fi

az ad sp create --id "$APP_ID" -o none 2>/dev/null || true

# Re-running this on an existing assignment is an error, not a no-op, so ask first.
if [ -z "$(az role assignment list --assignee "$APP_ID" \
             --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RG}" \
             --role Contributor --query '[0].id' -o tsv 2>/dev/null || true)" ]; then
  az role assignment create --role Contributor \
    --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RG}" \
    --assignee "$APP_ID" -o none
fi

if ! az ad app federated-credential show --id "$APP_ID" --federated-credential-id github-main -o none 2>/dev/null; then
  az ad app federated-credential create --id "$APP_ID" --parameters "{
    \"name\": \"github-main\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:${REPO}:ref:refs/heads/main\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
fi

echo
echo "=== GitHub secrets to set ==="
echo "AZURE_CLIENT_ID         ${APP_ID}"
echo "AZURE_TENANT_ID         ${TENANT_ID}"
echo "AZURE_SUBSCRIPTION_ID   ${SUBSCRIPTION_ID}"
echo "AZURE_RESOURCE_GROUP    ${RG}"
echo "AZURE_CONTAINERAPP      ${APP}"
echo "PROD_API_URL            https://${FQDN}"
echo
echo "Set CORS_ORIGINS once the Pages URL exists:"
echo "  az containerapp update -n ${APP} -g ${RG} --set-env-vars CORS_ORIGINS=https://<project>.pages.dev"
