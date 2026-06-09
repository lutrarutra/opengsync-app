from opengsync_db import SyncDBHandler, categories as C, queries as Q

from .create_units import (
    create_user, create_seq_request, create_library,
    create_feature, create_feature_kit
)  # noqa


def test_library_features_links(db: SyncDBHandler):
    user = create_user(db)
    request = create_seq_request(db, user)
    
    library_1 = create_library(db, user=user, seq_request=request)
    library_2 = create_library(db, user=user, seq_request=request)
    library_3 = create_library(db, user=user, seq_request=request)
    library_1.type = C.LibraryType.TENX_ANTIBODY_CAPTURE
    library_2.type = C.LibraryType.TENX_ANTIBODY_CAPTURE
    library_3.type = C.LibraryType.TENX_ANTIBODY_CAPTURE

    db.session.save(library_1)
    db.session.save(library_2)
    db.session.save(library_3)

    db.session.refresh(library_1)
    db.session.refresh(library_2)
    db.session.refresh(library_3)

    NUM_CUSTOM_FEATURES = 500
    NUM_KIT_FEATURES = 100

    for _ in range(NUM_CUSTOM_FEATURES):
        feature = create_feature(db)
        db.actions.link_feature_library(feature_id=feature.id, library_id=library_1.id)
        db.actions.link_feature_library(feature_id=feature.id, library_id=library_2.id)
        db.actions.link_feature_library(feature_id=feature.id, library_id=library_3.id)

    kit = create_feature_kit(db)
    for _ in range(NUM_KIT_FEATURES):
        feature = create_feature(db, kit=kit)
        db.actions.link_feature_library(feature_id=feature.id, library_id=library_1.id)

    for feature in kit.features:
        db.actions.link_feature_library(feature_id=feature.id, library_id=library_2.id)

    for feature in kit.features:
        db.actions.link_feature_library(feature_id=feature.id, library_id=library_3.id)

    db.session.refresh(library_1)
    db.session.refresh(library_2)
    db.session.refresh(library_3)
    assert len(library_1.features) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert len(library_2.features) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert len(library_3.features) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert library_1.num_features == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert library_2.num_features == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert library_3.num_features == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES

    db.session.delete(library_1)
    assert db.session.count(Q.feature.select()) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    db.session.delete(library_2)
    assert db.session.count(Q.feature.select()) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    db.session.delete(library_3)
    assert db.session.count(Q.feature.select()) == NUM_KIT_FEATURES