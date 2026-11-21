"""E2 - Version update v1 -> v2 under constant probe traffic.

Alternatives: Recreate vs RollingUpdate (maxSurge 1, maxUnavailable 0). Both: 3 replicas + probes.
Per run: probe CSV + JSON with total rollout duration.
Usage: python scripts/e2_update.py [--runs 3]
"""
import argparse
import time

from common import RESULTS, kubectl, reset, start_probe, write_json

VARIANTS = {"recreate": "api-recreate.yaml", "rolling": "api-hardened.yaml"}
PRE, TOTAL = 5.0, 60.0


def run_once(variant: str, run: int):
    reset(VARIANTS[variant])
    probe = start_probe(RESULTS / "e2" / f"{variant}_run{run}.csv", TOTAL)
    time.sleep(PRE)
    start_epoch = time.time()
    kubectl("set", "image", "deploy/api", "api=sen421-api:v2")
    kubectl("rollout", "status", "deploy/api", "--timeout=180s")
    done_epoch = time.time()
    probe.wait()
    meta = {"variant": variant, "run": run, "update_start_epoch": round(start_epoch, 3),
            "rollout_done_epoch": round(done_epoch, 3), "rollout_s": round(done_epoch - start_epoch, 3)}
    write_json(RESULTS / "e2" / f"{variant}_run{run}.json", meta)
    print(meta, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    for r in range(1, a.runs + 1):
        for v in VARIANTS:
            run_once(v, r)
