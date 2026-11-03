"""Print button and printout heading of the plate tabs (pool page, lab prep page)."""

from opengsync_db import SyncSession

from ..db.create_units import create_lab_prep, create_plate, create_pool, create_seq_request
from ._http import OpenGSyncTestClient, get


def test_pool_plate_tab_prints_with_pool_context(client: OpenGSyncTestClient, session: SyncSession, insider, insider_token: str):
    plate = create_plate(session, insider)
    pool = create_pool(session, insider, create_seq_request(session, insider))
    pool.plate_id = plate.id
    session.commit()

    response = get(client, f"/htmx/pools/render-plate/{plate.id}", insider_token, htmx=True)
    assert response.status_code == 200, response.text
    assert f"print_div('plate-print-{plate.id}')" in response.text
    assert f'id="plate-print-{plate.id}"' in response.text
    assert f"Pool: {pool.name} - Plate: {plate.name} (0 wells)" in response.text


def test_lab_prep_plates_tab_prints_each_plate_with_lab_prep_context(client: OpenGSyncTestClient, session: SyncSession, insider, insider_token: str):
    lab_prep = create_lab_prep(session, insider)
    plates = [create_plate(session, insider), create_plate(session, insider)]
    for plate in plates:
        plate.lab_prep_id = lab_prep.id
    session.commit()

    response = get(client, f"/htmx/lab_preps/{lab_prep.id}/plates", insider_token, htmx=True)
    assert response.status_code == 200, response.text
    for plate in plates:
        # Next to the plate name, not again above the plate
        assert response.text.count(f"print_div('plate-print-{plate.id}')") == 1
        assert f"[{lab_prep.identifier}] {lab_prep.name} - Plate: {plate.name} (0 wells)" in response.text
