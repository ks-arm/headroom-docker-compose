import time, requests, os
from prometheus_client import start_http_server, Gauge

URL = os.getenv("HEADROOM_URL", "http://host.docker.internal:8787")
INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "15"))

# Session / lifetime aggregates
cost_saved      = Gauge("headroom_cost_saved_usd",        "USD saved by headroom (session)")
cost_savings_pct= Gauge("headroom_cost_savings_pct",      "Cost savings percent (session)")
cost_without    = Gauge("headroom_cost_without_usd",      "Cost without headroom USD (session)")
cost_with       = Gauge("headroom_cost_with_usd",         "Cost with headroom USD (session)")
avg_compression = Gauge("headroom_compression_avg_pct",   "Average compression percent")
best_compression= Gauge("headroom_compression_best_pct",  "Best compression percent")
tp_p50          = Gauge("headroom_throughput_input_p50",  "Input tokens/s p50 (active requests)")
tp_p95          = Gauge("headroom_throughput_input_p95",  "Input tokens/s p95 (active requests)")
compress_p50    = Gauge("headroom_throughput_compress_p50","Compression tokens/s p50")
lifetime_saved  = Gauge("headroom_lifetime_tokens_saved", "Lifetime tokens saved")
lifetime_usd    = Gauge("headroom_lifetime_cost_saved_usd","Lifetime USD saved by compression")
session_pct     = Gauge("headroom_session_savings_pct",   "Current session savings percent")
session_saved   = Gauge("headroom_session_tokens_saved",  "Current session tokens saved")

# Per-model / per-provider (cumulative totals, labeled)
model_tokens_saved = Gauge("headroom_model_tokens_saved",  "Cumulative tokens saved", ["model", "provider"])
model_input_tokens = Gauge("headroom_model_input_tokens",  "Cumulative input tokens",  ["model", "provider"])
model_cost_saved   = Gauge("headroom_model_cost_saved_usd","Cumulative cost saved USD",["model", "provider"])
model_input_cost   = Gauge("headroom_model_input_cost_usd","Cumulative input cost USD", ["model", "provider"])

def scrape():
    try:
        s = requests.get(f"{URL}/stats", timeout=5).json()["summary"]
        cost_saved.set(s["cost"]["total_saved_usd"])
        cost_savings_pct.set(s["cost"]["savings_pct"])
        cost_without.set(s["cost"]["without_headroom_usd"])
        cost_with.set(s["cost"]["with_headroom_usd"])
        avg_compression.set(s["compression"]["avg_compression_pct"])
        best_compression.set(s["compression"]["best_compression_pct"])
        tp = requests.get(f"{URL}/stats", timeout=5).json()["throughput"]["current"]
        tp_p50.set(tp["input_active_p50"])
        tp_p95.set(tp["input_active_p95"])
        compress_p50.set(tp["compression_p50"])
    except Exception as e:
        print(f"[stats] {e}")

    try:
        h = requests.get(f"{URL}/stats-history", timeout=5).json()
        lifetime_saved.set(h["lifetime"]["tokens_saved"])
        lifetime_usd.set(h["lifetime"]["compression_savings_usd"])
        ds = h["display_session"]
        session_pct.set(ds["savings_percent"])
        session_saved.set(ds["tokens_saved"])

        # Aggregate history by model+provider (last seen cumulative value per pair)
        by_model = {}
        for entry in h.get("history", []):
            key = (entry["model"], entry["provider"])
            by_model[key] = entry  # later entries overwrite, giving the latest cumulative

        for (model, provider), e in by_model.items():
            labels = {"model": model, "provider": provider}
            model_tokens_saved.labels(**labels).set(e.get("total_tokens_saved", 0))
            model_input_tokens.labels(**labels).set(e.get("total_input_tokens", 0))
            model_cost_saved.labels(**labels).set(e.get("compression_savings_usd", 0))
            model_input_cost.labels(**labels).set(e.get("total_input_cost_usd", 0))
    except Exception as e:
        print(f"[stats-history] {e}")

if __name__ == "__main__":
    start_http_server(9091)
    print(f"Exporter running on :9091, polling {URL} every {INTERVAL}s")
    while True:
        scrape()
        time.sleep(INTERVAL)
