"""HTMX table sorting on hybrid count columns (count subqueries have no column name).

The sort state comes back in the header (``aria-sort``) and in the state the address bar mirrors
(``data-url-state``), so the header can toggle and a reload keeps the order.
"""

import re

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession

from ..db.create_units import create_user, create_project, create_seq_request
from ._http import get


@pytest.mark.parametrize("field, create", [  # type: ignore[attr-defined]
    ("num_projects", create_project),
    ("num_seq_requests", create_seq_request),
])
@pytest.mark.parametrize("order", ["asc", "desc"])  # type: ignore[attr-defined]
def test_user_table_sorts_by_count_column(
    client: TestClient, session: SyncSession, insider_token: str, field: str, create, order: str,
):
    users = []
    for n in (2, 0, 1):
        user = create_user(session)
        for _ in range(n):
            create(session, user)
        users.append((n, user.email))
    session.commit()

    response = get(client, f"/htmx/users/render-table-page?order_by={field}:{order}&limit=100", token=insider_token, htmx=True)
    assert response.status_code == 200
    html = response.text

    expected = [email for _, email in sorted(users, reverse=order == "desc")]
    positions = [html.index(email) for email in expected]
    assert positions == sorted(positions)

    # sort state is echoed back so the header can toggle and a reload keeps the order
    aria = "ascending" if order == "asc" else "descending"
    assert re.search(rf'data-col="{field}"\s+aria-sort="{aria}"', html)
    assert f"&#34;order_by&#34;: &#34;{field}:{order}&#34;" in html
