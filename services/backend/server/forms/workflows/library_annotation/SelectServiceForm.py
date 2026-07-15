import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, categories as C

from ....core import responses, exceptions as exc
from ....components import inputs
from ..HTMXWorkflowStep import HTMXWorkflowStep
from ...HTMXForm import RouteFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .DefineMultiplexedSamplesForm import DefineMultiplexedSamplesForm
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .CustomAssayAnnotationForm import CustomAssayAnnotationForm

class OptionalAssaysForm(SubHTMXForm):
    vdj_b = inputs.boolean.CheckboxInputField("VDJ-B")
    vdj_t = inputs.boolean.CheckboxInputField("VDJ-T")
    vdj_t_gd = inputs.boolean.CheckboxInputField("VDJ-T-GD")
    crispr_screening = inputs.boolean.CheckboxInputField("CRISPR Screening")
    antibody_capture = inputs.boolean.CheckboxInputField("Cell Surface Protein Quantification")
    antibody_multiplexing = inputs.boolean.CheckboxInputField("+ Sample Multiplexing with Antibody-based Cell Hashing", description="Multiple samples per library with antibody-based cell tagging. Only available with cell surface protein capture.")
    antibody_capture_kit = inputs.string.StringInputField("Antibody Capture Kit", description="Specify the antibody capture kit used for cell surface protein quantification.", max_length=64)

    parse_mux = inputs.boolean.CheckboxInputField("Multiple Samples per Sub-Library", description="Multiple samples per library with Parse Biosciences multiplexing. Only available with Parse Biosciences assays.")
    parse_mux = inputs.boolean.CheckboxInputField("Multiple Samples per Sub-Library", description="Multiple samples per sub-library with Parse Biosciences multiplexing technology.")
    parse_tcr = inputs.boolean.CheckboxInputField(C.LibraryType.PARSE_EVERCODE_TCR.name)
    parse_bcr = inputs.boolean.CheckboxInputField(C.LibraryType.PARSE_EVERCODE_BCR.name)
    parse_crispr = inputs.boolean.CheckboxInputField(C.LibraryType.PARSE_SC_CRISPR.name)

    Parse_kits = [(1, "WT_mini"), (2, "WT"), (3, "WT_mega"), (4, "WT_mega_384"), (5, "WT_penta"), (6, "WT_penta_384")]
    parse_kit = inputs.selectable.SelectableInputField("Parse Kit", Parse_kits)

    Parse_chemistries = [(1, "v1"), (2, "v2"), (3, "v3")]
    parse_chemistry = inputs.selectable.SelectableInputField("Parse Chemistry", Parse_chemistries)

class AdditionalSerevicesForm(SubHTMXForm):
    oligo_multiplexing = inputs.boolean.CheckboxInputField("Sample Multiplexing using Antibody/Oligo-based Cell Tagging for 10X Libraries", description="Multiple samples per library with oligo-based cell tagging, e.g. CMO/HTO/LMO/Antibodies..")
    oligo_multiplexing_kit = inputs.string.StringInputField("Multiplexing Kit", description="Multiplexing Kit", max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH)
    ocm_multiplexing = inputs.boolean.CheckboxInputField("On-Chip Multiplexing for 10X GEM-X Libraries", description="Multiple samples per library using 10X On-Chip Multiplexing")
    nuclei_isolation = inputs.boolean.CheckboxInputField("Nuclei Isolation")


