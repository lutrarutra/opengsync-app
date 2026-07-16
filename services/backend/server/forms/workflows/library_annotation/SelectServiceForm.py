import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, categories as C

from ....core import responses, exceptions as exc
from ....components import inputs
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep
from .DefineMultiplexedSamplesForm import DefineMultiplexedSamplesForm
from .CustomAssayAnnotationForm import CustomAssayAnnotationForm

class OptionalAssaysForm(SubHTMXForm):
    vdj_b = inputs.boolean.CheckboxInputField("VDJ-B")
    vdj_t = inputs.boolean.CheckboxInputField("VDJ-T")
    vdj_t_gd = inputs.boolean.CheckboxInputField("VDJ-T-GD")
    crispr_screening = inputs.boolean.CheckboxInputField("CRISPR Screening")
    antibody_capture = inputs.boolean.CheckboxInputField("Cell Surface Protein Quantification")
    antibody_multiplexing = inputs.boolean.CheckboxInputField("+ Sample Multiplexing with Antibody-based Cell Hashing", description="Multiple samples per library with antibody-based cell tagging. Only available with cell surface protein capture.")
    antibody_capture_kit = inputs.string.StringInputField("Antibody Capture Kit", description="Specify the antibody capture kit used for cell surface protein quantification.", max_length=64, required=False)

    parse_mux = inputs.boolean.CheckboxInputField("Multiple Samples per Sub-Library (Multiplexing)", description="Multiple samples per library with Parse Biosciences multiplexing. Only available with Parse Biosciences assays.")
    parse_tcr = inputs.boolean.CheckboxInputField(C.LibraryType.PARSE_EVERCODE_TCR.name)
    parse_bcr = inputs.boolean.CheckboxInputField(C.LibraryType.PARSE_EVERCODE_BCR.name)
    parse_crispr = inputs.boolean.CheckboxInputField(C.LibraryType.PARSE_SC_CRISPR.name)

    Parse_kits = [(1, "WT_mini"), (2, "WT"), (3, "WT_mega"), (4, "WT_mega_384"), (5, "WT_penta"), (6, "WT_penta_384")]
    parse_kit = inputs.selectable.SelectableInputField("Parse Kit", Parse_kits, required=False)

    Parse_chemistries = [(1, "v1"), (2, "v2"), (3, "v3")]
    parse_chemistry = inputs.selectable.SelectableInputField("Parse Chemistry", Parse_chemistries, required=False)

class AdditionalSerevicesForm(SubHTMXForm):
    oligo_multiplexing = inputs.boolean.CheckboxInputField("Sample Multiplexing using Antibody/Oligo-based Cell Tagging for 10X Libraries", description="Multiple samples per library with oligo-based cell tagging, e.g. CMO/HTO/LMO/Antibodies..")
    oligo_multiplexing_kit = inputs.string.StringInputField("Multiplexing Kit", description="Multiplexing Kit", max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, required=False)
    ocm_multiplexing = inputs.boolean.CheckboxInputField("On-Chip Multiplexing for 10X GEM-X Libraries", description="Multiple samples per library using 10X On-Chip Multiplexing")
    nuclei_isolation = inputs.boolean.CheckboxInputField("Nuclei Isolation")


class SelectServiceForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-select_service.html"

    service_type = inputs.selectable.SelectableInputField("Service", C.ServiceType.as_selectable())
    additional_info = inputs.string.TextAreaInputField("Additional Information", description="Please provide any additional information about the assay or library preparation that may be relevant for processing.", max_length=4096, required=False)
    optional_assays = OptionalAssaysForm()
    additional_services = AdditionalSerevicesForm()

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.submission_type = C.SubmissionType.get(workflow.header["submission_type_id"])

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: SelectServiceForm = Depends(SelectServiceForm.PreviousStep()),
        ) -> Response:
            form.service_type.data = form.workflow.metadata.get("service_type_id")
            form.additional_services.nuclei_isolation.data = form.workflow.metadata.get("nuclei_isolation", False)
            form.optional_assays.antibody_capture.data = form.workflow.metadata.get("antibody_capture", False)
            form.optional_assays.vdj_b.data = form.workflow.metadata.get("vdj_b", False)
            form.optional_assays.vdj_t.data = form.workflow.metadata.get("vdj_t", False)
            form.optional_assays.vdj_t_gd.data = form.workflow.metadata.get("vdj_t_gd", False)
            form.optional_assays.crispr_screening.data = form.workflow.metadata.get("crispr_screening", False)
            form.optional_assays.antibody_multiplexing.data = form.workflow.metadata.get("antibody_multiplexing", False)

            form.optional_assays.parse_kit.data = form.workflow.metadata.get("parse_kit", -1)
            form.optional_assays.parse_chemistry.data = form.workflow.metadata.get("parse_chemistry", -1)
            form.optional_assays.parse_crispr.data = form.workflow.metadata.get("parse_crispr", False)
            form.optional_assays.parse_mux.data = form.workflow.metadata["mux_type_id"] == C.MUXType.PARSE_WELLS.id
            form.optional_assays.parse_tcr.data = form.workflow.metadata.get("parse_tcr", False)
            form.optional_assays.parse_bcr.data = form.workflow.metadata.get("parse_bcr", False)

            form.optional_assays.antibody_capture_kit.data = form.workflow.metadata.get("antibody_capture_kit", "")
            
            if form.workflow.metadata.get("mux_type_id") == C.MUXType.TENX_OLIGO.id:
                form.additional_services.oligo_multiplexing.data = True
                form.additional_services.oligo_multiplexing_kit.data = form.workflow.metadata.get("oligo_multiplexing_kit", "")
            elif form.workflow.metadata.get("mux_type_id") == C.MUXType.TENX_ON_CHIP.id:
                form.additional_services.ocm_multiplexing.data = True

            form.additional_info.data = form.workflow.metadata.get("additional_info", "")
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def dependency(
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
            
            form.assert_valid()
            
            oligo_multiplexing = form.additional_services.oligo_multiplexing.data
            ocm_multiplexing = form.additional_services.ocm_multiplexing.data
            antibody_multiplexing = form.optional_assays.antibody_multiplexing.data
            flex_barcode_multiplexing = service_type in [C.ServiceType.TENX_SC_4_PLEX_FLEX, C.ServiceType.TENX_SC_16_PLEX_FLEX, C.ServiceType.TENX_SC_FLEX_V2]
            parse_multiplexing = form.optional_assays.parse_mux.data
            
            form.workflow.metadata["service_type_id"] = service_type.id
            form.workflow.metadata["mux_type_id"] = None
            form.workflow.metadata["oligo_multiplexing_kit"] = form.additional_services.oligo_multiplexing_kit.data
            form.workflow.metadata["antibody_capture_kit"] = form.optional_assays.antibody_capture_kit.data
            form.workflow.metadata["antibody_multiplexing"] = form.optional_assays.antibody_multiplexing.data

            if oligo_multiplexing:
                form.workflow.metadata["mux_type_id"] = C.MUXType.TENX_OLIGO.id
            elif ocm_multiplexing:
                form.workflow.metadata["mux_type_id"] = C.MUXType.TENX_ON_CHIP.id
            elif flex_barcode_multiplexing:
                form.workflow.metadata["mux_type_id"] = C.MUXType.TENX_FLEX_PROBE.id
            elif antibody_multiplexing:
                form.workflow.metadata["mux_type_id"] = C.MUXType.TENX_ABC_HASH.id
            elif parse_multiplexing:
                form.workflow.metadata["mux_type_id"] = C.MUXType.PARSE_WELLS.id
                
            form.workflow.metadata["nuclei_isolation"] = form.additional_services.nuclei_isolation.data
            form.workflow.metadata["antibody_capture"] = form.optional_assays.antibody_capture.data

            form.workflow.metadata["vdj_b"] = form.optional_assays.vdj_b.data
            form.workflow.metadata["vdj_t"] = form.optional_assays.vdj_t.data
            form.workflow.metadata["vdj_t_gd"] = form.optional_assays.vdj_t_gd.data
            form.workflow.metadata["crispr_screening"] = form.optional_assays.crispr_screening.data
            form.workflow.metadata["additional_info"] = form.additional_info.data

            form.workflow.metadata["parse_kit"] = form.optional_assays.parse_kit.data
            form.workflow.metadata["parse_chemistry"] = form.optional_assays.parse_chemistry.data
            form.workflow.metadata["parse_crispr"] = form.optional_assays.parse_crispr.data
            form.workflow.metadata["parse_tcr"] = form.optional_assays.parse_tcr.data
            form.workflow.metadata["parse_bcr"] = form.optional_assays.parse_bcr.data

            if form.additional_services.oligo_multiplexing_kit.data:
                form.workflow.add_comment(context="oligo_multiplexing_kit", text=form.additional_services.oligo_multiplexing_kit.data)

            if form.optional_assays.antibody_capture_kit.data:
                form.workflow.add_comment(context="antibody_capture_kit", text=form.optional_assays.antibody_capture_kit.data)

            if form.additional_info.data:
                form.workflow.add_comment(context="assay_tech_selection", text=form.additional_info.data)
            
            if (parse_chemistry := form.optional_assays.parse_chemistry.value) is not None:
                form.workflow.add_comment(context="parse_chemistry", text=parse_chemistry)

            if (parse_kit := form.optional_assays.parse_kit.value) is not None:
                form.workflow.add_comment(context="parse_kit", text=parse_kit)

            if DefineMultiplexedSamplesForm.is_applicable(form.workflow):
                next_form = DefineMultiplexedSamplesForm(form.workflow)
                return next_form.make_response()

            sample_table = form.workflow.tables["sample_table"]
            
            if service_type == C.ServiceType.CUSTOM:
                sample_pooling_table = {
                    "sample_pool": [],
                    "sample_name": [],
                }
                for (sample_name,), _ in sample_table.groupby(["sample_name"], sort=False):
                    sample_pooling_table["sample_pool"].append(sample_name)
                    sample_pooling_table["sample_name"].append(sample_name)
                    
                sample_pooling_table = pd.DataFrame(sample_pooling_table)
                form.workflow.tables["sample_pooling_table"] = sample_pooling_table
                next_form = CustomAssayAnnotationForm(form.workflow)
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

            form.workflow.tables["sample_pooling_table"] = sample_pooling_table
            form.workflow.tables["library_table"] = library_table
            return form.workflow.get_next_step(form).make_response()
        return dependency
