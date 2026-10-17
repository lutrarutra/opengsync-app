from opengsync_db import SyncSession, actions, categories as C, queries as Q

from .create_units import (
    create_user, create_seq_request, create_library,
    create_feature, create_feature_kit
)  # noqa


def test_library_features_links(session: SyncSession):
    user = create_user(session)
    request = create_seq_request(session, user)
    
    library_1 = create_library(session, user=user, seq_request=request)
    library_2 = create_library(session, user=user, seq_request=request)
    library_3 = create_library(session, user=user, seq_request=request)
    library_1.type = C.LibraryType.TENX_ANTIBODY_CAPTURE
    library_2.type = C.LibraryType.TENX_ANTIBODY_CAPTURE
    library_3.type = C.LibraryType.TENX_ANTIBODY_CAPTURE

    session.save(library_1)
    session.save(library_2)
    session.save(library_3)

    session.refresh(library_1)
    session.refresh(library_2)
    session.refresh(library_3)

    NUM_CUSTOM_FEATURES = 500
    NUM_KIT_FEATURES = 100

    for _ in range(NUM_CUSTOM_FEATURES):
        feature = create_feature(session)
        actions.link_feature_library(session, feature_id=feature.id, library_id=library_1.id)
        actions.link_feature_library(session, feature_id=feature.id, library_id=library_2.id)
        actions.link_feature_library(session, feature_id=feature.id, library_id=library_3.id)

    kit = create_feature_kit(session)
    for _ in range(NUM_KIT_FEATURES):
        feature = create_feature(session, kit=kit)
        actions.link_feature_library(session, feature_id=feature.id, library_id=library_1.id)

    for feature in kit.features:
        actions.link_feature_library(session, feature_id=feature.id, library_id=library_2.id)

    for feature in kit.features:
        actions.link_feature_library(session, feature_id=feature.id, library_id=library_3.id)

    session.refresh(library_1)
    session.refresh(library_2)
    session.refresh(library_3)
    assert len(library_1.features) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert len(library_2.features) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert len(library_3.features) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert library_1.num_features == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert library_2.num_features == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert library_3.num_features == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES

    session.delete(library_1)
    assert session.count(Q.feature.select()) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    session.delete(library_2)
    assert session.count(Q.feature.select()) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    session.delete(library_3)
    assert session.count(Q.feature.select()) == NUM_KIT_FEATURES