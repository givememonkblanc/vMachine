# VMware Assessment Benchmark Results

> Generated: 2026-05-11 01:12:14 UTC
> Environment: AMD RYZEN AI MAX+ PRO 395 w/ Radeon 8060S
> Memory: 31.1 GB total

## Summary

| VM Count | Compatibility | Mapping (cold) | Mapping (warm) | Plan Generation | Parallel (concurrency=10) |
|----------|:-------------:|:--------------:|:--------------:|:---------------:|:-------------------------:|
| 10       |     0.10 ms |     0.24 ms |     0.17 ms |     0.11 ms |     0.53 ms |
| 50       |     0.36 ms |     0.89 ms |     0.81 ms |     0.37 ms |     1.91 ms |
| 100      |     0.58 ms |     1.47 ms |     1.38 ms |     0.61 ms |    12.11 ms |
| 500      |     2.60 ms |     6.90 ms |     6.87 ms |     3.64 ms |    28.67 ms |

## 10 VMs — Detail

### Latency (ms)

| Operation | Avg | p50 | p95 | p99 | Min | Max | Throughput |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---------:|
| Compatibility Check                           |     0.10 |     0.08 |     0.16 |     0.16 |     0.07 |     0.16 |  31756.1 VM/s |
| Parallel (concurrency=10)                     |     0.53 |     0.51 |     0.65 |     0.65 |     0.44 |     0.65 |   6236.0 VM/s |
| Plan Generation                               |     0.11 |     0.08 |     0.16 |     0.16 |     0.07 |     0.16 |  31017.4 VM/s |
| Resource Mapping                              |     0.24 |     0.18 |     0.36 |     0.36 |     0.17 |     0.36 |  14092.4 VM/s |
| Resource Mapping (warm cache)                 |     0.17 |     0.17 |     0.18 |     0.18 |     0.17 |     0.18 |  19124.1 VM/s |

### Memory Profile

| Metric | Value |
|--------|:-----:|
| RSS Before | 70.8 MB |
| RSS After  | 71.2 MB |
| Delta      | +0.4 MB |

## 50 VMs — Detail

### Latency (ms)

| Operation | Avg | p50 | p95 | p99 | Min | Max | Throughput |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---------:|
| Compatibility Check                           |     0.36 |     0.32 |     0.46 |     0.46 |     0.31 |     0.46 |  45985.5 VM/s |
| Parallel (concurrency=10)                     |     1.91 |     1.82 |     2.12 |     2.12 |     1.79 |     2.12 |   8736.7 VM/s |
| Plan Generation                               |     0.37 |     0.36 |     0.42 |     0.42 |     0.34 |     0.42 |  44607.0 VM/s |
| Resource Mapping                              |     0.89 |     0.93 |     0.93 |     0.93 |     0.82 |     0.93 |  18697.2 VM/s |
| Resource Mapping (warm cache)                 |     0.81 |     0.81 |     0.82 |     0.82 |     0.80 |     0.82 |  20615.2 VM/s |

### Memory Profile

| Metric | Value |
|--------|:-----:|
| RSS Before | 71.3 MB |
| RSS After  | 72.8 MB |
| Delta      | +1.5 MB |

## 100 VMs — Detail

### Latency (ms)

| Operation | Avg | p50 | p95 | p99 | Min | Max | Throughput |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---------:|
| Compatibility Check                           |     0.58 |     0.56 |     0.63 |     0.63 |     0.56 |     0.63 |  57090.7 VM/s |
| Parallel (concurrency=10)                     |    12.11 |     3.35 |    29.86 |    29.86 |     3.11 |    29.86 |   2752.9 VM/s |
| Plan Generation                               |     0.61 |     0.58 |     0.69 |     0.69 |     0.57 |     0.69 |  54389.2 VM/s |
| Resource Mapping                              |     1.47 |     1.43 |     1.57 |     1.57 |     1.41 |     1.57 |  22673.7 VM/s |
| Resource Mapping (warm cache)                 |     1.38 |     1.37 |     1.40 |     1.40 |     1.37 |     1.40 |  24107.4 VM/s |

### Memory Profile

| Metric | Value |
|--------|:-----:|
| RSS Before | 72.9 MB |
| RSS After  | 75.2 MB |
| Delta      | +2.4 MB |

## 500 VMs — Detail

### Latency (ms)

| Operation | Avg | p50 | p95 | p99 | Min | Max | Throughput |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---------:|
| Compatibility Check                           |     2.60 |     2.54 |     2.73 |     2.73 |     2.53 |     2.73 |  64077.1 VM/s |
| Parallel (concurrency=10)                     |    28.67 |    18.09 |    51.63 |    51.63 |    16.28 |    51.63 |   5813.6 VM/s |
| Plan Generation                               |     3.64 |     3.20 |     4.54 |     4.54 |     3.20 |     4.54 |  45726.4 VM/s |
| Resource Mapping                              |     6.90 |     6.88 |     7.05 |     7.05 |     6.78 |     7.05 |  24149.2 VM/s |
| Resource Mapping (warm cache)                 |     6.87 |     6.81 |     7.00 |     7.00 |     6.81 |     7.00 |  24247.0 VM/s |

### Memory Profile

| Metric | Value |
|--------|:-----:|
| RSS Before | 76.1 MB |
| RSS After  | 89.5 MB |
| Delta      | +13.4 MB |

---

## API Compatibility Note

**Breaking change**: The `/api/v1/vmware/assess/{vm_id}/compatibility` endpoint
previously returned `VMCompatibilityResult` with flat boolean fields
(`os_supported`, `cpu_compatible`, `memory_compatible`, `disk_compatible`,
`network_compatible`, `power_state`). It now returns `ScoredCompatibilityResult`
with:

- `score` (float 0.0–1.0) — composite compatibility score
- `issues` (list of `{severity, category, message, compatible}`) — detailed
  per-check results
- `summary` — human-readable one-liner

Old clients consuming the flat fields must migrate to the new `issues[]` format.
The `VMCompatibilityResult` model is preserved in the schema module for
backward-reference but is no longer used by any endpoint.
