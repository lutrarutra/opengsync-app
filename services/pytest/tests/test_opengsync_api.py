import pytest
import requests

from unittest.mock import Mock, patch

from pydantic import SecretStr

from opengsync_api import OpeNGSyncAPI


def test_project_software_client_methods():
    response = Mock()
    response.json.return_value = {"result": "success"}
    api = OpeNGSyncAPI("https://example.test/", SecretStr("token"))

    with patch("requests.post", return_value=response) as post:
        assert api.add_project_software(12, " Software ", "v1", "comment") == {"result": "success"}

    post.assert_called_once_with(
        "https://example.test/api/projects/add-software",
        json={
            "project_id": 12,
            "software": " Software ",
            "version": "v1",
            "comment": "comment",
        },
        headers={"X-API-Token": "token"},
    )

    with patch("requests.delete", return_value=response) as delete:
        assert api.delete_project_software(12, " Software ") == {"result": "success"}

    delete.assert_called_once_with(
        "https://example.test/api/projects/delete-software",
        json={"project_id": 12, "software": " Software "},
        headers={"X-API-Token": "token"},
    )


def test_get_project_data_paths_client_method():
    response = Mock()
    response.json.return_value = ["/projects/project"]
    api = OpeNGSyncAPI("https://example.test/", SecretStr("token"))

    with patch("requests.get", return_value=response) as get:
        assert api.get_project_data_paths(12) == ["/projects/project"]

    get.assert_called_once_with(
        "https://example.test/api/projects/12/data-paths",
        headers={"X-API-Token": "token"},
    )


def test_client_parses_json_error_detail():
    response = Mock()
    response.status_code = 400
    response.text = '{"detail":"Data path cannot be resolved."}'
    response.json.return_value = {"detail": "Data path cannot be resolved."}
    response.raise_for_status.side_effect = requests.HTTPError("400 Client Error")
    api = OpeNGSyncAPI("https://example.test/", SecretStr("token"))

    with (
        patch("requests.get", return_value=response),
        pytest.raises(requests.HTTPError, match="400: Data path cannot be resolved\\."),  # type: ignore[attr-defined]
    ):
        api.get_project_data_paths(12)
