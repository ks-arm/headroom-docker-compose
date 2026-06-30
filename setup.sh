#!/usr/bin/env bash
# ponytail: zero-code interactive setup — ask for key, write .env, bring up the stack.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\033[1;34m▸\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# 1. preflight
command -v docker >/dev/null || die "docker is not installed (https://docs.docker.com/get-docker/)"
docker compose version >/dev/null 2>&1 || die "docker compose v2 not found"
command -v curl >/dev/null || die "curl not found"
ok "Docker ready"

# 2. workspace-root mount sanity (machine-specific path in docker-compose.yml)
if ! docker run --rm -v /Volumes/External-B:/_check:ro alpine true >/dev/null 2>&1; then
  die "'/Volumes/External-B' is not accessible to Docker. Edit the mount in docker-compose.yml to your projects root, then re-run."
fi
ok "Workspace root accessible"

# 3. API key -> .env
if [[ -f .env ]] && grep -q '^ZAI_API_KEY=.' .env; then
  ok "ZAI_API_KEY already in .env"
else
  printf '\033[1;34m▸\033[0m Paste your ZAI_API_KEY (get one at https://z.ai): '
  read -r KEY
  [[ -n "${KEY:-}" ]] || die "No key entered."
  if [[ -f .env ]] && grep -q '^ZAI_API_KEY=' .env; then
    grep -v '^ZAI_API_KEY=' .env > .env.tmp || true
    mv .env.tmp .env
  fi
  printf 'ZAI_API_KEY=%s\n' "$KEY" >> .env
  ok "Key saved to .env"
fi

# 4. bring up the stack
say "Starting the stack (first run builds the exporter)…"
docker compose up -d --build
ok "Stack started"

# 5. wait for the proxy health endpoint
say "Waiting for proxy"
ready=0
for _ in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8787/health 2>/dev/null || echo 000)
  [[ "$code" = "200" ]] && { ready=1; break; }
  printf '.'; sleep 1
done
echo
[[ $ready -eq 1 ]] && ok "Proxy healthy" || die "Proxy did not become healthy — check: docker compose logs headroom-proxy"

# 6. access points
cat <<EOF

$(printf '\033[1;32m') Headroom is up. $(printf '\033[0m')

   Proxy        http://localhost:8787    ← point your agent's base URL here
   Dashboard    http://localhost:8090    ← Manage tab to learn / set verbosity
   Logs         http://localhost:8082
   Metrics      http://localhost:9090
   Grafana      http://localhost:3001

   Learn verbosity now:   ./learn-verbosity.sh

EOF
