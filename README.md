# Headroom Docker

A self-hosted [Headroom](https://github.com/chopratejas/headroom) optimization-proxy stack with usage dashboard, metrics, and a management UI for the output-shaper verbosity.

Headroom sits between your coding agent (Claude Code, etc.) and the LLM API and compresses/optimizes traffic. This repo wraps it in Docker with persistent state, observability, and a verbosity-learning workflow.

> **Docs:** https://headroom-docs.vercel.app/docs

---

## Requirements

- Docker + Docker Compose (Compose v2)
- macOS with Docker Desktop (the compose uses `${HOME}` and `/Volumes/External-B` bind mounts — adjust the paths for your machine, see [Paths to change](#paths-to-change))
- An API key for your upstream provider — **optional** if you already route via `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in `docker-compose.yml`; set `ZAI_API_KEY` only to use the z.ai upstream

## Zero-code setup (recommended)

One script does everything — checks prerequisites, optionally asks for your API key, writes `.env`, starts the stack, and waits until it's healthy. No file editing.

```sh
./setup.sh
```

You'll be prompted for:

- **`ZAI_API_KEY`** _(optional)_ — get one at https://z.ai. Press **Enter to skip** if you route through another provider (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) set in `docker-compose.yml`.

When it finishes it prints the URLs. Open the **Dashboard** at http://localhost:8090.

That's it — your agent's base URL is `http://localhost:8787`.

> If `./setup.sh` reports that `/Volumes/External-B` isn't accessible, that's the machine-specific projects-root mount — open `docker-compose.yml` and change it to your own path, then re-run. Everything else is automatic.

## Manual setup

1. **Copy the env template and set a key** _(optional — only for the z.ai upstream)_:

   ```sh
   cp .env.example .env
   # then edit .env and uncomment ZAI_API_KEY=...
   ```

   Skip this if you route through `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` instead.

2. **Start everything:**

   ```sh
   docker compose up -d --build
   ```

3. **Open the dashboard:** http://localhost:8090  (default tab is the embedded Headroom dashboard)

4. **Point your agent** at the proxy (OpenAI-compatible base URL):

   ```
   http://localhost:8787
   ```

That's it. State persists in `./data/` and survives `docker compose down -v`.

---

## Point your agent at the proxy (client routing)

The proxy speaks OpenAI- and Anthropic-compatible protocols on `http://127.0.0.1:8787`. Set the matching base URL for each tool you use, then restart the agent.

**Claude Code** (Anthropic API):

```sh
export ANTHROPIC_BASE_URL=http://127.0.0.1:8787
```

**Codex CLI / any OpenAI-compatible client** (note the `/v1`):

```sh
export OPENAI_BASE_URL=http://127.0.0.1:8787/v1
```

Add these to `~/.zshrc` (or `~/.bashrc`) so they persist, then `source ~/.zshrc`. You still need the provider's API key set as usual (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) — the proxy forwards traffic to whichever upstream you configure in `docker-compose.yml` (`ZAI_API_KEY` is optional).

> Tip: run `docker exec headroom-proxy headroom init` to see the exact env vars and wrapper commands Headroom recommends for your installed agents.

---

| Service            | URL                       | Purpose                                                  |
|--------------------|---------------------------|----------------------------------------------------------|
| `headroom-proxy`   | http://localhost:8787     | The optimization proxy (your agent talks to this)        |
| `dashboard` (nginx)| http://localhost:8090     | Usage stats + Manage tab + embedded proxy dashboard      |
| `mgmt`             | _(internal, :8088)_       | Management API sidecar (read/write verbosity, run learn) |
| `dozzle`           | http://localhost:8082     | Live logs (filtered to `headroom-*` containers)          |
| `prometheus`       | http://localhost:9090     | Metrics scraper (30d retention)                          |
| `grafana`          | http://localhost:3001     | Dashboards (anonymous Admin, no login)                   |
| `exporter`         | _(internal)_              | Exposes proxy stats to Prometheus                        |

---

## Persistence (state survives recreate)

All proxy state lives in **bind mounts under `./data/`**, not named volumes — so nothing is lost on `docker compose down -v` or a folder rename:

```
./data/headroom-workspace/   # verbosity.json, savings, session state, logs
./data/headroom-config/      # config dir
```

These are the only things you need to back up.

---

## Output shaper & verbosity learning

Headroom can learn your preferred **output verbosity** from past Claude Code sessions and shape responses to match (e.g. "conclusions only" vs "full detail"). The active level lives in `./data/headroom-workspace/verbosity.json`.

### Activation (already configured)

The shaper is on when **both** are true:

- `HEADROOM_OUTPUT_SHAPER=1` (set on `headroom-proxy` in `docker-compose.yml`)
- `HEADROOM_VERBOSITY_LEVEL` is **unset** (so the level is read from `verbosity.json`)

Precedence: `HEADROOM_VERBOSITY_LEVEL` (env override) > `verbosity.json` > default.

### Learn / set verbosity — two ways

**1. CLI menu (interactive)**

```sh
./learn-verbosity.sh                 # interactive menu: pick a project or All
./learn-verbosity.sh list            # list projects + recommended levels (no write)
./learn-verbosity.sh all --apply     # learn + write across all projects
```

The menu writes `verbosity.json` directly with Headroom's native keys, bypassing `headroom learn --project` (which can't match paths containing hyphens/spaces — see the caveat in the script).

**2. Dashboard → Manage tab** (http://localhost:8090 → **Manage**)

- Shows current **Output Shaper** status + **Active Level**
- Lists learned projects; click **Set** to make one active
- **Re-learn all (--apply)** re-runs learning (project list is cached 10 min)

---

## Configuration reference

### Environment (`.env`)

| Variable      | Required | Description                                               |
|---------------|----------|-----------------------------------------------------------|
| `ZAI_API_KEY` | no       | Key for the z.ai upstream (optional — uncomment in `.env`)|

Other providers (OpenAI/Anthropic) can be added by uncommenting their env lines under `headroom-proxy`.

### Paths to change

These mounts are machine-specific — edit `docker-compose.yml` if your layout differs:

```yaml
# Claude Code transcripts (so `headroom learn` can read session history)
- ${HOME}/.claude/projects:/root/.claude/projects:ro

# Project source root (so `--project <host-path>` validation resolves)
- /Volumes/External-B:/Volumes/External-B:ro
```

---

## Common commands

```sh
docker compose up -d --build          # start / rebuild
docker compose ps                     # status
docker compose logs -f headroom-proxy # tail proxy logs
docker compose restart headroom-proxy # pick up env changes
docker compose down                   # stop (state kept in ./data)
docker compose down -v                # stop + wipe named volumes (./data bind mounts are KEPT)
```

---

## Files

```
.
├── docker-compose.yml          # the whole stack
├── setup.sh                    # zero-code interactive setup
├── .env                        # ZAI_API_KEY (not committed)
├── learn-verbosity.sh          # CLI menu for verbosity learning
├── dashboard/
│   ├── index.html              # usage dashboard SPA + Manage tab
│   └── nginx.conf              # nginx server + /api proxy to mgmt
├── mgmt/
│   └── mgmt_server.py          # stdlib management API sidecar
├── exporter/                   # prometheus exporter for proxy stats
├── prometheus/                 # prometheus config
├── grafana/                    # provisioning + dashboards
└── data/                       # persistent state (bind mounts) — back this up
    ├── headroom-workspace/
    └── headroom-config/
```
