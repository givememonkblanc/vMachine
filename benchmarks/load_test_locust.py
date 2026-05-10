import time
from locust import HttpUser, task, between

class VMachineUser(HttpUser):
    wait_time = between(1, 5)
    
    @task(5)
    def health_check(self):
        self.client.get("/api/v1/health", name="Health Check")
        
    @task(3)
    def list_servers(self):
        self.client.get("/api/v1/compute/servers", name="List Servers")
        
    @task(2)
    def list_images(self):
        self.client.get("/api/v1/image/images", name="List Images")
        
    @task(2)
    def list_networks(self):
        self.client.get("/api/v1/network/networks", name="List Networks")
        
    @task(2)
    def list_volumes(self):
        self.client.get("/api/v1/storage/volumes", name="List Volumes")
        
    @task(1)
    def simulate_vmware_migration_check(self):
        self.client.get("/api/v1/orchestration/migrations", name="Check Migrations")
