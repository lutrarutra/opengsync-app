import os
from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from limbless_db import models, DBSession
from limbless_db.categories import GenomeRef, LibraryType, FeatureType

from .... import logger, db
from ...TableDataForm import TableDataForm


def complete_workflow(table_data_form: TableDataForm, user_id: int, seq_request: models.SeqRequest) -> Response:
    data = table_data_form.get_data()

    library_table: pd.DataFrame = data.get("library_table")  # type: ignore
    pool_table: pd.DataFrame = data.get("pool_table")  # type: ignore
    cmo_table: Optional[pd.DataFrame] = data.get("cmo_table")  # type: ignore
    visium_table: Optional[pd.DataFrame] = data.get("visium_table")  # type: ignore
    feature_table: Optional[pd.DataFrame] = data.get("feature_table")  # type: ignore
    comment_table: Optional[pd.DataFrame] = data.get("comment_table")  # type: ignore

    n_added = 0
    n_new_samples = 0
    if feature_table is not None:
        custom_features = feature_table[feature_table["feature_id"].isna()]
        with DBSession(db) as session:
            for (feature, pattern, read, sequence), _df in custom_features.groupby(["feature", "pattern", "read", "sequence"]):
                feature = session.create_feature(
                    name=feature,
                    sequence=sequence,
                    pattern=pattern,
                    read=read,
                    type=FeatureType.ANTIBODY
                )
                feature_id = feature.id
                feature_table.loc[_df.index, "feature_id"] = feature_id

    with DBSession(db) as session:
        projects: dict[int | str, models.Project] = {}
        for project_id, project_name in library_table[["project_id", "project_name"]].drop_duplicates().values.tolist():
            if not pd.isnull(project_id):
                project_id = int(project_id)
                if (project := session.get_project(project_id)) is None:
                    raise Exception(f"Project with id {project_id} does not exist.")
                
                projects[project_id] = project
            else:
                project = session.create_project(
                    name=project_name,
                    description="",
                    owner_id=user_id
                )
                projects[project.id] = project
                library_table.loc[library_table["project_name"] == project_name, "project_id"] = project.id

        if library_table["project_id"].isna().any():
            raise Exception("Project id is None (should not be).")

    with DBSession(db) as session:
        pools: dict[str, models.Pool] = {}

        if pool_table is not None:
            for _, row in pool_table.iterrows():
                pool = session.create_pool(
                    name=row["name"],
                    owner_id=user_id,
                    seq_request_id=seq_request.id,
                    num_m_reads_requested=row["num_m_reads"] if pd.notna(row["num_m_reads"]) else None,
                    contact_name=row["contact_person_name"],
                    contact_email=row["contact_person_email"],
                    contact_phone=row["contact_person_phone"] if pd.notna(row["contact_person_phone"]) else None,
                )
                pools[row["name"]] = pool

        for (sample_name, sample_id, project_id, is_cmo_sample), _df in library_table.groupby(["sample_name", "sample_id", "project_id", "is_cmo_sample"], dropna=False):
            if cmo_table is not None:
                feature_ref = cmo_table.loc[cmo_table["sample_pool"] == sample_name, :]
            else:
                feature_ref = pd.DataFrame()
            library_samples: list[tuple[models.Sample, Optional[models.CMO]]] = []

            sample_id = int(sample_id) if not pd.isna(sample_id) else None
            project_id = int(project_id)

            if is_cmo_sample:
                for _, row in feature_ref.iterrows():
                    feature = session.get_feature(row["feature_id"])
                    sample = session.create_sample(
                        name=row["demux_name"],
                        owner_id=user_id,
                        project_id=project_id,
                    )
                    # Temporary data object
                    cmo = models.CMO(
                        sequence=feature.sequence,
                        pattern=feature.pattern,
                        read=feature.read,
                        sample_id=0,
                        library_id=0,
                    )
                    
                    library_samples.append((sample, cmo))
                    n_new_samples += 1
            else:
                
                if sample_id is None:
                    sample = session.create_sample(
                        name=sample_name,
                        project_id=project_id,
                        owner_id=user_id
                    )
                    library_samples.append((sample, None))
                    n_new_samples += 1
                else:
                    if (sample := session.get_sample(sample_id)) is None:
                        logger.error(f"Sample with id {sample_id} does not exist.")
                        raise Exception(f"Sample with id {sample_id} does not exist.")
                    library_samples.append((sample, None))

            for _, row in _df.iterrows():
                library_type = LibraryType.get(row["library_type_id"])
                genome_ref = GenomeRef.get(row["genome_id"])

                library_name = row["library_name"]
                index_kit_id = int(row["index_kit_id"]) if "index_kit_id" in row and not pd.isna(row["index_kit_id"]) else None
                adapter = row["adapter"].strip() if "adapter" in row and not pd.isna(row["adapter"]) else None
                index_1_sequence = row["index_1"].strip() if "index_1" in row and not pd.isna(row["index_1"]) else None
                index_2_sequence = row["index_2"].strip() if "index_2" in row and not pd.isna(row["index_2"]) else None
                index_3_sequence = row["index_3"].strip() if "index_3" in row and not pd.isna(row["index_3"]) else None
                index_4_sequence = row["index_4"].strip() if "index_4" in row and not pd.isna(row["index_4"]) else None

                if library_type == LibraryType.SPATIAL_TRANSCRIPTOMIC:
                    if visium_table is None:
                        raise Exception("Visium reference table not found.")    # this should not happen
                    
                    visium_row = visium_table[visium_table["library_name"] == library_name].iloc[0]
                    visium_annotation = db.create_visium_annotation(
                        area=visium_row["area"],
                        image=visium_row["image"],
                        slide=visium_row["slide"],
                    )
                    visium_annotation_id = visium_annotation.id
                else:
                    visium_annotation_id = None

                library = session.create_library(
                    name=library_name,
                    seq_request_id=seq_request.id,
                    library_type=library_type,
                    index_kit_id=index_kit_id,
                    owner_id=user_id,
                    genome_ref=genome_ref,
                    index_1_sequence=index_1_sequence if index_1_sequence else None,
                    index_2_sequence=index_2_sequence if index_2_sequence else None,
                    index_3_sequence=index_3_sequence if index_3_sequence else None,
                    index_4_sequence=index_4_sequence if index_4_sequence else None,
                    adapter=adapter if adapter else None,
                    visium_annotation_id=visium_annotation_id,
                )

                if feature_table is not None:
                    feature_ref = feature_table[feature_table["library_name"] == library_name]
                    for _, feature_row in feature_ref.iterrows():
                        if pd.isna(feature_id := feature_row["feature_id"]):
                            logger.error("Feature id is None (should not be).")
                            raise Exception("Feature id is None (should not be).")

                        _feature = session.get_feature(feature_id)
                        
                        session.link_feature_library(
                            feature_id=_feature.id,
                            library_id=library.id
                        )

                n_added += 1
            
                for sample, cmo in library_samples:
                    if cmo is not None:
                        _cmo = session.create_cmo(
                            sequence=cmo.sequence,
                            pattern=cmo.pattern,
                            read=cmo.read,
                            sample_id=sample.id,
                            library_id=library.id,
                        )
                        session.link_sample_library(
                            sample_id=sample.id,
                            library_id=library.id,
                            cmo_id=_cmo.id,
                        )
                    else:
                        session.link_sample_library(
                            sample_id=sample.id,
                            library_id=library.id,
                        )

                if "pool" in row.keys() and not pd.isna(row["pool"]):
                    session.link_library_pool(
                        library_id=library.id,
                        pool_id=pools[row["pool"]].id
                    )

    if comment_table is not None:
        for _, row in comment_table[comment_table["context"] == "visium_instructions"].iterrows():
            comment = session.create_comment(
                text=row["text"],
                author_id=user_id,
            )
            session.add_seq_request_comment(
                seq_request_id=seq_request.id,
                comment_id=comment.id
            )

    if n_added == 0:
        flash("No libraries added.", "warning")
    else:
        flash(f"Added {n_added} libraries to sequencing request.", "success")

    if os.path.exists(table_data_form.path):
        os.remove(table_data_form.path)

    return make_response(
        redirect=url_for(
            "seq_requests_page.seq_request_page", seq_request_id=seq_request.id
        )
    )