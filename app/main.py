"""Small multi-container demo API for the SEN421 Kubernetes project.

Endpoints:
  GET /         -> increments a Redis counter, returns version + pod name
  GET /health   -> liveness/readiness check (also checks Redis)
  GET /cpu      -> fixed CPU work (?n= SHA-256 rounds, default 150,000 ~= 50 ms) to drive the HPA
  GET /version  -> returns APP_VERSION
"""
import hashlib
import os
import socket
import time

import redis
from flask import Flask, jsonify, request

APP_VERSION = os.getenv("APP_VERSION", "v1")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
STARTUP_DELAY_S = float(os.getenv("STARTUP_DELAY_S", "0"))

# Simulate an application that needs time to warm up (e.g. loading config/caches).
# This makes the effect of readiness probes visible.
time.sleep(STARTUP_DELAY_S)

app = Flask(__name__)
r = redis.Redis(host=REDIS_HOST, port=6379, socket_connect_timeout=1, socket_timeout=1)
POD = socket.gethostname()


@app.get("/")
def index():
    try:
        hits = r.incr("hits")
    except redis.RedisError:
        hits = -1
    return jsonify(version=APP_VERSION, pod=POD, hits=hits)


@app.get("/health")
def health():
    try:
        r.ping()
        return jsonify(status="ok"), 200
    except redis.RedisError:
        return jsonify(status="redis-unavailable"), 503


@app.get("/cpu")
def cpu():
    # Fixed amount of work (not a fixed duration): if the pod is CPU-throttled or overloaded,
    # the request really takes longer. 150,000 SHA-256 rounds ~= 50 ms of unthrottled CPU
    # (calibrated in python:3.12-slim on the test host).
    n = min(int(request.args.get("n", 150_000)), 2_000_000)
    h = b"x" * 64
    for _ in range(n):
        h = hashlib.sha256(h).digest()
    return jsonify(pod=POD, rounds=n)


@app.get("/version")
def version():
    return jsonify(version=APP_VERSION, pod=POD)
