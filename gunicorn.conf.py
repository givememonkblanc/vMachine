"""Gunicorn configuration for vMachine production deployment.

Architecture
-----------
Nginx (0.0.0.0:8083) → Gunicorn (127.0.0.1:8002) → FastAPI workers

Worker formula: (2 × CPU cores) + 1 = 65, but capped at 8 workers.
Benchmarked 4/8/16 — 8 is the sweet spot for this 32-core, 31 GB host:
  - Memory: ~80 MB/worker → 8 workers = ~680 MB (2.1% of 31 GB)
  - Cache efficiency: fewer workers = warmer per-worker caches
  - OpenStack throttling: remote API is bottleneck, not local workers
  - Headroom: leaves resources for Phase 2 (Redis) and Phase 3 (PostgreSQL)
"""

import multiprocessing
import os

# ---------------------------------------------------------------------------
# Server socket
# ---------------------------------------------------------------------------
# Listen on loopback only — Nginx is the public face on port 8001.
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8002")
backlog = int(os.getenv("GUNICORN_BACKLOG", "2048"))

# ---------------------------------------------------------------------------
# Worker processes
# ---------------------------------------------------------------------------
# FastAPI requires an ASGI worker — UvicornWorker provides this.
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "uvicorn.workers.UvicornWorker")

# Formula: (2 × CPU) + 1 = 65.  Cap at 8 (benchmark-validated).
_cores = multiprocessing.cpu_count()
_recommended = _cores * 2 + 1
_default_workers = min(_recommended, 8)
workers = int(os.getenv("GUNICORN_WORKERS", str(_default_workers)))

# Restart workers periodically to prevent memory leaks.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "10000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "1000"))

worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "1000"))

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
# OpenStack SDK calls are the slowest path (~500 ms).  Set timeout > slowest
# expected response but low enough to fail-fast on hung workers.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# ---------------------------------------------------------------------------
# Preload
# ---------------------------------------------------------------------------
# Import the app once in the master before forking workers.  Saves memory
# through copy-on-write.  CAUTION: do NOT open DB/Redis connections at import
# time — use FastAPI lifespan handlers instead.
preload_app = True

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
accesslog = os.getenv("GUNICORN_ACCESSLOG", "-")  # stdout
errorlog = os.getenv("GUNICORN_ERRORLOG", "-")    # stderr
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = os.getenv(
    "GUNICORN_ACCESS_LOG_FORMAT",
    '%(h)s "%(r)s" %(s)s %(b)s %(D)sμs "%(f)s" "%(a)s"',
)

# ---------------------------------------------------------------------------
# Process naming
# ---------------------------------------------------------------------------
proc_name = "vMachine-api"

# ---------------------------------------------------------------------------
# Security: drop privileges after binding (requires root → user transition).
# ---------------------------------------------------------------------------
# Only enable if running as root (e.g. in Docker with `--user`).
# In systemd the service runs as `ryzen395` already.
# user = "ryzen395"
# group = "ryzen395"

# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def on_starting(server):
    """Log the number of workers on startup."""
    server.log.info(
        "Starting vMachine Gunicorn: %d workers (%d CPU cores), backend %s",
        server.cfg.workers,
        _cores,
        bind,
    )


def worker_abort(worker):
    worker.log.info("Worker %s aborted (PID %d)", worker.pid, worker.age)


def when_ready(server):
    server.log.info("vMachine API ready — accepting requests via Nginx")
