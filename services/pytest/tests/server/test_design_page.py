"""Design page: the page and its htmx-loaded lists render with designs present."""

import pytest

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C

from ..db.create_units import create_flow_cell_design, create_pool_design, create_todo_comment
from ._http import get


@pytest.fixture
def designs(session: SyncSession, user):
    active = create_flow_cell_design(session)
    typed = create_flow_cell_design(session)
    typed.stored_flow_cell_type = C.FlowCellType.NOVASEQ_6K_S4
    archived = create_flow_cell_design(session)
    archived.task_status = C.TaskStatus.ARCHIVED
    pd = create_pool_design(session)
    pd.flow_cell_design = active
    create_todo_comment(session, user, flow_cell_design_id=active.id)
    create_todo_comment(session, user, pool_design_id=pd.id)
    create_pool_design(session)  # orphan
    session.commit()
    return active, archived


@pytest.mark.parametrize("path", [
    "/design/",
    "/htmx/flow_cell_design/flow-cells",
    "/htmx/flow_cell_design/archived-flow-cells",
    "/htmx/pool_design/render-pool-designs",
])
def test_design_views_render(client: TestClient, insider_token: str, designs, path: str):
    response = get(client, path, insider_token, htmx=path.startswith("/htmx"))
    assert response.status_code == 200, response.text


def test_pool_design_list_for_flow_cell_renders(client: TestClient, insider_token: str, designs):
    active, _ = designs
    response = get(client, f"/htmx/pool_design/render-pool-designs?flow_cell_design_id={active.id}", insider_token, htmx=True)
    assert response.status_code == 200, response.text
