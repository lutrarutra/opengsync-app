"""Q.pd.match_barcodes_to_kit: a kit matches only if it contains every given sequence of the barcode type."""

import uuid

from opengsync_db import SyncSession, models, categories as C, queries as Q

BT = C.BarcodeType


def _kit(session: SyncSession, adapters: list[list[tuple[C.BarcodeType, str]]]) -> models.IndexKit:
    _uuid = str(uuid.uuid4())
    kit = session.save(Q.index_kit.create(
        name=_uuid, identifier=_uuid[:12], type=C.IndexType.DUAL_INDEX, supported_protocol_ids=[],
    ), flush=True)
    for n, barcodes in enumerate(adapters):
        adapter = session.save(Q.adapter.create(index_kit=kit, well=f"A{n + 1}"), flush=True)
        for barcode_type, sequence in barcodes:
            session.save(Q.barcode.create(
                name=f"{barcode_type.name}_{n}", sequence=sequence, well=f"A{n + 1}", type=barcode_type, adapter=adapter,
            ), flush=True)
    session.flush()
    return kit


def _matches(session: SyncSession, sequences: list[str], barcode_type: C.BarcodeType) -> set[int]:
    unique = list(set(sequences))
    df = session.get_pandas(Q.pd.match_barcodes_to_kit(unique, len(unique), barcode_type.id), limit=None)
    return set(df["kit_id"]) if not df.empty else set()


def _seq() -> str:
    return uuid.uuid4().hex[:10].upper().translate(str.maketrans("0123456789BDEF", "ACGTACGTACGTAC"))


def test_kit_containing_all_sequences_matches(session: SyncSession):
    a, b, c, i5 = _seq(), _seq(), _seq(), _seq()
    kit = _kit(session, [[(BT.INDEX_I7, a), (BT.INDEX_I5, i5)], [(BT.INDEX_I7, b), (BT.INDEX_I5, i5)], [(BT.INDEX_I7, c), (BT.INDEX_I5, i5)]])

    assert _matches(session, [a, b], BT.INDEX_I7) == {kit.id}
    assert _matches(session, [a, a, b, c], BT.INDEX_I7) == {kit.id}
    # i5 shared by all adapters: one distinct sequence
    assert _matches(session, [i5], BT.INDEX_I5) == {kit.id}


def test_kit_missing_one_sequence_does_not_match(session: SyncSession):
    a, b = _seq(), _seq()
    _kit(session, [[(BT.INDEX_I7, a), (BT.INDEX_I5, _seq())]])

    assert _matches(session, [a, b], BT.INDEX_I7) == set()


def test_sequences_spread_over_two_kits_match_neither(session: SyncSession):
    a, b = _seq(), _seq()
    _kit(session, [[(BT.INDEX_I7, a), (BT.INDEX_I5, _seq())]])
    _kit(session, [[(BT.INDEX_I7, b), (BT.INDEX_I5, _seq())]])

    assert _matches(session, [a, b], BT.INDEX_I7) == set()


def test_barcode_type_must_match(session: SyncSession):
    a, b = _seq(), _seq()
    kit = _kit(session, [[(BT.INDEX_I7, a), (BT.INDEX_I5, b)]])

    assert _matches(session, [b], BT.INDEX_I7) == set()
    assert _matches(session, [a, b], BT.INDEX_I7) == set()
    assert _matches(session, [b], BT.INDEX_I5) == {kit.id}


def test_every_kit_containing_the_sequences_matches(session: SyncSession):
    a = _seq()
    k1 = _kit(session, [[(BT.INDEX_I7, a), (BT.INDEX_I5, _seq())]])
    k2 = _kit(session, [[(BT.INDEX_I7, a), (BT.INDEX_I5, _seq())], [(BT.INDEX_I7, _seq()), (BT.INDEX_I5, _seq())]])

    assert _matches(session, [a], BT.INDEX_I7) == {k1.id, k2.id}
