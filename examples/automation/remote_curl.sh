#!/usr/bin/env bash
set -euo pipefail

# Requires curl and jq. BASE_URL must be HTTPS or reached through an encrypted
# tunnel. Pass one to sixteen image paths; results remain in input order.
: "${BASE_URL:?Set BASE_URL, for example http://100.x.y.z:28765}"
: "${LATEXSNIPPER_REMOTE_KEY:?Set LATEXSNIPPER_REMOTE_KEY}"

backend="${BACKEND:-mathcraft}"
mode="${MODE:-mixed}"
job_timeout="${TIMEOUT:-120}"
prefer_wait="${PREFER_WAIT:-30}"
poll_interval="${POLL_INTERVAL:-0.25}"
output="${OUTPUT:-text}"

if ! command -v curl >/dev/null || ! command -v jq >/dev/null; then
  echo "This example requires curl and jq." >&2
  exit 2
fi
if (($# < 1 || $# > 16)); then
  echo "Usage: BASE_URL=... LATEXSNIPPER_REMOTE_KEY=... $0 IMAGE [IMAGE ...]" >&2
  exit 2
fi
case "$backend" in mathcraft|external) ;; *) echo "BACKEND must be mathcraft or external." >&2; exit 2 ;; esac
case "$mode" in formula|text|mixed) ;; *) echo "MODE must be formula, text, or mixed." >&2; exit 2 ;; esac
case "$output" in text|json) ;; *) echo "OUTPUT must be text or json." >&2; exit 2 ;; esac
if [[ ! "$job_timeout" =~ ^[1-9][0-9]*$ || "$job_timeout" -gt 3600 ]]; then
  echo "TIMEOUT must be an integer from 1 to 3600." >&2
  exit 2
fi

base_url="${BASE_URL%/}"
response_file="$(mktemp)"
trap 'rm -f "$response_file"' EXIT
form_args=(-F "backend=$backend" -F "mode=$mode" -F "timeout=$job_timeout")
for image in "$@"; do
  if [[ ! -f "$image" ]]; then
    echo "Image file does not exist: $image" >&2
    exit 2
  fi
  form_args+=(-F "images=@$image")
done

request() {
  local method="$1"
  local url="$2"
  shift 2
  curl --silent --show-error --connect-timeout 10 --max-time 40 \
    --output "$response_file" --write-out "%{http_code}" \
    --request "$method" "$url" \
    -H "Authorization: Bearer $LATEXSNIPPER_REMOTE_KEY" \
    "$@"
}

show_http_error() {
  local status="$1"
  local code message request_id
  code="$(jq -r '.error.code // "http_error"' "$response_file" 2>/dev/null || true)"
  message="$(jq -r '.error.message // "Request failed."' "$response_file" 2>/dev/null || true)"
  request_id="$(jq -r '.error.request_id // empty' "$response_file" 2>/dev/null || true)"
  echo "HTTP $status $code: $message${request_id:+ (request_id=$request_id)}" >&2
}

http_status="$(request POST "$base_url/api/v1/recognition/jobs" \
  -H "Prefer: wait=$prefer_wait" \
  -H "Idempotency-Key: curl-$(date +%s)-$$" \
  "${form_args[@]}")"
if [[ "$http_status" != 200 && "$http_status" != 202 ]]; then
  show_http_error "$http_status"
  exit 2
fi

job_id="$(jq -r '.job.id // empty' "$response_file")"
state="$(jq -r '.job.state // empty' "$response_file")"
if [[ -z "$job_id" || -z "$state" ]]; then
  echo "Automation API response did not contain a valid job." >&2
  exit 2
fi

deadline=$((SECONDS + job_timeout + 30))
while [[ "$state" != completed && "$state" != failed && "$state" != canceled ]]; do
  if ((SECONDS >= deadline)); then
    echo "Recognition job $job_id timed out." >&2
    exit 2
  fi
  sleep "$poll_interval"
  http_status="$(request GET "$base_url/api/v1/recognition/jobs/$job_id")"
  if [[ "$http_status" != 200 ]]; then
    show_http_error "$http_status"
    exit 2
  fi
  state="$(jq -r '.job.state // empty' "$response_file")"
done

if [[ "$state" != completed ]]; then
  detail="$(jq -r '.job.error.message // .job.error.code // .job.state' "$response_file")"
  echo "Recognition did not complete: $detail" >&2
  exit 2
fi

failed="$(jq '[.job.items[] | select(.state != "completed")] | length' "$response_file")"
if ((failed > 0)) && [[ "${ALLOW_PARTIAL:-0}" != 1 ]]; then
  jq -r '.job.items[] | select(.state != "completed") |
    "#\(.index) \(.error.code // "failed"): \(.error.message // "")"' "$response_file" >&2
  exit 2
fi

if [[ "$output" == json ]]; then
  jq . "$response_file"
else
  jq -r '.job.items[] | select(.state == "completed") | .text' "$response_file"
fi
