from opengsync_db import categories
import requests
import pandas as pd



class OpeNGSyncAPI:
    def __init__(self, base_url, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    def get_status(self):
        response = requests.get(f"{self.base_url}/status")
        return response
    
    def add_data_path(
        self,
        path: str, path_type: categories.DataPathTypeEnum,
        seq_request_id: int | None = None,
        project_id: int | None = None,
        experiment_id: int | None = None,
        library_id: int | None = None,
    ):
        if seq_request_id is None and project_id is None and experiment_id is None and library_id is None:
            raise ValueError("At least one of seq_request_id, project_id, experiment_id, or library_id must be provided.")
        
        payload = {
            "api_token": self.api_token,
            "project_id": project_id,
            "seq_request_id": seq_request_id,
            "experiment_id": experiment_id,
            "library_id": library_id,
            "path": path,
            "path_type_id": path_type.id
        }
        response = requests.post(f"{self.base_url}/api/shares/add_data_path/", json=payload)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"{response.status_code}: {response.text}") from e
        return response.json()
    
    def remove_data_paths(
        self,
        project_id: int | None = None,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        library_id: int | None = None,
    ):
        payload = {
            "api_token": self.api_token,
            "project_id": project_id,
            "seq_request_id": seq_request_id,
            "experiment_id": experiment_id,
            "library_id": library_id,
        }
        response = requests.delete(f"{self.base_url}/api/shares/remove_data_paths/", json=payload)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"{response.status_code}: {response.text}") from e
        return response.json()

    def query_sequence_i7(self, sequence: str, limit: int = 10) -> pd.DataFrame:
        payload = {
            "api_token": self.api_token,
            "sequence": sequence,
            "limit": limit
        }
        response = requests.post(f"{self.base_url}/api/barcodes/query_sequence_i7/", json=payload)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"{response.status_code}: {response.text}") from e
        data = response.json()
        fc_results = pd.DataFrame(data["fc_results"])
        fc_results["orientation"] = "forward"
        rc_results = pd.DataFrame(data["rc_results"])
        rc_results["orientation"] = "rc"
        df = pd.concat([fc_results, rc_results], ignore_index=True).sort_values("hamming")
        df["type"] = df["type"].apply(lambda x: categories.BarcodeType.get(x["id"]))  # type: ignore
        return df
    
    def set_library_lane_reads(self, library_id: int | None, experiment_name: str, lane: int, num_reads: int, qc: dict | None = None):
        """_summary_

        Args:
            library_id (int | None): id of the library, or None for undetermined reads
            experiment_name (str): name of the experiment
            lane (int): lane number
            num_reads (int): number of reads
            qc (dict | None, optional): quality control information. Defaults to None.
        Returns:
            dict: json response from the server
        """
        payload = {
            "api_token": self.api_token,
            "library_id": library_id,
            "experiment_name": experiment_name,
            "lane": lane,
            "num_reads": num_reads,
            "qc": qc
        }
        response = requests.post(f"{self.base_url}/api/stats/set_library_lane_reads/", json=payload)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"{response.status_code}: {response.text}") from e
        return response.json()
    
    def __str__(self):
        return f"OpeNGSyncAPI('{self.base_url}')"

    def __repr__(self):
        return self.__str__()