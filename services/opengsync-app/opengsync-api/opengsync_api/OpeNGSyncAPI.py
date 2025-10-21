import requests

class OpeNGSyncAPI:
    def __init__(self, base_url):
        self.base_url = base_url

    def get_status(self):
        response = requests.get(f"{self.base_url}/status")
        response.raise_for_status()
        return response.json()
    
    def add_share_path_to_project(self, api_token: str, project_id: int, path: str):
        payload = {
            "api_token": api_token,
            "project_id": project_id,
            "path": path
        }
        response = requests.post(f"{self.base_url}/api/shares/add_share_path_to_project", json=payload)
        response.raise_for_status()
        return response.json()