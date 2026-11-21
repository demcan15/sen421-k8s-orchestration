"""Availability probe: sends one request every --interval seconds and logs each result.

Output CSV columns: t_epoch, t_rel_s, status, latency_ms, version, pod
(t_epoch = wall-clock time, used to align with kubectl events recorded by the experiment scripts)
status = HTTP code, or 0 for connection error / timeout.

Usage: python probe.py --url http://127.0.0.1:8080/ --duration 60 --out results/x.csv
"""
import argparse
import csv
import json
import time
import urllib.error
import urllib.request


def main():
    p = argparse.ArgumentParser()
    # IPv4 on purpose: "localhost" adds ~1 s per request on Windows (tries ::1 first).
    p.add_argument("--url", default="http://127.0.0.1:8080/")
    p.add_argument("--duration", type=float, default=60)
    p.add_argument("--interval", type=float, default=0.1)
    p.add_argument("--timeout", type=float, default=1.0)
    p.add_argument("--out", required=True)
    a = p.parse_args()

    t0 = time.perf_counter()
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_epoch", "t_rel_s", "status", "latency_ms", "version", "pod"])
        f.flush()
        nxt = t0
        while (now := time.perf_counter()) - t0 < a.duration:
            start = now
            epoch = time.time()
            status, version, pod = 0, "", ""
            try:
                with urllib.request.urlopen(a.url, timeout=a.timeout) as r:
                    status = r.status
                    body = json.loads(r.read())
                    version, pod = body.get("version", ""), body.get("pod", "")
            except urllib.error.HTTPError as e:
                status = e.code
            except Exception:
                status = 0
            lat = (time.perf_counter() - start) * 1000
            w.writerow([f"{epoch:.3f}", f"{start - t0:.3f}", status, f"{lat:.1f}", version, pod])
            f.flush()
            nxt += a.interval
            time.sleep(max(0.0, nxt - time.perf_counter()))


if __name__ == "__main__":
    main()
