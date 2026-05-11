"""Scenario 3: Mixed API — realistic read-only user pattern across all endpoints."""

from locust import HttpUser, task, between


class MixedAPIUser(HttpUser):
    wait_time = between(1, 5)

    @task(5)
    def health_check(self):
        self.client.get("/api/v1/health", name="Health Check")

    @task(3)
    def list_servers(self):
        self.client.get("/api/v1/compute/servers", name="List Servers")

    @task(2)
    def list_images(self):
        self.client.get("/api/v1/images", name="List Images")

    @task(2)
    def list_networks(self):
        self.client.get("/api/v1/networks", name="List Networks")

    @task(2)
    def list_volumes(self):
        self.client.get("/api/v1/volumes", name="List Volumes")

    @task(1)
    def check_migrations(self):
        self.client.get("/api/v1/migrations", name="Check Migrations")
