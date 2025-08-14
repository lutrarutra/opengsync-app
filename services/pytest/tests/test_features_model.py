from opengsync_db import DBHandler

from .create_units import (
    create_user, create_seq_request, create_library,
    create_feature, create_feature_kit
)  # noqa


def test_library_features_links(db: DBHandler):
    user = create_user(db)
    request = create_seq_request(db, user)
    
    library_1 = create_library(db, user=user, seq_request=request)
    library_2 = create_library(db, user=user, seq_request=request)
    library_3 = create_library(db, user=user, seq_request=request)

    NUM_CUSTOM_FEATURES = 500
    NUM_KIT_FEATURES = 100

    for _ in range(NUM_CUSTOM_FEATURES):
        feature = create_feature(db)
        db.link_feature_library(feature_id=feature.id, library_id=library_1.id)
        db.link_feature_library(feature_id=feature.id, library_id=library_2.id)
        db.link_feature_library(feature_id=feature.id, library_id=library_3.id)

    kit = create_feature_kit(db)
    for _ in range(NUM_KIT_FEATURES):
        feature = create_feature(db, kit=kit)
        db.link_feature_library(feature_id=feature.id, library_id=library_1.id)

    db.link_features_library(
        feature_ids=[f.id for f in kit.features],
        library_id=library_2.id
    )
    db.link_features_library(
        feature_ids=[f.id for f in kit.features],
        library_id=library_3.id
    )

    db.refresh(library_1)
    db.refresh(library_2)
    db.refresh(library_3)
    assert len(library_1.features) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert len(library_2.features) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert len(library_3.features) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert library_1.num_features == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert library_2.num_features == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    assert library_3.num_features == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES

    db.delete_library(library_1.id)
    assert len(db.get_features(limit=None)[0]) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    db.delete_library(library_2.id)
    assert len(db.get_features(limit=None)[0]) == NUM_CUSTOM_FEATURES + NUM_KIT_FEATURES
    db.delete_library(library_3.id)
    assert len(db.get_features(limit=None)[0]) == NUM_KIT_FEATURES