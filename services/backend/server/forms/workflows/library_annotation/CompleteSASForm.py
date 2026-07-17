import pandas as pd
from fastapi import Depends, Response
from loguru import logger

from opengsync_db import models, categories as C, queries as Q, SyncSession, actions

from ....core import responses, exceptions as exc, dependencies
from ....utils import barcodes
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow

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
        logger.debug(self.pool_table)
        self.feature_table = self.workflow.tables.get("feature_table")
        self.library_properties_table = self.workflow.tables.get("library_properties_table")
        self.mux_type = C.MUXType.get(self.workflow.metadata["mux_type_id"]) if self.workflow.metadata["mux_type_id"] is not None else None
        self.submission_type = C.SubmissionType.get(self.workflow.header["submission_type_id"])

        self.library_table["genome_id"] = C.GenomeRef.CUSTOM.id
        for idx, row in self.library_table.iterrows():
            sample_names = self.sample_pooling_table[self.sample_pooling_table["library_name"] == row["library_name"]]["sample_name"].unique()
            sample_genome_ids = self.sample_table[self.sample_table["sample_name"].isin(sample_names)]["genome_id"].unique()
            if len(sample_genome_ids) > 1:
                logger.warning(f"{self.workflow.uuid}: Multiple genome references found for library {row['library_name']}: {sample_genome_ids}. Setting to CUSTOM.")
                continue
            elif len(sample_genome_ids) == 1:
                self.library_table.at[idx, "genome_id"] = sample_genome_ids[0]  # type: ignore
            else:
                logger.error(f"{self.workflow.uuid}: No genome reference found for library {row['library_name']}.")
                raise exc.OpeNGSyncServerException(f"No genome reference found for library {row['library_name']}.")
            
        self.library_table["genome"] = self.library_table["genome_id"].apply(lambda gid: C.GenomeRef.get(gid).display_name if pd.notna(gid) else None)

        self.abc_libraries = self.library_table[
            self.library_table["library_type_id"].isin(
                [C.LibraryType.TENX_ANTIBODY_CAPTURE.id, C.LibraryType.TENX_SC_ABC_FLEX.id]
            )
        ]["library_name"]

        if self.barcode_table is not None:
            self.barcode_table["orientation_id"] = self.barcode_table["orientation_i7_id"]
            self.barcode_table.loc[
                pd.notna(self.barcode_table["orientation_i7_id"]) &
                (self.barcode_table["orientation_i7_id"] != self.barcode_table["orientation_i5_id"]),
                "orientation_id"
            ] = None

        spatial_library_type_ids = [t.id for t in C.LibraryType.get_visium_library_types()] + [C.LibraryType.OPENST.id]
        self.contains_spatial_samples = self.library_table["library_type_id"].isin(spatial_library_type_ids).any()

        if self.contains_spatial_samples:
            if self.library_properties_table is None:
                logger.error(f"{self.workflow.uuid}: Library properties table not found for visium samples.")
                raise Exception("Library properties table not found for visium samples.")
            
            spatial_libraries = self.library_table[self.library_table["library_type_id"].isin(spatial_library_type_ids)]["library_name"].values
            self._context["spatial_table"] = self.library_properties_table[self.library_properties_table["library_name"] == spatial_libraries]
        else:
            self._context["spatial_table"] = None

        self.contains_crispr_guides = self.library_table["library_type_id"].isin([C.LibraryType.PARSE_SC_CRISPR.id]).any()

        if self.contains_crispr_guides:
            if (table := self.workflow.tables.get("crispr_guide_table")) is None:
                logger.error(f"{self.workflow.uuid}: CRISPR guide table not found for CRISPR guide samples.")
                raise Exception("CRISPR guide table not found for CRISPR guide samples.")
            
            crispr_guide_table = table[["guide_name", "target_gene", "prefix", "guide_sequence", "suffix"]].copy()
            self._context["crispr_guide_table"] = crispr_guide_table
        else:
            self._context["crispr_guide_table"] = None

        self._context["mux_type"] = self.mux_type

        if self.barcode_table is not None:
            self.barcode_table["pool"] = None
            for (library_name, pool_name), _ in self.library_table.groupby(["library_name", "pool"]):
                self.barcode_table.loc[self.barcode_table["library_name"] == library_name, "pool"] = pool_name  # type: ignore
            self.barcode_table = barcodes.check_indices(self.barcode_table, groupby="pool")
        
        self.library_table["mux_type_id"] = None
        for (library_name, mux_type_id), _df in self.sample_pooling_table.groupby(["library_name", "mux_type_id"]):
            self.library_table.loc[self.library_table["library_name"] == library_name, "mux_type_id"] = mux_type_id  # type: ignore
    
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

        for sample_name, _df in self.sample_pooling_table.groupby("sample_name"):
            sample_node = {
                "node": node_idx,
                "name": sample_name,
            }
            nodes.append(sample_node)
            node_idx += 1

            links.append({
                "source": project_node["node"],
                "target": sample_node["node"],
                "value": LINK_WIDTH_UNIT * len(self.sample_pooling_table[self.sample_pooling_table["sample_name"] == sample_name]),
            })

            for _, row in _df.iterrows():
                if row["library_name"] in library_nodes.keys():
                    library_node = library_nodes[row["library_name"]]
                else:
                    library_node = {
                        "node": node_idx,
                        "name": row['library_name'],
                    }
                    library_nodes[row["library_name"]] = library_node
                    nodes.append(library_node)
                    node_idx += 1

                    if self.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                        for _, library_row in self.library_table[self.library_table["library_name"] == row["library_name"]].iterrows():
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
                                "value": LINK_WIDTH_UNIT * len(self.sample_pooling_table[self.sample_pooling_table["library_name"] == row["library_name"]]),
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

            for idx, library_row in form.sample_table.iterrows():
                if pd.notna(library_row["sample_id"]):
                    if (sample := session.first(Q.sample.select(id=library_row["sample_id"]))) is None:
                        logger.error(f"{form.workflow.uuid}: Sample with id {library_row['sample_id']} not found.")
                        raise ValueError(f"Sample with id {library_row['sample_id']} not found.")
                else:
                    sample = session.save(Q.sample.create(
                        name=library_row["sample_name"],
                        project_id=project.id,
                        owner_id=current_user.id,
                        status=None if form.submission_type == C.SubmissionType.POOLED_LIBRARIES else C.SampleStatus.DRAFT
                    ), flush=True)
                    form.sample_table.at[idx, "sample_id"] = sample.id  # type: ignore

                for attr in C.AttributeType.as_list():
                    attr_label = f"_attr_{attr.label}"
                    if attr_label in library_row.keys() and pd.notna(library_row[attr_label]):
                        sample.set_attribute(
                            key=attr.label,
                            type=attr,
                            value=str(library_row[attr_label]),
                        )

                for attr_label in custom_sample_attributes:
                    if attr_label in library_row.keys() and pd.notna(library_row[attr_label]):
                        sample.set_attribute(
                            key=attr_label.removeprefix("_attr_"),
                            type=C.AttributeType.CUSTOM,
                            value=str(library_row[attr_label]),
                        )
                session.save(sample)

            form.sample_table["sample_id"] = form.sample_table["sample_id"].astype(int)

            if form.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                if form.pool_table is None:
                    logger.error(f"{form.workflow.uuid}: Pool table not found.")
                    raise ValueError("Pool table not found.")
                
                for idx, library_row in form.pool_table.iterrows():
                    if pd.notna(library_row["pool_id"]):
                        if (pool := session.first(Q.pool.select(id=library_row["pool_id"]))) is None:
                            logger.error(f"{form.workflow.uuid}: Pool with id {library_row['pool_id']} not found.")
                            raise ValueError(f"Pool with id {library_row['pool_id']} not found.")
                    else:
                        pool = session.save(Q.pool.create(
                            name=library_row["pool_name"],
                            owner_id=current_user.id,
                            seq_request_id=seq_request.id,
                            pool_type=C.PoolType.EXTERNAL,
                            contact_name=form.workflow.metadata["pool_contact_name"],
                            contact_email=form.workflow.metadata["pool_contact_email"],
                            contact_phone=form.workflow.metadata["pool_contact_phone"],
                            num_m_reads_requested=library_row["num_m_reads_requested"],
                            clone_number=0
                        ), flush=True)

                    form.pool_table.at[idx, "pool_id"] = pool.id  # type: ignore
                    
                form.pool_table["pool_id"] = form.pool_table["pool_id"].astype(int)

            form.library_table["library_id"] = None
            for idx, library_row in form.library_table.iterrows():
                library_type = C.LibraryType.get(library_row["library_type_id"])

                if form.library_properties_table is not None:
                    visium_row = form.library_properties_table[form.library_properties_table["library_name"] == library_row["library_name"]].iloc[0]
                    properties = dict([(k, v) for k, v in visium_row.to_dict().items() if pd.notna(v)])
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
                    pool_id = int(form.pool_table[form.pool_table["pool_label"] == library_row["pool"]]["pool_id"].values[0])
                else:
                    pool_id = None

                service_type = C.ServiceType.get(form.workflow.metadata["service_type_id"])

                library = session.save(Q.library.create(
                    name=library_row["library_name"],
                    sample_name=library_row["sample_name"],
                    seq_request_id=seq_request.id,
                    library_type=library_type,
                    owner_id=current_user.id,
                    genome_ref=C.GenomeRef.get(library_row["genome_id"]),
                    pool_id=pool_id,
                    service_type=service_type,
                    properties=properties,
                    mux_type=C.MUXType.get(library_row["mux_type_id"]) if pd.notna(library_row["mux_type_id"]) else None,
                    nuclei_isolation=form.workflow.metadata.get("nuclei_isolation", False),
                    seq_depth_requested=library_row["seq_depth"] if "seq_depth" in library_row and pd.notna(library_row["seq_depth"]) else None,
                    clone_number=0,
                    status=C.LibraryStatus.DRAFT
                ), flush=True)

                form.library_table.at[idx, "library_id"] = library.id  # type: ignore
                
                if form.submission_type == C.SubmissionType.POOLED_LIBRARIES:
                    if form.barcode_table is None:
                        logger.error(f"{form.workflow.uuid}: Barcode table not found.")
                        raise ValueError("Barcode table not found.")

                    library_barcodes = form.barcode_table[form.barcode_table["library_name"] == library_row["library_name"]]
                    if library.type == C.LibraryType.TENX_SC_ATAC:
                        if len(library_barcodes) != 4:
                            logger.warning(f"{form.workflow.uuid}: Expected 4 barcodes (i7) for TENX_SC_ATAC library, found {len(library_barcodes)}.")
                        index_type = C.IndexType.TENX_ATAC_INDEX
                    else:
                        if library_barcodes["sequence_i5"].isna().all():
                            index_type = C.IndexType.SINGLE_INDEX_I7
                        elif library_barcodes["sequence_i5"].isna().any():
                            logger.warning(f"{form.workflow.uuid}: Mixed index types found for library {library_row['library_name']}.")
                            index_type = C.IndexType.DUAL_INDEX
                        else:
                            index_type = C.IndexType.DUAL_INDEX

                    library.index_type = index_type
                    session.save(library)

                    for _, barcode_row in library_barcodes.iterrows():
                        if int(barcode_row["index_type_id"]) != index_type.id:
                            logger.error(f"{form.workflow.uuid}: Index type mismatch for library {library_row['library_name']}. Expected {index_type}, found {C.IndexType.get(barcode_row['index_type_id'])}.")
                            logger.warning(form.barcode_table)
                            logger.warning(form.library_table)

                        orientation = None
                        if pd.notna(barcode_row["orientation_i7_id"]):
                            orientation = C.BarcodeOrientation.get(int(barcode_row["orientation_i7_id"]))

                        if orientation is not None and pd.notna(barcode_row["orientation_i5_id"]):
                            if orientation.id != int(barcode_row["orientation_i5_id"]):
                                logger.error(f"{form.workflow.uuid}: Conflicting orientations for i7 and i5 in library {library_row['library_name']}.")
                                raise ValueError("Conflicting orientations for i7 and i5.")

                        library = actions.add_index_to_library(
                            session,
                            library_id=library.id,
                            sequence_i7=barcode_row["sequence_i7"] if pd.notna(barcode_row["sequence_i7"]) else None,
                            sequence_i5=barcode_row["sequence_i5"] if pd.notna(barcode_row["sequence_i5"]) else None,
                            index_kit_i7_id=barcode_row["kit_i7_id"] if pd.notna(barcode_row["kit_i7_id"]) else None,
                            index_kit_i5_id=barcode_row["kit_i5_id"] if pd.notna(barcode_row["kit_i5_id"]) else None,
                            name_i7=barcode_row["name_i7"] if pd.notna(barcode_row["name_i7"]) else None,
                            name_i5=barcode_row["name_i5"] if pd.notna(barcode_row["name_i5"]) else None,
                            orientation=orientation,
                        )

                for _, pooling_row in form.sample_pooling_table[form.sample_pooling_table["library_name"] == library_row["library_name"]].iterrows():
                    if pooling_row["mux_type_id"] == C.MUXType.TENX_FLEX_PROBE.id:
                        if form.submission_type in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and pd.isna(pooling_row["mux_barcode"]):
                            logger.error(f"{form.workflow.uuid}: Mux barcode is required for TENX_FLEX_PROBE mux type.")
                            raise ValueError("Mux barcode is required for TENX_FLEX_PROBE mux type.")
                        
                        mux = {"barcode": pooling_row["mux_barcode"]}
                    elif pooling_row["mux_type_id"] in [C.MUXType.TENX_OLIGO.id]:
                        if form.submission_type in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and pd.isna(pooling_row["mux_barcode"]):
                            logger.error(f"{form.workflow.uuid}: Mux barcode is required for TENX_OLIGO mux type.")
                            raise ValueError("Mux barcode is required for TENX_OLIGO mux type.")
                        if form.submission_type in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and pd.isna(pooling_row["mux_pattern"]):
                            logger.error(f"{form.workflow.uuid}: Mux pattern is required for TENX_OLIGO mux type.")
                            raise ValueError("Mux pattern is required for TENX_OLIGO mux type.")
                        if form.submission_type in [C.SubmissionType.POOLED_LIBRARIES, C.SubmissionType.UNPOOLED_LIBRARIES] and pd.isna(pooling_row["mux_read"]):
                            logger.error(f"{form.workflow.uuid}: Mux read is required for TENX_OLIGO mux type.")
                            raise ValueError("Mux read is required for TENX_OLIGO mux type.")
                        
                        mux = {
                            "barcode": pooling_row["mux_barcode"],
                            "pattern": pooling_row["mux_pattern"],
                            "read": pooling_row["mux_read"]
                        }

                    elif pooling_row["mux_type_id"] == C.MUXType.TENX_ON_CHIP.id:
                        mux = {"barcode": pooling_row["mux_barcode"]}
                    elif pooling_row["mux_type_id"] == C.MUXType.TENX_ABC_HASH.id:
                        mux = {
                            "barcode": pooling_row["mux_barcode"],
                            "pattern": pooling_row["mux_pattern"],
                            "read": pooling_row["mux_read"]
                        }
                    elif pooling_row["mux_type_id"] == C.MUXType.PARSE_WELLS.id:
                        mux = { "barcode": pooling_row["mux_barcode"] }
                    else:
                        mux = None
                    
                    sample_ids = form.sample_table[form.sample_table["sample_name"] == pooling_row["sample_name"]]["sample_id"].values
                    if len(sample_ids) != 1:
                        logger.error(f"{form.workflow.uuid}: Expected exactly one sample for name {pooling_row['sample_name']}, found {len(sample_ids)}.")
                        logger.error(form.library_table)
                        logger.error(form.sample_table)
                        logger.error(form.sample_pooling_table)
                        raise ValueError(f"Expected exactly one sample for name {pooling_row['sample_name']}, found {len(sample_ids)}.")
                    actions.link_sample_library(session, sample_id=sample_ids[0], library_id=library.id, mux=mux)

            form.library_table["library_id"] = form.library_table["library_id"].astype(int)

            if form.feature_table is not None:
                custom_features = form.feature_table[form.feature_table["feature_id"].isna()]
                for (identifier, feature, pattern, read, sequence), _df in custom_features.groupby(["identifier", "feature", "pattern", "read", "sequence"], dropna=False):
                    feature = session.save(Q.feature.create(
                        identifier=identifier if pd.notna(identifier) else None,  # type: ignore
                        name=feature,  # type: ignore
                        sequence=sequence,  # type: ignore
                        pattern=pattern,  # type: ignore
                        read=read,  # type: ignore
                        type=C.FeatureType.ANTIBODY
                    ), flush=True)
                    form.feature_table.loc[_df.index, "feature_id"] = feature.id

                form.feature_table["feature_id"] = form.feature_table["feature_id"].astype(int)
                
                for _, library_row in form.library_table.iterrows():
                    mask = (
                        (form.feature_table["library_name"] == library_row["library_name"]) |
                        form.feature_table["library_name"].isna()
                    )
                    if len(ids := form.feature_table[mask]["feature_id"].values.tolist()) > 0:
                        for feature_id in ids:
                            session.save(models.links.LibraryFeatureLink(
                                library_id=int(library_row["library_id"]),
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
                elif context == "i7_option":
                    seq_request.comments.append(Q.comment.create(text=text, author=current_user))
                elif context == "i5_option":
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