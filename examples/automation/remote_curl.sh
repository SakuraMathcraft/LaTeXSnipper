#!/bin/sh
set -eu

# BASE_URL must be an HTTPS URL or an address reached through an encrypted tunnel.
: "${BASE_URL:?Set BASE_URL}"
: "${LATEXSNIPPER_REMOTE_KEY:?Set LATEXSNIPPER_REMOTE_KEY}"

curl --fail-with-body --silent --show-error \
  "$BASE_URL/api/v1/recognition/jobs" \
  -H "Authorization: Bearer $LATEXSNIPPER_REMOTE_KEY" \
  -H "Prefer: wait=30" \
  -F "backend=${BACKEND:-mathcraft}" \
  -F mode=mixed \
  -F timeout=120 \
  -F "images=@${1:?Pass an image path}"
