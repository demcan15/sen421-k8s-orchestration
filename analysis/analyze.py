"""Turn raw experiment output in results/ into summary tables and figures.

Outputs:
  results/summary_e1.csv, summary_e2.csv, summary_e3.csv   (one row per run)
  results/summary.md                                      (mean +- std per variant)
  results/figures/*.pdf and *.png                          (for the report and slides)
Usage: python analysis/analyze.py
"""
import glob
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
FIG = RES / "figures"
FIG.mkdir(parents=True, exist_ok=True)
PROBE_INTERVAL = 0.1
SLOW_MS = 200  # E3: a 10 s window with p95 above this counts as "degraded"
plt.rcParams.update({"font.size": 9, "figure.dpi": 150, "savefig.bbox": "tight"})


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf")
    fig.savefig(FIG / f"{name}.png")
    plt.close(fig)


def downtime(df, ref_epoch):
    """Failed-request window relative to ref_epoch: (n_failed, first, last, window_s)."""
    bad = df[df.status != 200]
    if bad.empty:
        return 0, None, None, 0.0
    first = bad.t_epoch.min() - ref_epoch
    last = bad.t_epoch.max() - ref_epoch
    # window ends when the last failed request ended (it may have hit the 1 s timeout)
    last_end = (bad.t_epoch + bad.latency_ms / 1000).max() - ref_epoch
    return len(bad), first, last, last_end - first


def agg(df, cols, by="variant"):
    g = df.groupby(by)[cols].agg(["mean", "std"])
    out = pd.DataFrame(index=g.index)
    for c in cols:
        out[c] = [f"{m:.2f} ± {s:.2f}" for m, s in zip(g[(c, "mean")], g[(c, "std")].fillna(0))]
    return out


# ---------------------------------------------------------------- E1 self-healing
def e1():
    rows = []
    for f in sorted(glob.glob(str(RES / "e1" / "*.json"))):
        m = json.load(open(f))
        df = pd.read_csv(f[:-5] + ".csv")
        n, first, last, win = downtime(df, m["kill_epoch"])
        rows.append({"variant": m["variant"], "run": m["run"], "requests": len(df), "failed": n,
                     "downtime_s": win, "k8s_reported_ready_s": m["k8s_recovery_s"]})
    s = pd.DataFrame(rows)
    s.to_csv(RES / "summary_e1.csv", index=False)

    # Figure: probe timeline around the kill, run 1 of each variant
    fig, axes = plt.subplots(2, 1, figsize=(3.5, 3.2), sharex=True)
    for ax, v in zip(axes, ["baseline", "hardened"]):
        m = json.load(open(RES / "e1" / f"{v}_run1.json"))
        df = pd.read_csv(RES / "e1" / f"{v}_run1.csv")
        t = df.t_epoch - m["kill_epoch"]
        ok = df.status == 200
        ax.scatter(t[ok], df.latency_ms[ok], s=3, label="success")
        ax.scatter(t[~ok], df.latency_ms[~ok], s=8, c="red", marker="x", label="failed")
        ax.axvline(0, ls="--", c="gray", lw=0.8)
        ax.set_ylabel("Latency (ms)")
        ax.set_yscale("log")
        ax.set_ylim(0.5, 3000)
        ax.set_title({"baseline": "Baseline (1 replica, no probes)",
                      "hardened": "Hardened (3 replicas + probes)"}[v], fontsize=8)
        ax.set_xlim(-3, 15)
    axes[0].legend(fontsize=7, loc="upper right")
    axes[1].set_xlabel("Time since pod deletion (s)")
    save(fig, "e1_timeline")
    return s


# ---------------------------------------------------------------- E2 update
def e2():
    rows = []
    for f in sorted(glob.glob(str(RES / "e2" / "*.json"))):
        m = json.load(open(f))
        df = pd.read_csv(f[:-5] + ".csv")
        n, first, last, win = downtime(df, m["update_start_epoch"])
        during = df[(df.t_epoch >= m["update_start_epoch"]) & (df.t_epoch <= m["rollout_done_epoch"])
                    & (df.status == 200)]
        before = df[(df.t_epoch < m["update_start_epoch"]) & (df.status == 200)]
        ok = df[df.status == 200]
        # Window in which users could get either version (first v2 answer .. last v1 answer); 0 if none.
        mixed_s = max(0.0, ok[ok.version == "v1"].t_epoch.max() - ok[ok.version == "v2"].t_epoch.min())
        rows.append({"variant": m["variant"], "run": m["run"], "rollout_s": m["rollout_s"],
                     "failed": n, "downtime_s": win,
                     "p95_before_ms": before.latency_ms.quantile(0.95),
                     "p95_during_ms": during.latency_ms.quantile(0.95) if len(during) else float("nan"),
                     "mixed_versions_s": mixed_s})
    s = pd.DataFrame(rows)
    s.to_csv(RES / "summary_e2.csv", index=False)

    fig, axes = plt.subplots(2, 1, figsize=(3.5, 3.2), sharex=True)
    for ax, v in zip(axes, ["recreate", "rolling"]):
        m = json.load(open(RES / "e2" / f"{v}_run1.json"))
        df = pd.read_csv(RES / "e2" / f"{v}_run1.csv")
        t = df.t_epoch - m["update_start_epoch"]
        for ver, c in [("v1", "tab:blue"), ("v2", "tab:green")]:
            sel = (df.status == 200) & (df.version == ver)
            ax.scatter(t[sel], df.latency_ms[sel], s=3, c=c, label=f"{ver} served")
        bad = df.status != 200
        ax.scatter(t[bad], df.latency_ms[bad], s=8, c="red", marker="x", label="failed")
        ax.axvline(0, ls="--", c="gray", lw=0.8)
        ax.axvline(m["rollout_s"], ls=":", c="gray", lw=0.8)
        ax.set_yscale("log")
        ax.set_ylim(0.5, 3000)
        ax.set_ylabel("Latency (ms)")
        ax.set_title({"recreate": "Recreate", "rolling": "RollingUpdate (maxUnavailable 0)"}[v], fontsize=8)
        ax.set_xlim(-3, max(m["rollout_s"] + 5, 20))
    axes[0].legend(fontsize=7, loc="upper right", markerscale=2)
    axes[1].set_xlabel("Time since update started (s)")
    save(fig, "e2_timeline")
    return s


