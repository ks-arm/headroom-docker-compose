#!/usr/bin/env bash
# ponytail: interactive menu for `headroom learn --verbosity`.
# headroom's `--project` can't match paths with hyphens/spaces, so per-project
# apply writes /workspace/verbosity.json directly from parsed --all output.
# Non-interactive: `list` / `all` / `all --apply`.
set -euo pipefail
CONTAINER=headroom-proxy

docker ps --format '{{.Names}}' | grep -qx "$CONTAINER" \
  || { echo "error: container '$CONTAINER' is not running" >&2; exit 1; }

# Fast paths (no menu)
case "${1:-}" in
  list) exec docker exec "$CONTAINER" headroom learn --verbosity --all \
          | grep -E '^Path:|Recommended verbosity' ;;
  all)
    apply=()
    [[ "${2:-}" == "--apply" ]] && apply=(--apply)
    exec docker exec "$CONTAINER" headroom learn --verbosity ${apply[@]+"${apply[@]}"} --all ;;
esac

# Interactive menu: ship python into the container, then run it with a TTY
docker exec -i "$CONTAINER" sh -c 'cat > /tmp/_learn_menu.py' <<'PY'
import subprocess, re, json, sys
from datetime import datetime, timezone

WS = "/workspace"

def discover():
    r = subprocess.run(["headroom","learn","--verbosity","--all"],
                       capture_output=True, text=True)
    text = r.stdout + r.stderr
    paths = re.findall(r"Path:\s*(.+)", text)
    if not paths:
        return []
    levels = [int(x) for x in re.findall(r"Recommended verbosity level:\s*(\d+)", text)]
    confs  = re.findall(r"\(confidence:\s*(\w+)\)", text)
    srcs   = re.findall(r"Source:\s*(\w+)", text)
    rats   = re.findall(r"\n\s{2}([^\n]*\(L\d\))", text)
    sess   = re.findall(r"Sessions:\s*(\d+)\s+human turns:\s*(\d+)\s+responses:\s*(\d+)", text)
    inter  = re.findall(r"Interrupts:\s*(\d+)\s+\(([\d.]+)%", text)
    skips  = re.findall(r"Fast-skips:\s*(\d+)\s*/\s*(\d+)\s+long answers \((\d+)%", text)
    echo   = re.findall(r"Echo ratio:\s*([\d.]+)%", text)
    rows = []
    for i, path in enumerate(paths):
        signals = {}
        if i < len(sess):
            signals.update(sessions=int(sess[i][0]), human_msgs=int(sess[i][1]),
                           asst_responses=int(sess[i][2]))
        if i < len(inter):
            signals.update(interrupts=int(inter[i][0]), interrupt_rate=float(inter[i][1])/100)
        if i < len(skips):
            signals.update(fast_skips=int(skips[i][0]), skip_eligible=int(skips[i][1]),
                           fast_skip_rate=float(skips[i][2])/100)
        if i < len(echo):
            signals["mean_echo_ratio"] = float(echo[i])/100
        rows.append({
            "path": path.strip(),
            "level": levels[i] if i < len(levels) else 0,
            "conf": confs[i] if i < len(confs) else "unknown",
            "source": srcs[i] if i < len(srcs) else "heuristic",
            "rationale": rats[i].strip() if i < len(rats) else "",
            "signals": signals,
        })
    return rows

def write_verbosity(row):
    data = {
        "project_path": row["path"],
        "verbosity_level": row["level"],
        "confidence": row["conf"],
        "source": row["source"],
        "rationale": row["rationale"],
        "signals": row["signals"],
        "learned_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(f"{WS}/verbosity.json", "w") as f:
        json.dump(data, f, indent=2)

rows = discover()
if not rows:
    print("No Claude projects discovered."); sys.exit(1)

print("\n  [0]  ALL projects   (headroom learn --all --apply)")
for i, r in enumerate(rows, 1):
    print(f"  [{i:<2}] L{r['level']} {r['conf']:<6} {r['path']}")
print()

try:
    choice = input(f"Pick [0-{len(rows)}], Enter=0, q=quit: ").strip()
except (EOFError, KeyboardInterrupt):
    print("\nAborted."); sys.exit(130)

if choice.lower() in ("q","quit",""): 
    if choice == "": choice = "0"
    else: print("Aborted."); sys.exit(0)
if not choice.isdigit() or not (0 <= int(choice) <= len(rows)):
    print(f"Invalid: {choice!r}"); sys.exit(1)
n = int(choice)

if n == 0:
    print("\n>> headroom learn --verbosity --apply --all\n")
    subprocess.run(["headroom","learn","--verbosity","--apply","--all"])
    print(f"\nDone. Last project is the active level in {WS}/verbosity.json")
else:
    row = rows[n-1]
    write_verbosity(row)
    print(f"\n>> Active verbosity = L{row['level']} ({row['conf']})")
    print(f"   {row['path']}")
    print(f"   wrote {WS}/verbosity.json")

print("\nShaper uses this when HEADROOM_OUTPUT_SHAPER=1 and HEADROOM_VERBOSITY_LEVEL is unset.")
PY

TTY=()
[ -t 0 ] && TTY=(-t)
exec docker exec -i ${TTY[@]+"${TTY[@]}"} "$CONTAINER" python3 /tmp/_learn_menu.py
