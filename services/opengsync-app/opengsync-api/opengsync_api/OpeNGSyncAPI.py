from opengsync_db import categories
import requests
import pandas as pd



class OpeNGSyncAPI:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def get_status(self):
        response = requests.get(f"{self.base_url}/status")
        return response
    
    def add_share_path_to_project(self, project_id: int, path: str):
        payload = {
            "api_token": "",
            "project_id": project_id,
            "path": path
        }
        response = requests.post(f"{self.base_url}/api/shares/add_share_path_to_project/", json=payload)
        response.raise_for_status()
        return response.json()

    def query_sequence_i7(self, sequence: str, limit: int = 10) -> pd.DataFrame:
        payload = {
            "api_token": "",
            "sequence": sequence,
            "limit": limit
        }
        response = requests.post(f"{self.base_url}/api/barcodes/query_sequence_i7/", json=payload)
        response.raise_for_status()
        data = response.json()
        fc_results = pd.DataFrame(data["fc_results"])
        fc_results["orientation"] = "forward"
        rc_results = pd.DataFrame(data["rc_results"])
        rc_results["orientation"] = "rc"
        df = pd.concat([fc_results, rc_results], ignore_index=True).sort_values("hamming")
        df["type"] = df["type"].apply(lambda x: categories.BarcodeType.get(x["id"]))  # type: ignore
        return df