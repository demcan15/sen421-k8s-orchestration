# SEN421 Project — Container Orchestration with Kubernetes (Topic 8, Part A)

How much user-visible downtime do pod failures and version updates cause on Kubernetes, how
much of it is removed by replicas + readiness probes and by a RollingUpdate strategy, and how
fast does a Horizontal Pod Autoscaler react at 50 % vs 80 % CPU targets?

Everything runs locally on a [kind](https://kind.sigs.k8s.io) cluster. **No cloud resources are
created, the actual cost is USD 0, and no credentials are needed.**

## Contents
| Path | Purpose |
|---|---|
| `app/` | Flask API (`/`, `/health`, `/cpu`, `/version`) + Dockerfile; Redis-backed hit counter |
| `k8s/` | kind cluster config, Redis, api Service, Deployment variants, HPA variants, metrics-server |
| `load/probe.py` | Availability probe: 1 request / 100 ms, logs status + latency to CSV |
| `load/k6-cpu.js` | Constant-arrival-rate load on `/cpu` for the HPA experiment |
| `scripts/e1_selfheal.py` | E1: delete a pod — baseline (1 replica, no probes) vs hardened (3 replicas + probes) |
| `scripts/e2_update.py` | E2: v1 → v2 update — Recreate vs RollingUpdate (both 3 replicas + probes) |
| `scripts/e3_hpa.py` | E3: HPA at 80 % vs 50 % CPU target, 7 req/s on `/cpu`, 180 s load + 180 s idle |
| `analysis/analyze.py` | Builds `results/summary*.csv`, `results/summary.md` and `results/figures/` |
| `results/` | Raw data of every run (committed) |
| `report/` | IEEE report (`main.tex`) |
| `slides/` | Beamer slides (`slides.tex`) |

## Requirements (versions used)
Windows 11, Docker Desktop 29.5.3, kind 0.33.0 (node image Kubernetes v1.37.0), kubectl,
Python 3.14 on the host (pandas, matplotlib, tabulate), images `python:3.12-slim` and
`grafana/k6:2.4.0` for the load clients.

## Reproduce
```powershell
# 1. Images and cluster
docker build -t sen421-api:v1 --build-arg APP_VERSION=v1 app
docker build -t sen421-api:v2 --build-arg APP_VERSION=v2 app
kind create cluster --config k8s/kind-config.yaml
kind load docker-image sen421-api:v1 sen421-api:v2 --name sen421

# 2. Shared components
kubectl apply -f k8s/metrics-server.yaml      # upstream v0.8.0 + --kubelet-insecure-tls (kind only)
kubectl apply -f k8s/redis.yaml -f k8s/api-service.yaml

# 3. Experiments (each runs 3 repetitions of both alternatives)
python scripts/e1_selfheal.py     # ~7 min
python scripts/e2_update.py       # ~10 min
python scripts/e3_hpa.py          # ~45 min

# 4. Analysis
pip install pandas matplotlib tabulate
python analysis/analyze.py

# 5. Clean up
kind delete cluster --name sen421
```

## Measurement path (important)
The probe and k6 run **as containers on the `kind` Docker network** and call the api through
the NodePort on the control-plane node (`http://sen421-control-plane:30080`). A first version
called `http://127.0.0.1:8080` from the Windows host through Docker Desktop's port forwarding;
that path showed ~20 s of failures after a pod kill although the service had recovered inside
the cluster after ~5 s (verified with `curl` against the pod IP and the NodePort from inside the
node). Those runs are kept in `results/e1_hostpath_artifact/` as evidence and are **not** used
in the results. Also, `localhost` on Windows adds ~1 s per request (IPv6 is tried first), so
`127.0.0.1` is used everywhere on the host.

Host and container clocks were compared before the runs; the offset was below the ±0.25 s
resolution of that check.

## Results (mean ± std over 3 runs, see `results/summary.md`)
| Experiment | Alternative A | Alternative B |
|---|---|---|
| E1 pod deletion — downtime | 1 replica, no probes: 3.21 ± 0.00 s (5 failed req.) | 3 replicas + probes: 0 s |
| E2 update — downtime / rollout | Recreate: 5.37 ± 0.16 s / 7.85 s | RollingUpdate: 0 s / 12.41 s |
| E3 HPA — max replicas / p95 / pod-s | 80 %: 5.3 / 118 ms / 1323 | 50 %: 9.3 / 112 ms / 2090 |

Estimated AKS cost (list prices, 2026-11-17): USD 48.29/month baseline vs USD 210.57 hardened
(`results/cost_summary.md`).

## Archived (not reported) data
| Folder | Why it is not used |
|---|---|
| `results/e1_hostpath_artifact/` | Probe ran on the Windows host through Docker Desktop port forwarding (see above). |
| `results/e3_wallclock_v1/` | First `/cpu` version spun for a fixed *wall-clock* time, so CPU throttling and overload could not appear as latency. Replaced by a fixed amount of work (150,000 SHA-256 rounds ≈ 50 ms). |
| `results/archive_prev_image/` | E1/E2 runs made with the previous image. All reported E1–E3 results were re-run with the final image so that every number comes from the same build. |
| `results/e3_overload_10rps/` | E3 at 10 req/s: the single pod saturated, failed its readiness probe, and the HPA ignored the unready pod and never scaled out. Discussed in the report; reported E3 runs use 7 req/s. |