# ---------------------------------------------------------------- E3 HPA
def e3():
    rows, series = [], {}
    for f in sorted(glob.glob(str(RES / "e3" / "*_run?.json"))):
        m = json.load(open(f))
        base = f[:-5]
        rep = pd.read_csv(base + "_replicas.csv")
        k6 = pd.read_csv(base + "_k6.csv", low_memory=False)
        dur = k6[k6.metric_name == "http_req_duration"].copy()
        failed = k6[(k6.metric_name == "http_req_failed") & (k6.metric_value == 1)]
        dur["t"] = dur.timestamp - m["load_start_epoch"]
        load = load_s = m["load_s"]
        # Degraded period: end of the last 10 s window (during load) whose p95 latency > 200 ms.
        w = dur[dur.t < load].assign(b=lambda d: (d.t // 10) * 10).groupby("b").metric_value.quantile(0.95)
        slow = w[w > SLOW_MS]
        degraded_s = float(slow.index.max() + 10) if len(slow) else 0.0
        first_out = rep[(rep.ready > 1)].t_s.min()
        maxr = rep.replicas.max()
        t_max = rep[rep.ready == maxr].t_s.min()
        after = rep[(rep.t_s > load) & (rep.replicas == 1)].t_s.min()
        rows.append({"variant": m["variant"], "run": m["run"],
                     "first_scale_out_s": first_out,
                     "degraded_s": degraded_s,
                     "max_replicas": maxr, "time_to_max_s": t_max,
                     "scale_in_after_load_s": (after - load) if pd.notna(after) else float("nan"),
                     "p50_ms": dur.metric_value.quantile(0.5),
                     "p95_ms": dur.metric_value.quantile(0.95),
                     "p95_first60s_ms": dur[dur.t < 60].metric_value.quantile(0.95),
                     "p95_last60s_ms": dur[(dur.t > load - 60) & (dur.t < load)].metric_value.quantile(0.95),
                     "failed": len(failed),
                     "pod_seconds": float((rep.replicas.shift().fillna(rep.replicas) * rep.t_s.diff().fillna(0)).sum())})
        series[(m["variant"], m["run"])] = (rep, dur)
    s = pd.DataFrame(rows)
    s.to_csv(RES / "summary_e3.csv", index=False)

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(3.5, 3.6), sharex=True)
    for v, c in [("hpa80", "tab:orange"), ("hpa50", "tab:purple")]:
        if (v, 1) not in series:  # run not finished yet
            continue
        rep, dur = series[(v, 1)]
        a1.step(rep.t_s, rep.ready, where="post", c=c, label=f"{v[3:]}% target")
        dur["bucket"] = (dur.t // 10) * 10
        p95 = dur.groupby("bucket").metric_value.quantile(0.95)
        a2.plot(p95.index + 5, p95.values, c=c, marker="o", ms=2)
    for a in (a1, a2):
        a.axvline(load_s, ls="--", c="gray", lw=0.8)  # end of load phase
    a1.set_ylabel("Ready replicas")
    a1.legend(fontsize=7)
    a2.set_ylabel("p95 latency (ms)")
    a2.set_yscale("log")
    a2.set_xlabel("Time since load start (s)")
    save(fig, "e3_hpa")
    return s


if __name__ == "__main__":
    md = ["# Experiment summary (mean ± std over runs)\n"]
    s1 = e1()
    md += ["## E1 Self-healing\n", agg(s1, ["failed", "downtime_s", "k8s_reported_ready_s"]).to_markdown(), "\n"]
    if glob.glob(str(RES / "e2" / "*.json")):
        s2 = e2()
        md += ["## E2 Update\n", agg(s2, ["rollout_s", "failed", "downtime_s", "p95_before_ms", "p95_during_ms",
                                          "mixed_versions_s"]).to_markdown(), "\n"]
    if glob.glob(str(RES / "e3" / "*_run?.json")):
        s3 = e3()
        md += ["## E3 HPA\n", agg(s3, ["first_scale_out_s", "degraded_s", "max_replicas", "time_to_max_s",
                                       "scale_in_after_load_s", "p50_ms", "p95_ms", "p95_first60s_ms",
                                       "p95_last60s_ms", "failed", "pod_seconds"]).to_markdown(), "\n"]
    (RES / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
