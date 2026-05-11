#!/usr/bin/env python3
"""
vMachine Locust Load Test — Scenario Runner

This file is a DISPATCHER that delegates to per-scenario files under scenarios/.
Use the scenario files directly for actual test execution:

  locust -f benchmarks/scenarios/health_check.py ...
  locust -f benchmarks/scenarios/list_servers.py ...
  locust -f benchmarks/scenarios/mixed_api.py ...
  locust -f benchmarks/scenarios/long_running.py ...

See scenarios/*.py for individual User class definitions.
"""

import sys
import os

SCENARIO_MAP = {
    "health": "health_check",
    "servers": "list_servers",
    "mixed": "mixed_api",
    "long": "long_running",
}


def main():
    print(__doc__)
    print("\nAvailable scenarios:")
    for key, name in SCENARIO_MAP.items():
        print(f"  {key}: benchmarks/scenarios/{name}.py")


if __name__ == "__main__":
    main()