class SelectServiceForm(HTMXWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-select_service.html"

    service_type = inputs.selectable.SelectableInputField("Assay Type", C.ServiceType.as_selectable())
    additional_info = inputs.string.TextAreaInputField("Additional Information", description="Please provide any additional information about the assay or library preparation that may be relevant for processing.", max_length=4096, required=False)
    optional_assays = OptionalAssaysForm()
    additional_services = AdditionalSerevicesForm()

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.submission_type = C.SubmissionType.get(workflow.header["submission_type_id"])

    @property
    def post_url(self) -> responses.URL:
        return SelectServiceForm.PostURL(
            SelectServiceForm.Submit, prefix="LibraryAnnotationWorkflow", seq_request_id=self.workflow.seq_request_id
        ).include_query_params(uuid=self.workflow.uuid)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Previous(cls.__name__)),
            form: SelectServiceForm = Depends(SelectServiceForm.Init()),
        ) -> Response:
            # form.spreadsheet.set_data(workflow.tables["sample_table"])
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def dependency(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
            form: SelectServiceForm = Depends(SelectServiceForm.Validate()),
        ) -> Response:
            try:
                service_type = C.ServiceType.get(int(form.service_type.data))
            except ValueError:
                form.service_type.errors.append("Invalid assay type")
                raise exc.FormValidationException(form)
            
            if service_type == C.ServiceType.PARSE:
                if form.optional_assays.parse_kit.data == -1:
                    form.optional_assays.parse_kit.errors.append("Please select a Parse kit.")
                if form.optional_assays.parse_chemistry.data == -1:
                    form.optional_assays.parse_chemistry.errors.append("Please select a Parse chemistry.")
            
            if form.optional_assays.antibody_capture.data and not form.optional_assays.antibody_capture_kit.data:
                form.optional_assays.antibody_capture_kit.errors.append("Please specify an antibody capture kit.")
            
            if form.additional_services.oligo_multiplexing.data and not form.additional_services.oligo_multiplexing_kit.data:
                form.additional_services.oligo_multiplexing_kit.errors.append("Please specify a multiplexing kit.")

            if form.optional_assays.antibody_multiplexing.data and not form.optional_assays.antibody_capture.data:
                form.optional_assays.antibody_multiplexing.errors.append("Antibody-based cell hashing multiplexing requires cell surface protein capture.")

            if form.optional_assays.antibody_multiplexing.data and form.additional_services.oligo_multiplexing.data:
                form.optional_assays.antibody_multiplexing.errors.append("Please select only one multiplexing method.")
                form.additional_services.oligo_multiplexing.errors.append("Please select only one multiplexing method.")

            if form.optional_assays.antibody_multiplexing.data and form.additional_services.ocm_multiplexing.data:
                form.optional_assays.antibody_multiplexing.errors.append("Please select only one multiplexing method.")
                form.additional_services.ocm_multiplexing.errors.append("Please select only one multiplexing method.")

            if form.additional_services.oligo_multiplexing.data and form.additional_services.ocm_multiplexing.data:
                form.additional_services.oligo_multiplexing_kit.errors.append("Please select only one multiplexing method.")
                form.additional_services.ocm_multiplexing.errors.append("Please select only one multiplexing method.")

            if form.optional_assays.parse_mux.data and service_type != C.ServiceType.PARSE:
                form.optional_assays.parse_mux.errors.append("Parse Biosciences multiplexing is only available with Parse Biosciences assays.")

            if form.optional_assays.parse_mux.data and (form.additional_services.oligo_multiplexing.data or form.additional_services.ocm_multiplexing.data or form.optional_assays.antibody_multiplexing.data):
                form.optional_assays.parse_mux.errors.append("Please select only one multiplexing method.")

            if form.optional_assays.antibody_multiplexing.data and service_type in C.ServiceType.get_flex_services():
                form.optional_assays.antibody_multiplexing.errors.append("Antibody-based cell hashing multiplexing is not available with 10X Flex assays.")
            
            if form.errors:
                raise exc.FormValidationException(form)
            
            oligo_multiplexing = form.additional_services.oligo_multiplexing.data
            ocm_multiplexing = form.additional_services.ocm_multiplexing.data
            antibody_multiplexing = form.optional_assays.antibody_multiplexing.data
            flex_barcode_multiplexing = service_type in [C.ServiceType.TENX_SC_4_PLEX_FLEX, C.ServiceType.TENX_SC_16_PLEX_FLEX, C.ServiceType.TENX_SC_FLEX_V2]
            parse_multiplexing = form.optional_assays.parse_mux.data
            
            workflow.metadata["service_type_id"] = service_type.id
            workflow.metadata["mux_type_id"] = None
            workflow.metadata["oligo_multiplexing_kit"] = form.additional_services.oligo_multiplexing_kit.data
            workflow.metadata["antibody_capture_kit"] = form.optional_assays.antibody_capture_kit.data
            workflow.metadata["antibody_multiplexing"] = form.optional_assays.antibody_multiplexing.data

            if oligo_multiplexing:
                workflow.metadata["mux_type_id"] = C.MUXType.TENX_OLIGO.id
            elif ocm_multiplexing:
                workflow.metadata["mux_type_id"] = C.MUXType.TENX_ON_CHIP.id
            elif flex_barcode_multiplexing:
                workflow.metadata["mux_type_id"] = C.MUXType.TENX_FLEX_PROBE.id
            elif antibody_multiplexing:
                workflow.metadata["mux_type_id"] = C.MUXType.TENX_ABC_HASH.id
            elif parse_multiplexing:
                workflow.metadata["mux_type_id"] = C.MUXType.PARSE_WELLS.id
                
            workflow.metadata["nuclei_isolation"] = form.additional_services.nuclei_isolation.data
            workflow.metadata["antibody_capture"] = form.optional_assays.antibody_capture.data

            workflow.metadata["vdj_b"] = form.optional_assays.vdj_b.data
            workflow.metadata["vdj_t"] = form.optional_assays.vdj_t.data
            workflow.metadata["vdj_t_gd"] = form.optional_assays.vdj_t_gd.data
            workflow.metadata["crispr_screening"] = form.optional_assays.crispr_screening.data
            workflow.metadata["additional_info"] = form.additional_info.data

            workflow.metadata["parse_kit"] = form.optional_assays.parse_kit.data
            workflow.metadata["parse_chemistry"] = form.optional_assays.parse_chemistry.data
            workflow.metadata["parse_crispr"] = form.optional_assays.parse_crispr.data
            workflow.metadata["parse_tcr"] = form.optional_assays.parse_tcr.data
            workflow.metadata["parse_bcr"] = form.optional_assays.parse_bcr.data

            if form.additional_services.oligo_multiplexing_kit.data:
                workflow.add_comment(context="oligo_multiplexing_kit", text=form.additional_services.oligo_multiplexing_kit.data)

            if form.optional_assays.antibody_capture_kit.data:
                workflow.add_comment(context="antibody_capture_kit", text=form.optional_assays.antibody_capture_kit.data)

            if form.additional_info.data:
                workflow.add_comment(context="assay_tech_selection", text=form.additional_info.data)
            
            if (parse_chemistry := dict(OptionalAssaysForm.Parse_chemistries).get(form.optional_assays.parse_chemistry.data)) is not None:
                workflow.add_comment(context="parse_chemistry", text=parse_chemistry)

            if (parse_kit := dict(OptionalAssaysForm.Parse_kits).get(form.optional_assays.parse_kit.data)) is not None:
                workflow.add_comment(context="parse_kit", text=parse_kit)

            if DefineMultiplexedSamplesForm.is_applicable(workflow):
                next_form = DefineMultiplexedSamplesForm(workflow)
                return next_form.make_response()

            sample_table = workflow.tables["sample_table"]
            
            if service_type == C.ServiceType.CUSTOM:
                sample_pooling_table = {
                    "sample_pool": [],
                    "sample_name": [],
                }
                for (sample_name,), _ in sample_table.groupby(["sample_name"], sort=False):
                    sample_pooling_table["sample_pool"].append(sample_name)
                    sample_pooling_table["sample_name"].append(sample_name)
                    
                sample_pooling_table = pd.DataFrame(sample_pooling_table)
                workflow.tables["sample_pooling_table"] = sample_pooling_table
                next_form = CustomAssayAnnotationForm(workflow)
                return next_form.make_response()
            
            library_table_data = {
                "library_name": [],
                "sample_name": [],
                "library_type": [],
                "library_type_id": [],
            }

            sample_pooling_table = {
                "sample_name": [],
                "library_name": [],
                "sample_pool": [],
            }

            def add_library(sample_name: str, library_type: C.LibraryType):
                library_name = f"{sample_name}_{library_type.identifier}"

                sample_pooling_table["sample_name"].append(sample_name)
                sample_pooling_table["library_name"].append(library_name)
                sample_pooling_table["sample_pool"].append(sample_name)

                library_table_data["library_name"].append(library_name)
                library_table_data["sample_name"].append(sample_name)
                library_table_data["library_type"].append(library_type.name)
                library_table_data["library_type_id"].append(library_type.id)

            for _, row in sample_table.iterrows():
                sample_name = row["sample_name"]

                for library_type in service_type.library_types:
                    add_library(sample_name, library_type)

                if form.optional_assays.antibody_capture.data:
                    if service_type in C.ServiceType.get_flex_services():
                        add_library(sample_name, C.LibraryType.TENX_SC_ABC_FLEX)
                    else:
                        add_library(sample_name, C.LibraryType.TENX_ANTIBODY_CAPTURE)

                if form.optional_assays.vdj_b.data:
                    add_library(sample_name, C.LibraryType.TENX_VDJ_B)

                if form.optional_assays.vdj_t.data:
                    add_library(sample_name, C.LibraryType.TENX_VDJ_T)

                if form.optional_assays.vdj_t_gd.data:
                    add_library(sample_name, C.LibraryType.TENX_VDJ_T_GD)

                if form.optional_assays.crispr_screening.data:
                    add_library(sample_name, C.LibraryType.TENX_CRISPR_SCREENING)

                if form.optional_assays.parse_crispr.data:
                    add_library(sample_name, C.LibraryType.PARSE_SC_CRISPR)
                
                if form.optional_assays.parse_tcr.data:
                    add_library(sample_name, C.LibraryType.PARSE_EVERCODE_TCR)

                if form.optional_assays.parse_bcr.data:
                    add_library(sample_name, C.LibraryType.PARSE_EVERCODE_BCR)

            library_table = pd.DataFrame(library_table_data)
            library_table["seq_depth"] = None

            sample_pooling_table = pd.DataFrame(sample_pooling_table)
            sample_pooling_table["mux_type_id"] = None

            workflow.tables["sample_pooling_table"] = sample_pooling_table
            workflow.tables["library_table"] = library_table
            return workflow.get_next_step(form).make_response()
        return dependency
