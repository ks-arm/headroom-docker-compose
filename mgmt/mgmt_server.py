#!/usr/bin/env python3
# ponytail: stdlib-only management API for the dashboard.
# Reads/writes /workspace/verbosity.json and runs `headroom learn --verbosity`.
# Runs as a sidecar using the same headroom image (has python3 + headroom CLI).
import json, os, re, subprocess, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone

WS = "/workspace"
VERB = f"{WS}/verbosity.json"
CACHE = f"{WS}/.projects_cache.json"
CACHE_TTL = 600
PORT = int(os.environ.get("MGMT_PORT", "8088"))


def _scan_projects():
    r = subprocess.run(["headroom", "learn", "--verbosity", "--all"],
                       capture_output=True, text=True, timeout=600)
    text = r.stdout + r.stderr
    paths = re.findall(r"Path:\s*(.+)", text)
    levels = [int(x) for x in re.findall(r"Recommended verbosity level:\s*(\d+)", text)]
    confs = re.findall(r"\(confidence:\s*(\w+)\)", text)
    srcs = re.findall(r"Source:\s*(\w+)", text)
    rats = re.findall(r"\n\s{2}([^\n]*\(L\d\))", text)
    out = []
    for i, p in enumerate(paths):
        out.append({
            "path": p.strip(),
            "level": levels[i] if i < len(levels) else None,
            "confidence": confs[i] if i < len(confs) else "unknown",
            "source": srcs[i] if i < len(srcs) else "heuristic",
            "rationale": rats[i].strip() if i < len(rats) else "",
        })
    try:
        tmp = CACHE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"ts": time.time(), "projects": out}, f)
        os.replace(tmp, CACHE)
    except Exception:
        pass
    return out


def parse_projects(force=False):
    if not force:
        try:
            with open(CACHE) as f:
                c = json.load(f)
            age = time.time() - c.get("ts", 0)
            if age < CACHE_TTL:
                return c["projects"], age
        except Exception:
            pass
    return _scan_projects(), 0.0


def read_verbosity():
    try:
        with open(VERB) as f:
            return json.load(f)
    except Exception:
        return None


def write_verbosity(row):
    data = {
        "project_path": row["path"],
        "verbosity_level": int(row["level"]),
        "confidence": row.get("confidence", "unknown"),
        "source": row.get("source", "menu"),
        "rationale": row.get("rationale", ""),
        "signals": {},
        "learned_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = VERB + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, VERB)
    return data


class H(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/state":
            self._json(200, {
                "verbosity": read_verbosity(),
                "output_shaper": os.environ.get("HEADROOM_OUTPUT_SHAPER", "0"),
                "verbosity_level_env": os.environ.get("HEADROOM_VERBOSITY_LEVEL"),
            })
        elif p == "/api/projects":
            force = parse_qs(urlparse(self.path).query).get("refresh", ["0"])[0] == "1"
            try:
                projs, age = parse_projects(force=force)
                self._json(200, {"projects": projs, "cache_age_s": round(age, 1)})
            except Exception as e:
                self._json(500, {"error": str(e)})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/verbosity":
            row = self._read()
            if not row.get("path") or row.get("level") is None:
                self._json(400, {"error": "need path + level"})
                return
            self._json(200, {"ok": True, "verbosity": write_verbosity(row)})
        elif p == "/api/learn-all":
            for f in (CACHE, CACHE + ".tmp"):
                try: os.remove(f)
                except OSError: pass
            r = subprocess.run(["headroom", "learn", "--verbosity", "--apply", "--all"],
                               capture_output=True, text=True, timeout=900)
            self._json(200 if r.returncode == 0 else 500, {
                "ok": r.returncode == 0,
                "tail": (r.stdout + r.stderr)[-1500:],
            })
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"mgmt API on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
