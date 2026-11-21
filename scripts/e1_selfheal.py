"""E1 - Self-healing: delete one api pod under constant probe traffic.

Alternatives: baseline (1 replica, no probes) vs hardened (3 replicas, readiness/liveness probes).
Per run: probe CSV (user-visible availability) + JSON with time until a replacement pod is Ready.
Usage: python scripts/e1_selfheal.py [--runs 3]
"""
import argparse
import time

from common import RESULTS, api_pods, kubectl, reset, start_probe, write_json

VARIANTS = {"baseline": "api-baseline.yaml", "hardened": "api-hardened.yaml"}
PRE, TOTAL = 5.0, 45.0  # seconds of traffic before the kill / total probe duration


def run_once(variant: str, run: int):
    reset(VARIANTS[variant])
    before = {p["name"] for p in api_pods()}
    victim = sorted(before)[0]
    probe = start_probe(RESULTS / "e1" / f"{variant}_run{run}.csv", TOTAL)
    time.sleep(PRE)
    kill_epoch = time.time()
    kubectl("delete", "pod", victim, "--wait=false")

    ready_epoch = None
    while time.time() - kill_epoch < TOTAL - PRE:
        new = [p for p in api_pods() if p["name"] not in before and p["ready"] and not p["deleting"]]
        if new:
            ready_epoch = time.time()
            break
        time.sleep(0.2)
    probe.wait()
    meta = {"variant": variant, "run": run, "victim": victim, "kill_epoch": round(kill_epoch, 3),
            "replacement_ready_epoch": round(ready_epoch, 3) if ready_epoch else None,
            "k8s_recovery_s": round(ready_epoch - kill_epoch, 3) if ready_epoch else None}
    write_json(RESULTS / "e1" / f"{variant}_run{run}.json", meta)
    print(meta, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    for r in range(1, a.runs + 1):
        for v in VARIANTS:
            run_once(v, r)
