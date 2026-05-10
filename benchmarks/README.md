# vMachine Benchmark Tools

This directory contains scripts and tools for evaluating the performance of the vMachine backend platform.

## Prerequisites

1. Ensure the vMachine backend is running.
2. Install the required benchmark dependencies:
   ```bash
   pip install httpx locust psutil
   ```

## Tools

### 1. API Benchmark (`api_benchmark.py`)

Measures single-client API latency (min, max, avg, p50, p95, p99) by making sequential requests to the vMachine API endpoints.

**Usage:**
```bash
python benchmarks/api_benchmark.py --base-url http://localhost:8001
```

### 2. Load Testing (`load_test_locust.py`)

A Locust-based load testing script that simulates concurrent users making requests to the platform to measure throughput (RPS), concurrency limits, and failure rates under load.

**Usage:**
```bash
locust -f benchmarks/load_test_locust.py --host http://localhost:8001
```
Then open `http://localhost:8089` in your browser to configure and start the test.

### 3. System Monitor (`system_monitor.py`)

Logs CPU, Memory, Disk I/O, and Network I/O of the host system during a benchmark run.

**Usage:**
```bash
python benchmarks/system_monitor.py --duration 300 --interval 2
```

## Results

Use the `result_template.md` as a baseline to record your findings.

For the comprehensive performance report and architectural bottleneck analysis, see:
`docs/performance_report.md`
