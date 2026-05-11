"""Scenario 2: List Servers only — measure OpenStack Nova dependency."""

from locust import HttpUser, task, between


class ListServersUser(HttpUser):
    wait_time = between(1, 5)

    @task
    def list_servers(self):
        self.client.get("/api/v1/compute/servers", name="List Servers")
