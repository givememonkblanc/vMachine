"""Scenario 4: Long-running async operations (VM, migrations)."""

from locust import HttpUser, task, between


class LongRunningUser(HttpUser):
    wait_time = between(5, 15)

    @task(3)
    def list_servers(self):
        self.client.get("/api/v1/compute/servers", name="List Servers")

    @task(1)
    def list_migrations(self):
        self.client.get("/api/v1/migrations", name="List Migrations")
