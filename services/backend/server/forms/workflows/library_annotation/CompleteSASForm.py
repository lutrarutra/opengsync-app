from loguru import logger
import pandas as pd
from fastapi import Depends, Response
from pydantic import BaseModel

from opengsync_db import models, categories as C, queries as Q, SyncSession, actions

from ....core import responses, exceptions as exc, dependencies
from ....utils import barcodes, parsing
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep

class LibraryTableRow(BaseModel):
    sample_name: str
    library_name: str
    library_type_id: int
    genome_id: int
    _raw_: dict[str, object]
    pool: str | None = None
    mux_type_id: int | None = None
    seq_depth: float | None = None

class PoolTableRow(BaseModel):
    pool_name: str
    pool_id: int | None = None
    num_m_reads_requested: float | None = None

class BarcodeTableRow(BaseModel):
    library_name: str
    index_type_id: int
    sequence_i7: str | None
    sequence_i5: str | None
    name_i7: str | None
    name_i5: str | None
    kit_i7_id: int | None
    kit_i5_id: int | None
    orientation_i7_id: int | None
    orientation_i5_id: int | None

class SamplePoolingTableRow(BaseModel):
    library_name: str
    sample_name: str
    mux_barcode: str | None = None
    mux_pattern: str | None = None
    mux_read: str | None = None
    mux_type_id: int | None = None


class CompleteSASForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-complete.html"

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.library_table = self.workflow.tables["library_table"]
        self.sample_table = self.workflow.tables["sample_table"]
        self.sample_pooling_table = self.workflow.tables["sample_pooling_table"]
        self.barcode_table = self.workflow.tables.get("barcode_table")
        self.pool_table = self.workflow.tables.get("pool_table")
        self.feature_table = self.workflow.tables.get("feature_table")
        self.library_properties_table = self.workflow.tables.get("library_properties_table")
        self.mux_type = C.MUXType.get(self.workflow.metadata["mux_type_id"]) if self.workflow.metadata["mux_type_id"] is not None else None
        self.submission_type = C.SubmissionType.get(self.workflow.header["submission_type_id"])

        self.library_table["genome_id"] = C.GenomeRef.CUSTOM.id
        for idx, row in parsing.safe_iter(self.library_table, LibraryTableRow):
            sample_names = self.sample_pooling_table[self.sample_pooling_table["library_name"] == row.library_name]["sample_name"].unique()  # type: ignore
            sample_genome_ids = self.sample_table[self.sample_table["sample_name"].isin(sample_names)]["genome_id"].unique()  # type: ignore
            if len(sample_genome_ids) > 1:
                logger.warning(f"{self.workflow.uuid}: Multiple genome references found for library {row.library_name}: {sample_genome_ids}. Setting to CUSTOM.")
                continue
            elif len(sample_genome_ids) == 1:
                self.library_table.at[idx, "genome_id"] = sample_genome_ids[0]  # type: ignore
            else:
                logger.error(f"{self.workflow.uuid}: No genome reference found for library {row.library_name}.")
                raise exc.OpeNGSyncServerException(f"No genome reference found for library {row.library_name}.")
            
        self.library_table["genome"] = self.library_table["genome_id"].apply(lambda gid: C.GenomeRef.get(gid).display_name if pd.notna(gid) else None)

        self.abc_libraries = self.library_table[
            self.library_table["library_type_id"].isin([C.LibraryType.TENX_ANTIBODY_CAPTURE.id, C.LibraryType.TENX_SC_ABC_FLEX.id])
        ]["library_name"]

        if self.barcode_table is not None:
            # Same rule as saving: the i7 orientation, unless i7 and i5 are both set and differ
            self.barcode_table["orientation_id"] = self.barcode_table["orientation_i7_id"]
            self.barcode_table.loc[
                pd.notna(self.barcode_table["orientation_i7_id"]) &
                pd.notna(self.barcode_table["orientation_i5_id"]) &
                (self.barcode_table["orientation_i7_id"] != self.barcode_table["orientation_i5_id"]),
                "orientation_id"
            ] = None

        spatial_library_type_ids = [t.id for t in C.LibraryType.get_visium_library_types()] + [C.LibraryType.OPENST.id]
        contains_spatial_samples = bool(self.library_table["library_type_id"].isin(spatial_library_type_ids).any())

        if contains_spatial_samples:
            if self.library_properties_table is None:
                logger.error(f"{self.workflow.uuid}: Library properties table not found for visium samples.")
                raise exc.OpeNGSyncServerException("Library properties table not found for visium samples.")
            
            spatial_libraries = self.library_table[self.library_table["library_type_id"].isin(spatial_library_type_ids)]["library_name"].values  # type: ignore
            self._context["spatial_table"] = self.library_properties_table[self.library_properties_table["library_name"] == spatial_libraries]
        else:
            self._context["spatial_table"] = None

        contains_crispr_guides = bool(self.library_table["library_type_id"].isin([C.LibraryType.PARSE_SC_CRISPR.id]).any())

        if contains_crispr_guides:
            if (table := self.workflow.tables.get("crispr_guide_table")) is None:
                logger.error(f"{self.workflow.uuid}: CRISPR guide table not found for CRISPR guide samples.")
                raise exc.OpeNGSyncServerException("CRISPR guide table not found for CRISPR guide samples.")
            
            crispr_guide_table = table[["guide_name", "target_gene", "prefix", "guide_sequence", "suffix"]].copy()
            self._context["crispr_guide_table"] = crispr_guide_table
        else:
            self._context["crispr_guide_table"] = None

        self._context["mux_type"] = self.mux_type

        if self.barcode_table is not None:
            self.barcode_table["pool"] = None

            class LibraryPoolGroup(BaseModel):
                library_name: str
                pool: str

            for group, _ in parsing.safe_groupby(self.library_table, LibraryPoolGroup):
                self.barcode_table.loc[self.barcode_table["library_name"] == group.library_name, "pool"] = group.pool

            self.barcode_table = barcodes.check_indices(self.barcode_table, groupby="pool")
        
        self.library_table["mux_type_id"] = None
        class SamplePoolingLibraryMuxGroup(BaseModel):
            library_name: str
            mux_type_id: int

        for group, _ in parsing.safe_groupby(self.sample_pooling_table, SamplePoolingLibraryMuxGroup, dropna=True):
            self.library_table.loc[self.library_table["library_name"] == group.library_name, "mux_type_id"] = group.mux_type_id
    
    def prepare(self):
        self._context["library_table"] = self.library_table
        self._context["sample_table"] = self.sample_table
        self._context["sample_pooling_table"] = self.sample_pooling_table
        self._context["barcode_table"] = self.barcode_table
        self._context["feature_table"] = self.feature_table
        self._context["library_properties_table"] = self.library_properties_table
        self._context["pool_table"] = self.pool_table

        LINK_WIDTH_UNIT = 1
        nodes = []
        links = []

        project_node = {
            "node": 0,
            "name": self.workflow.metadata["project_title"],
        }
        nodes.append(project_node)
        node_idx = 1
        pool_nodes = {}

        library_nodes = {}

        class SamplePoolingSampleNameGroup(BaseModel):
            sample_name: str

        class LibraryNameRow(BaseModel):
            library_name: str

        for group, _df in parsing.safe_groupby(self.sample_pooling_table, SamplePoolingSampleNameGroup):
            sample_node = {
                "node": node_idx,
                "name": group.sample_name,
            }
            nodes.append(sample_node)
            node_idx += 1

            links.append({
                "source": project_node["node"],
                "target": sample_node["node"],
                "value": LINK_WIDTH_UNIT * len(self.sample_pooling_table[self.sample_pooling_table["sample_name"] == group.sample_name]),
            })

            for _, row in parsing.safe_iter(_df, LibraryNameRow):
                if row.library_name in library_nodes:
                    library_node = library_nodes[row.library_name]
                else:
                    library_node = {
                        "node": node_idx,
                        "name": row.library_name,
                    }
                    library_nodes[row.library_name] = library_node
                    nodes.append(library_node)
                    node_idx += 1

                    if self.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                        for _, library_row in self.library_table[self.library_table["library_name"] == row.library_name].iterrows():
                            if (pool_node := pool_nodes.get(library_row["pool"])) is None:
                                pool_node = {
                                    "node": node_idx,
                                    "name": library_row["pool"],
                                }
                                nodes.append(pool_node)
                                node_idx += 1
                                pool_nodes[library_row["pool"]] = pool_node

                            links.append({
                                "source": library_node["node"],
                                "target": pool_node["node"],
                                "value": LINK_WIDTH_UNIT * len(self.sample_pooling_table[self.sample_pooling_table["library_name"] == row.library_name]),
                            })

                links.append({
                    "source": sample_node["node"],
                    "target": library_node["node"],
                    "value": LINK_WIDTH_UNIT,
                })

        self._context["nodes"] = nodes
        self._context["links"] = links
    
    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: CompleteSASForm = Depends(CompleteSASForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
            _ = Depends(dependencies.audit_log),
        ) -> Response:
            
            seq_request = session.get_one(Q.seq_request.select(id=form.workflow.seq_request_id))

            if (project_id := form.workflow.metadata.get("project_id")) is not None:
                if (project := session.first(Q.project.select(id=project_id))) is None:
                    logger.error(f"{form.workflow.uuid}: Project with id {project_id} not found.")
                    raise ValueError(f"Project with id {project_id} not found.")
            else:
                project = session.save(Q.project.create(
                    title=form.workflow.metadata["project_title"],
                    description=form.workflow.metadata["project_description"],
                    owner_id=int(form.workflow.metadata["project_owner_id"]),
                    group_id=seq_request.group_id
                ), flush=True)

            predefined_attrs = [f"_attr_{attr.label}" for attr in C.AttributeType.as_list()]
            custom_sample_attributes = [attr for attr in form.sample_table.columns if attr.startswith("_attr_") and attr not in predefined_attrs]

            class SampleTableRow(BaseModel):
                sample_id: int | None
                sample_name: str
                _raw_: dict[str, object]

            for idx, row in parsing.safe_iter(form.sample_table, SampleTableRow):
                if row.sample_id is not None:
                    sample = session.get_one(Q.sample.select(id=row.sample_id))
                else:
                    sample = session.save(Q.sample.create(
                        name=row.sample_name,
                        project_id=project.id,
                        owner_id=current_user.id,
                        status=None if form.submission_type == C.SubmissionType.POOLED_LIBRARIES else C.SampleStatus.DRAFT
                    ), flush=True)
                    form.sample_table.at[idx, "sample_id"] = sample.id

                for attr in C.AttributeType.as_list():
                    attr_label = f"_attr_{attr.label}"
                    if attr_label in row._raw_ and bool(pd.notna(row._raw_[attr_label])):
                        sample.set_attribute(
                            key=attr.label,
                            type=attr,
                            value=str(row._raw_[attr_label]),
                        )

                for attr_label in custom_sample_attributes:
                    if attr_label in row._raw_ and bool(pd.notna(row._raw_[attr_label])):
                        sample.set_attribute(
                            key=attr_label.removeprefix("_attr_"),
                            type=C.AttributeType.CUSTOM,
                            value=str(row._raw_[attr_label]),
                        )
                session.save(sample)

            form.sample_table["sample_id"] = form.sample_table["sample_id"].astype(int)

            if form.submission_type == C.SubmissionType.POOLED_LIBRARIES:

                if form.pool_table is None:
                    logger.error(f"{form.workflow.uuid}: Pool table not found.")
                    raise ValueError("Pool table not found.")
                
                for idx, row in parsing.safe_iter(form.pool_table, PoolTableRow):
                    if row.pool_id is not None:
                        pool = session.get_one(Q.pool.select(id=row.pool_id))
                    else:
                        pool = session.save(Q.pool.create(
                            name=row.pool_name,
                            owner_id=current_user.id,
                            seq_request_id=seq_request.id,
                            pool_type=C.PoolType.EXTERNAL,
                            contact_name=form.workflow.metadata["pool_contact_name"],
                            contact_email=form.workflow.metadata["pool_contact_email"],
                            contact_phone=form.workflow.metadata["pool_contact_phone"],
                            num_m_reads_requested=row.num_m_reads_requested,
                            clone_number=0
                        ), flush=True)

                    form.pool_table.at[idx, "pool_id"] = pool.id
                    
                form.pool_table["pool_id"] = form.pool_table["pool_id"].astype(int)

            form.library_table["library_id"] = None
            for idx, row in parsing.safe_iter(form.library_table, LibraryTableRow):
                library_type = C.LibraryType.get(row.library_type_id)

                if form.library_properties_table is not None:
                    visium_row = form.library_properties_table[form.library_properties_table["library_name"] == row.library_name].iloc[0]
                    properties = {k: v for k, v in visium_row.to_dict().items() if pd.notna(v)}
                    properties.pop("library_name", None)
                    properties.pop("sample_name", None)
                else:
                    properties = None

                if library_type == C.LibraryType.PARSE_SC_CRISPR:
                    if (crispr_guide_table := form.workflow.tables.get("crispr_guide_table")) is None:
                        logger.error(f"{form.workflow.uuid}: CRISPR guide table not found.")
                        raise ValueError("CRISPR guide table not found.")
                    
                    if properties is None:
                        properties = {}

                    properties["crispr_guides"] = crispr_guide_table.to_dict(orient="records")

                if form.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                    if form.pool_table is None:
                        logger.error(f"{form.workflow.uuid}: Pool table not found.")
                        raise ValueError("Pool table not found.")
                    pool_id = int(form.pool_table[form.pool_table["pool_label"] == row.pool]["pool_id"].values[0])  # type: ignore
                else:
                    pool_id = None

                service_type = C.ServiceType.get(form.workflow.metadata["service_type_id"])

                library = session.save(Q.library.create(
                    name=row.library_name,
                    sample_name=row.sample_name,
                    seq_request_id=seq_request.id,
                    library_type=library_type,
                    owner_id=current_user.id,
                    genome_ref=C.GenomeRef.get(row.genome_id),
                    pool_id=pool_id,
                    service_type=service_type,
                    properties=properties,
                    mux_type=C.MUXType.get(row.mux_type_id) if row.mux_type_id is not None else None,
                    nuclei_isolation=form.workflow.metadata.get("nuclei_isolation", False),
                    seq_depth_requested=row.seq_depth if row.seq_depth is not None else None,
                    clone_number=0,
                    status=C.LibraryStatus.DRAFT
                ), flush=True)

                form.library_table.at[idx, "library_id"] = library.id
                
                if form.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                    if form.barcode_table is None:
                        logger.error(f"{form.workflow.uuid}: Barcode table not found.")
                        raise ValueError("Barcode table not found.")

                    library_barcodes: pd.DataFrame = form.barcode_table[form.barcode_table["library_name"] == row.library_name]  # type: ignore
                    if library.type == C.LibraryType.TENX_SC_ATAC:
                        if len(library_barcodes) != 4:
                            logger.warning(f"{form.workflow.uuid}: Expected 4 barcodes (i7) for TENX_SC_ATAC library, found {len(library_barcodes)}.")
                        index_type = C.IndexType.TENX_ATAC_INDEX
                    else:
                        if library_barcodes["sequence_i5"].isna().all():  # type: ignore
                            index_type = C.IndexType.SINGLE_INDEX_I7
                        elif library_barcodes["sequence_i5"].isna().any():  # type: ignore
                            logger.warning(f"{form.workflow.uuid}: Mixed index types found for library {row.library_name}.")
                            index_type = C.IndexType.DUAL_INDEX
                        else:
                            index_type = C.IndexType.DUAL_INDEX

                    library.index_type = index_type
                    session.save(library)

                    for _, barcode_row in parsing.safe_iter(library_barcodes, BarcodeTableRow):
                        if barcode_row.index_type_id != index_type.id:
                            logger.error(f"{form.workflow.uuid}: Index type mismatch for library {row.library_name}. Expected {index_type}, found {C.IndexType.get(barcode_row.index_type_id)}.")
                            logger.warning(form.barcode_table)
                            logger.warning(form.library_table)

                        orientation = None
                        if barcode_row.orientation_i7_id is not None:
                            orientation = C.BarcodeOrientation.get(barcode_row.orientation_i7_id)

                        if orientation is not None and barcode_row.orientation_i5_id is not None:
                            if orientation.id != barcode_row.orientation_i5_id:
                                logger.error(f"{form.workflow.uuid}: Conflicting orientations for i7 and i5 in library {row.library_name}.")
                                raise exc.OpeNGSyncServerException("Conflicting orientations for i7 and i5.")

                        library = actions.add_index_to_library(
                            session,
                            library_id=library.id,
                            sequence_i7=barcode_row.sequence_i7,
                            sequence_i5=barcode_row.sequence_i5,
                            index_kit_i7_id=barcode_row.kit_i7_id,
                            index_kit_i5_id=barcode_row.kit_i5_id,
                            name_i7=barcode_row.name_i7,
                            name_i5=barcode_row.name_i5,
                            orientation=orientation,
                        )

                sample_pool_table: pd.DataFrame = form.sample_pooling_table[form.sample_pooling_table["library_name"] == row.library_name]  # type: ignore
                for _, pooling_row in parsing.safe_iter(sample_pool_table, SamplePoolingTableRow):
                    if pooling_row.mux_type_id == C.MUXType.TENX_FLEX_PROBE.id:
                        if form.submission_type in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and pooling_row.mux_barcode is None:
                            logger.error(f"{form.workflow.uuid}: Mux barcode is required for TENX_FLEX_PROBE mux type.")
                            raise exc.OpeNGSyncServerException("Mux barcode is required for TENX_FLEX_PROBE mux type.")
                        
                        mux = {"barcode": pooling_row.mux_barcode}
                    elif pooling_row.mux_type_id in [C.MUXType.TENX_OLIGO.id]:
                        if form.submission_type in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and pooling_row.mux_barcode is None:
                            logger.error(f"{form.workflow.uuid}: Mux barcode is required for TENX_OLIGO mux type.")
                            raise exc.OpeNGSyncServerException("Mux barcode is required for TENX_OLIGO mux type.")
                        if form.submission_type in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and pooling_row.mux_pattern is None:
                            logger.error(f"{form.workflow.uuid}: Mux pattern is required for TENX_OLIGO mux type.")
                            raise exc.OpeNGSyncServerException("Mux pattern is required for TENX_OLIGO mux type.")
                        if form.submission_type in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and pooling_row.mux_read is None:
                            logger.error(f"{form.workflow.uuid}: Mux read is required for TENX_OLIGO mux type.")
                            raise exc.OpeNGSyncServerException("Mux read is required for TENX_OLIGO mux type.")
                        
                        mux = {
                            "barcode": pooling_row.mux_barcode,
                            "pattern": pooling_row.mux_pattern,
                            "read": pooling_row.mux_read
                        }

                    elif pooling_row.mux_type_id == C.MUXType.TENX_ON_CHIP.id:
                        mux = {"barcode": pooling_row.mux_barcode}
                    elif pooling_row.mux_type_id == C.MUXType.TENX_ABC_HASH.id:
                        mux = {
                            "barcode": pooling_row.mux_barcode,
                            "pattern": pooling_row.mux_pattern,
                            "read": pooling_row.mux_read
                        }
                    elif pooling_row.mux_type_id == C.MUXType.PARSE_WELLS.id:
                        mux = { "barcode": pooling_row.mux_barcode }
                    else:
                        mux = None
                    
                    sample_ids = form.sample_table[form.sample_table["sample_name"] == pooling_row.sample_name]["sample_id"].values  # type: ignore
                    if len(sample_ids) != 1:
                        logger.error(f"{form.workflow.uuid}: Expected exactly one sample for name {pooling_row.sample_name}, found {len(sample_ids)}.")
                        logger.error(form.library_table)
                        logger.error(form.sample_table)
                        logger.error(form.sample_pooling_table)
                        raise ValueError(f"Expected exactly one sample for name {pooling_row.sample_name}, found {len(sample_ids)}.")
                    actions.link_sample_library(session, sample_id=sample_ids[0], library_id=library.id, mux=mux)

            form.library_table["library_id"] = form.library_table["library_id"].astype(int)

            if form.feature_table is not None:
                custom_features: pd.DataFrame = form.feature_table[form.feature_table["feature_id"].isna()]  # type: ignore

                class FeatureGroup(BaseModel):
                    identifier: str | None
                    feature: str
                    pattern: str
                    read: str
                    sequence: str

                for group, _df in parsing.safe_groupby(custom_features, FeatureGroup):
                    feature = session.save(Q.feature.create(
                        identifier=group.identifier,
                        name=group.feature,
                        sequence=group.sequence,
                        pattern=group.pattern,
                        read=group.read,
                        type=C.FeatureType.ANTIBODY
                    ), flush=True)
                    form.feature_table.loc[_df.index, "feature_id"] = feature.id

                form.feature_table["feature_id"] = form.feature_table["feature_id"].astype(int)
                
                for _, library_row in parsing.safe_iter(form.library_table, LibraryTableRow):
                    mask = (
                        (form.feature_table["library_name"] == library_row.library_name) |
                        form.feature_table["library_name"].isna()
                    )
                    if len(ids := form.feature_table[mask]["feature_id"].values.tolist()) > 0:  # type: ignore
                        for feature_id in ids:
                            session.save(models.links.LibraryFeatureLink(
                                library_id=library_row._raw_["library_id"],
                                feature_id=feature_id
                            ), flush=True)
                
            for comment in form.workflow.get_comments():
                context = comment["context"]
                text = comment["comment"]

                if context == "visium_instructions":
                    seq_request.comments.append(Q.comment.create(text=f"Visium data instructions: {text}", author=current_user))
                elif context == "custom_genome_reference":
                    seq_request.comments.append(Q.comment.create(text=f"Custom genome reference: {text}", author=current_user))
                elif context == "assay_tech_selection":
                    seq_request.comments.append(Q.comment.create(text=f"Additional info from assay selection: {text}", author=current_user))
                elif context == "i7_option" or context == "i5_option":
                    seq_request.comments.append(Q.comment.create(text=text, author=current_user))
                elif context == "parse_chemistry":
                    seq_request.comments.append(Q.comment.create(text=f"Parse Chemistry: {text}", author=current_user))
                elif context == "parse_kit":
                    seq_request.comments.append(Q.comment.create(text=f"Parse Kit: {text}", author=current_user))
                elif context == "i7_primer":
                    seq_request.comments.append(Q.comment.create(text=f"i7 Primer Sequence: {text}", author=current_user))
                elif context == "i5_primer":
                    seq_request.comments.append(Q.comment.create(text=f"i5 Primer Sequence: {text}", author=current_user))
                else:
                    seq_request.comments.append(Q.comment.create(text=context.replace("_", " ").capitalize() + ": " + text, author=current_user))

            form.workflow.tables["sample_table"] = form.sample_table
            form.workflow.tables["library_table"] = form.library_table
            if form.library_properties_table is not None:
                form.workflow.tables["library_properties_table"] = form.library_properties_table
            if form.sample_pooling_table is not None:
                form.workflow.tables["sample_pooling_table"] = form.sample_pooling_table

            logger.info(f"{form.workflow.uuid}: added libraries to sequencing request.")

            # newdir = os.path.join("/media", C.MediaFileType.LIBRARY_ANNOTATION.dir, str(seq_request.id))
            # os.makedirs(newdir, exist_ok=True)
            form.workflow.complete()
            return responses.htmx_response(
                redirect=responses.url_for("seq_request_page", seq_request_id=seq_request.id),
                flash=responses.flash(f"Added {form.library_table.shape[0]} libraries to sequencing request.", "success")
            )
        return route