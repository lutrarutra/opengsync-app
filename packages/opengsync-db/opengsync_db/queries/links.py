import sqlalchemy as sa

from ..models import links, Protocol, Kit

def get_sample_library_link(
    sample_id: int, library_id: int,
    statement: sa.Select[tuple[links.SampleLibraryLink]] = sa.select(links.SampleLibraryLink),
) -> sa.Select[tuple[links.SampleLibraryLink]]:
    statement = statement.where(
        links.SampleLibraryLink.sample_id == sample_id,
        links.SampleLibraryLink.library_id == library_id,
    )
    return statement


def get_laned_pool_link(
    experiment_id: int, lane_num: int, pool_id: int,
    statement: sa.Select[tuple[links.LanePoolLink]] = sa.select(links.LanePoolLink),
) -> sa.Select[tuple[links.LanePoolLink]]:
    statement = statement.where(
        links.LanePoolLink.experiment_id == experiment_id,
        links.LanePoolLink.lane_num == lane_num,
        links.LanePoolLink.pool_id == pool_id,
    )
    return statement

def get_protocol_kit_links(
    protocol: Protocol, kit: Kit,
    statement: sa.Select[tuple[links.ProtocolKitLink]] = sa.select(links.ProtocolKitLink),
) -> sa.Select[tuple[links.ProtocolKitLink]]:
    statement = statement.where(
        links.ProtocolKitLink.protocol_id == protocol.id,
        links.ProtocolKitLink.kit_id == kit.id,
    )
    return statement

def get_seq_request_delivery_email_link(
    seq_request_id: int, email: str,
    statement: sa.Select[tuple[links.SeqRequestDeliveryEmailLink]] = sa.select(links.SeqRequestDeliveryEmailLink),
) -> sa.Select[tuple[links.SeqRequestDeliveryEmailLink]]:
    statement = statement.where(
        links.SeqRequestDeliveryEmailLink.seq_request_id == seq_request_id,
        links.SeqRequestDeliveryEmailLink.email == email
    )
    return statement