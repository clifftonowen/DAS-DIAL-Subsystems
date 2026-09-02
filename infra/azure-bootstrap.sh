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
LOCATION="${LOCATION:-southeastasia}"        # Singapore. Keep it near Supabase — every request
                                             # makes a round trip there.
ENVIRONMENT="${ENVIRONMENT:-das-dial-env}"
APP="${APP:-das-dial-api}"
REPO="clifftonowen/DAS-DIAL-Subsystems"
IMAGE="ghcr.io/$(echo "$REPO" | tr '[:upper:]' '[:lower:]')-api:bootstrap"

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"

az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

az group create --name "$RG" --location "$LOCATION" -o none
az containerapp env create --name "$ENVIRONMENT" --resource-group "$RG" --location "$LOCATION" -o none

# --- the app ----------------------------------------------------------------------------------
# Secrets live in Container Apps' own secret store and are referenced by env vars as
# `secretref:`, so no real value is ever passed on a later deploy command or printed in a log.
#
# --min-replicas 1 is what buys a demo with NO cold start, and it is also the entire running
# cost: roughly $14/month at this size, so the $100 credit covers about seven months. Set it to 0
# to scale to zero and pay almost nothing, at the price of a few seconds on the first request
# after idle. That is a one-flag change; nothing else about the deployment differs.
echo "Enter the four secret values (input is not echoed):"
read -rsp "  SUPABASE_URL: " V_URL; echo
read -rsp "  SUPABASE_KEY (service-role): " V_KEY; echo
read -rsp "  SUPABASE_JWT_SECRET: " V_JWT; echo
read -rsp "  GEMINI_API_KEY: " V_GEM; echo

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

FQDN="$(az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)"

# --- GitHub OIDC ------------------------------------------------------------------------------
# Federated credentials, not a stored client secret: this repo is public and a long-lived
# credential is a thing that can leak. The subject pins it to pushes on main of THIS repo.
APP_ID="$(az ad app create --display-name das-dial-deployer --query appId -o tsv)"
az ad sp create --id "$APP_ID" -o none 2>/dev/null || true
az role assignment create --role Contributor \
  --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RG}" \
  --assignee "$APP_ID" -o none

az ad app federated-credential create --id "$APP_ID" --parameters "{
  \"name\": \"github-main\",
  \"issuer\": \"https://token.actions.githubusercontent.com\",
  \"subject\": \"repo:${REPO}:ref:refs/heads/main\",
  \"audiences\": [\"api://AzureADTokenExchange\"]
}" -o none

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
