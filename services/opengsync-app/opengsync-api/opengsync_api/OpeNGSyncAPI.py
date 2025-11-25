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
    
    def authenticate(self):
        payload = {
            "api_token": self.api_token
        }
        response = requests.get(f"{self.base_url}/validate_api_token/", json=payload)
        response.raise_for_status()
        return response.json()
    
    def add_data_path(
        self,
        path: str, path_type: categories.DataPathTypeEnum,
        seq_request_id: int | None = None,
        project_id: int | None = None,
        experiment_id: int | None = None,
        library_id: int | None = None,
    ):
        """Adds a data path associated with the given ids. Checks that path exists on server and is a child of a share-directory.

        Args:
            path (str): path to the data
            path_type (categories.DataPathTypeEnum): type of the data path
            seq_request_id (int | None, optional): id of the sequencing request. Defaults to None.
            project_id (int | None, optional): id of the project. Defaults to None.
            experiment_id (int | None, optional): id of the experiment. Defaults to None.
            library_id (int | None, optional): id of the library. Defaults to None.
        Raises:
            ValueError: if none of seq_request_id, project_id, experiment_id, or library_id is provided
            requests.HTTPError: if the request fails

        Returns:
            dict: json response from the server
        """
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
        """removes all data paths associated with the given identifiers

        Args:
            project_id (int | None, optional): id of the project. Defaults to None.
            seq_request_id (int | None, optional): id of the sequencing request. Defaults to None.
            experiment_id (int | None, optional): id of the experiment. Defaults to None.
            library_id (int | None, optional): id of the library. Defaults to None.

        Raises:
            requests.HTTPError: if the request fails

        Returns:
            dict: json response from the server
        """
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

    def query_barcode_sequence(self, sequence: str, limit: int = 5) -> pd.DataFrame:
        payload = {
            "api_token": self.api_token,
            "sequence": sequence,
            "limit": limit
        }
        response = requests.post(f"{self.base_url}/api/barcodes/query_barcode_sequence/", json=payload)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"{response.status_code}: {response.text}") from e
        data = response.json()
        fc_results = pd.DataFrame(data["fc_results"])
        fc_results["orientation"] = "forward"
        rc_results = pd.DataFrame(data["rc_results"])
        rc_results["orientation"] = "rc"
        df = pd.concat([fc_results, rc_results], ignore_index=True).sort_values("hamming").reset_index(drop=True)
        df["type"] = df["type"].apply(lambda x: categories.BarcodeType.get(x["id"]))  # type: ignore
        return df
    
    def set_library_lane_reads(self, library_id: int | None, experiment_name: str, lane: int, num_reads: int, qc: dict | None = None):
        """set the number of reads (and qc metadata) for a given library lane

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
    
    def release_project_data(
        self,
        project_id: int,
        internal_access: bool,
        time_valid_min: int,
        recipients: list[str],
        anonymous_send: bool = False,
    ):
        """
        Creates temporary share-token and sends the token with instructions to recipients via email.
        Previous token is invalidated.
        Project status is updated to -> DELIVERED.

        Args:
            project_id (int): id of the project to share
            internal_access (bool): if True, add instructions for internal access
            time_valid_min (int): time in minutes for which the share is valid
            recipients (list[str]): list of email addresses to send the instructions to
            anonymous_send (bool, optional): if True, send the email anonymously. Defaults to False.

        Raises:
            requests.HTTPError: if the request fails

        Returns:
            dict: json response from the server
        """
        payload = {
            "api_token": self.api_token,
            "project_id": project_id,
            "internal_access": internal_access,
            "time_valid_min": time_valid_min,
            "recipients": recipients,
            "anonymous_send": anonymous_send,
        }
        response = requests.post(f"{self.base_url}/api/shares/release_project_data/", json=payload)
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(f"{response.status_code}: {response.text}") from e
        return response.json()
    
    def __str__(self):
        return f"OpeNGSyncAPI('{self.base_url}')"

    def __repr__(self):
        return self.__str__()