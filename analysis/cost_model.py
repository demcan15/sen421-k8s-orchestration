"""Estimated monthly cost of running the tested setups on Azure AKS (germanywestcentral).

The experiments themselves ran locally on kind (actual cost USD 0). This model answers:
"What would the availability gained in E1/E2 cost on a managed service?" and
"What does the lower HPA target in E3 cost in extra CPU?"

Assumptions (stated in the report):
  * 730 hours per month, pay-as-you-go list prices, no reservations/savings plans, no tax.
  * Data transfer out and the Standard Load Balancer rule charges are NOT included
    (small for this workload; to be checked in the Azure Pricing Calculator).
  * Baseline  = AKS Free tier, 1 x B2s node, 1 replica (no SLA, single point of failure).
  * Hardened  = AKS Standard tier (financially backed control-plane SLA), 3 x B2s nodes
                (one per availability zone), 3 replicas.
  * HPA cost difference = extra CPU *requested* by the extra replicas (pod-seconds x 0.1 vCPU),
    priced at the per-vCPU-hour share of a B2s node (USD 0.048 / 2 vCPU).
Usage: python analysis/cost_model.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
HOURS = 730
P = pd.read_csv(Path(__file__).with_name("prices_2026-11-17.csv")).set_index("item").price_usd


def monthly(nodes: int, control_plane_item: str):
    items = {
        "Control plane": P[control_plane_item] * HOURS,
        "Compute (B2s nodes)": nodes * P["vm_node"] * HOURS,
        "OS disks (E10)": nodes * P["os_disk"],
        "Public IP": P["public_ip"] * HOURS,
    }
    items["Total"] = sum(items.values())
    return items


def main():
    table = pd.DataFrame({
        "Baseline (Free, 1 node)": monthly(1, "aks_control_plane_free"),
        "Hardened (Standard, 3 nodes)": monthly(3, "aks_control_plane_standard"),
    }).round(2)
    table["Difference"] = (table.iloc[:, 1] - table.iloc[:, 0]).round(2)
    out = ["# Estimated monthly AKS cost (USD, list prices accessed 2026-11-17)\n", table.to_markdown(), ""]

    e3 = ROOT / "results" / "summary_e3.csv"
    if e3.exists():
        s = pd.read_csv(e3).groupby("variant").pod_seconds.agg(["mean", "std"])
        vcpu_hour = P["vm_node"] / 2
        s["cpu_request_vcpu_h_per_run"] = s["mean"] * 0.1 / 3600
        s["usd_per_run"] = s.cpu_request_vcpu_h_per_run * vcpu_hour
        # One "run" = 6-minute window (3 min load + 3 min idle). Scale to a month with
        # one such burst per hour as an illustrative pattern.
        s["usd_per_month_1_burst_per_hour"] = s.usd_per_run * HOURS
        out += ["# E3: requested CPU per load burst (one run = 180 s load + 180 s idle)\n",
                s.round(5).to_markdown(), ""]
    text = "\n".join(out)
    (ROOT / "results" / "cost_summary.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
