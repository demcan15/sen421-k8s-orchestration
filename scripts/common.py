"""Shared helpers for the experiment scripts (kubectl wrappers, reset, probe launcher)."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
K8S = ROOT / "k8s"
RESULTS = ROOT / "results"
PROBE = ROOT / "load" / "probe.py"
# Load/probe clients run as containers on the "kind" Docker network and reach the api through
# the NodePort on the control-plane node. This bypasses Docker Desktop's Windows port forwarding,
# which was found to add ~16 s of extra unavailability after a backend failure (measurement
# artefact, see README "Measurement path").
NETWORK = "kind"
URL = "http://sen421-control-plane:30080/"
PY_IMAGE = "python:3.12-slim"
K6_IMAGE = "grafana/k6:2.4.0"
K6 = shutil.which("k6") or r"C:\Program Files\k6\k6.exe"  # host binary, only for version info


def kubectl(*args, check=True, capture=True):
    r = subprocess.run(["kubectl", *args], capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed:\n{r.stderr}")
    return r.stdout


def api_pods():
    """Return list of (name, ready, deleting, creation_ts) for app=api pods."""
    data = json.loads(kubectl("get", "pods", "-l", "app=api", "-o", "json"))
    out = []
    for p in data["items"]:
        conds = {c["type"]: c["status"] for c in p["status"].get("conditions", [])}
        out.append({
            "name": p["metadata"]["name"],
            "ready": conds.get("Ready") == "True",
            "deleting": "deletionTimestamp" in p["metadata"],
            "node": p["spec"].get("nodeName", ""),
        })
    return out


def reset(manifest: str, image: str = "sen421-api:v1", replicas: int | None = None):
    """Delete the api Deployment/HPA, wait until all api pods are gone, apply a fresh variant."""
    kubectl("delete", "hpa", "api", "--ignore-not-found")
    kubectl("delete", "deploy", "api", "--ignore-not-found", "--wait=true")
    while api_pods():
        time.sleep(1)
    kubectl("apply", "-f", str(K8S / manifest))
    if image != "sen421-api:v1":
        kubectl("set", "image", "deploy/api", f"api={image}")
    if replicas is not None:
        kubectl("scale", "deploy/api", f"--replicas={replicas}")
    kubectl("rollout", "status", "deploy/api", "--timeout=180s")
    # Wait until the Service answers through the NodePort, then let things settle.
    for _ in range(60):
        r = subprocess.run(["docker", "exec", "sen421-control-plane", "curl", "-s", "-o", "/dev/null",
                            "-w", "%{http_code}", "-m", "1", "http://127.0.0.1:30080/"],
                           capture_output=True, text=True)
        if r.stdout.strip() == "200":
            break
        time.sleep(1)
    time.sleep(10)


def start_probe(out: Path, duration: float, url: str = URL, interval: float = 0.1):
    """Start probe.py in a container on the kind network; block until it has sent its first request."""
    out.parent.mkdir(parents=True, exist_ok=True)
    rel = out.relative_to(ROOT).as_posix()
    proc = subprocess.Popen(["docker", "run", "--rm", "--network", NETWORK,
                             "-v", f"{ROOT / 'load'}:/load:ro", "-v", f"{ROOT / 'results'}:/results",
                             PY_IMAGE, "python", "/load/probe.py", "--url", url, "--duration", str(duration),
                             "--interval", str(interval), "--out", f"/{rel}"])
    deadline = time.time() + 30
    while time.time() < deadline:
        if out.exists() and len(out.read_text().splitlines()) >= 2:
            break
        time.sleep(0.2)
    return proc


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))


def env_info():
    """Versions for the report's Table I."""
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, shell=isinstance(cmd, str)).stdout.strip()
        except Exception as e:  # noqa: BLE001
            return f"n/a ({e})"
    return {
        "kubectl": run(["kubectl", "version", "-o", "json"]),
        "kind": run(["kind", "version"]),
        "docker": run(["docker", "version", "--format", "{{.Server.Version}}"]),
        "k6": run([K6, "version"]),
        "python": sys.version,
        "nodes": run(["kubectl", "get", "nodes", "-o", "wide"]),
        "os": os.environ.get("OS", ""),
    }
