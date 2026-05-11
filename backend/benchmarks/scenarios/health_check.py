"""Scenario 1: Health Check only — measure raw FastAPI/Uvicorn throughput."""

from locust import HttpUser, task, between


class HealthCheckUser(HttpUser):
    wait_time = between(0.1, 1)

    @task
    def health_check(self):
        self.client.get("/api/v1/health", name="Health Check")
