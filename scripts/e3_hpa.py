"""E3 - Horizontal Pod Autoscaler reaction at 50% vs 80% CPU target.

Start from 1 ready replica, apply HPA, run k6 at a constant rate on /cpu for LOAD seconds,
then stay idle for IDLE seconds to observe scale-in. Replica counts and HPA utilisation are
sampled every 2 s; k6 writes per-request results to CSV.
Usage: python scripts/e3_hpa.py [--runs 3]
"""
import argparse
import json
import subprocess
import time

from common import K6_IMAGE, K8S, NETWORK, ROOT, RESULTS, kubectl, reset, write_json

VARIANTS = {"hpa80": "hpa-80.yaml", "hpa50": "hpa-50.yaml"}
LOAD, IDLE, RATE = 180, 180, 7  # 10 req/s saturates one pod -> see results/e3_overload_10rps


def sample():
    d = json.loads(kubectl("get", "deploy", "api", "-o", "json"))["status"]
    h = json.loads(kubectl("get", "hpa", "api", "-o", "json")).get("status", {})
    util = None
    for m in h.get("currentMetrics", []) or []:
        util = m.get("resource", {}).get("current", {}).get("averageUtilization")
    return d.get("replicas", 0), d.get("readyReplicas", 0), h.get("desiredReplicas"), util


def run_once(variant: str, run: int):
    reset("api-hardened.yaml", replicas=1)
    kubectl("apply", "-f", str(K8S / VARIANTS[variant]))
    time.sleep(30)  # let the HPA read its first metrics at idle
    out = RESULTS / "e3"
    out.mkdir(parents=True, exist_ok=True)
    k6 = subprocess.Popen(["docker", "run", "--rm", "--network", NETWORK,
                           "-v", f"{ROOT / 'load'}:/load:ro", "-v", f"{ROOT / 'results'}:/results",
                           K6_IMAGE, "run", "--quiet", "-e", f"RATE={RATE}", "-e", f"DURATION={LOAD}s",
                           "--out", f"csv=/results/e3/{variant}_run{run}_k6.csv",
                           "--summary-export", f"/results/e3/{variant}_run{run}_k6summary.json",
                           "/load/k6-cpu.js"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    load_epoch = time.time()  # k6 container start; k6 CSV has its own epoch timestamps
    rows = ["t_epoch,t_s,replicas,ready,desired,cpu_util_pct"]
    while (t := time.time() - load_epoch) < LOAD + IDLE:
        rep, ready, desired, util = sample()
        rows.append(f"{time.time():.3f},{t:.1f},{rep},{ready},{desired},{util}")
        time.sleep(2)
    k6.wait()
    (out / f"{variant}_run{run}_replicas.csv").write_text("\n".join(rows) + "\n")
    write_json(out / f"{variant}_run{run}.json", {"variant": variant, "run": run, "load_s": LOAD,
                                                  "idle_s": IDLE, "rate_rps": RATE,
                                                  "load_start_epoch": round(load_epoch, 3)})
    print(variant, run, "done; last sample:", rows[-1], flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--first-run", type=int, default=1, help="resume: skip runs before this number")
    a = ap.parse_args()
    for r in range(a.first_run, a.runs + 1):
        for v in VARIANTS:
            run_once(v, r)
