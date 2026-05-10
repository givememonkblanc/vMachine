# Benchmark Result Template

## Environment Details
- **Date**: [Date]
- **Target Environment**: [Local / Staging / Production OpenStack]
- **Server Specifications**: [CPU / RAM / Disk]
- **Test Duration**: [Seconds]
- **Concurrent Users**: [Number] (for Locust)

## API Latency Results (api_benchmark.py)

| API Name             | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Min (ms) | Max (ms) | Success % |
|----------------------|----------|----------|----------|----------|----------|----------|-----------|
| Health Check         |          |          |          |          |          |          |           |
| List Servers         |          |          |          |          |          |          |           |
| List Images          |          |          |          |          |          |          |           |
| List Networks        |          |          |          |          |          |          |           |
| List Volumes         |          |          |          |          |          |          |           |
| List K8s Clusters    |          |          |          |          |          |          |           |

## Load Test Results (Locust)

- **Total Requests**: [Number]
- **Requests Per Second (RPS)**: [Number]
- **Failure Rate**: [%]

## System Resource Utilization

- **Average CPU**: [%]
- **Max CPU**: [%]
- **Average Memory**: [%]
- **Max Memory**: [%]

## Notes / Observations
- [Any specific bottlenecks or errors encountered]
