from typing import Optional

import pandas as pd

from flask import Response
from flask_wtf import FlaskForm
from wtforms import SelectField, TextAreaField, BooleanField, FormField
from wtforms.validators import Optional as OptionalValidator, Length, DataRequired

from limbless_db import models
from limbless_db.categories import AssayType, GenomeRef, LibraryType

from .... import logger, db  # noqa
from ...MultiStepForm import MultiStepForm
from .DefineSamplesForm import DefineSamplesForm
from .DefineMultiplexedSamplesForm import DefineMultiplexedSamplesForm


class OptionalAssaysForm(FlaskForm):
    antibody_capture = BooleanField("Cell Surface Protein Capture", description="Anitbody Capture", default=False)
    vdj_b = BooleanField("VDJ-B", description="BCR-sequencing", default=False)
    vdj_t = BooleanField("VDJ-T", description="TCR-sequencing", default=False)
    vdj_t_gd = BooleanField("VDJ-T-GD", description="TCR-GD-sequencing", default=False)
    crispr_screening = BooleanField("CRISPR Screening", default=False)


class AdditionalSerevicesForm(FlaskForm):
    multiplexing = BooleanField("Sample Antibody Multiplexing", description="Multiple samples per library with cell multiplexing hashtag-oligo (HTO)", default=False)
    nuclei_isolation = BooleanField("Nuclei Isolation", default=False)


class SelectAssayForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-select_assay.html"
    _workflow_name = "library_annotation"
    _step_name = "specify_assay"

    assay_type = SelectField("Assay Type", choices=AssayType.as_selectable(), validators=[DataRequired()], coerce=int)
    additional_info = TextAreaField("Additional Information", validators=[OptionalValidator(), Length(max=models.Comment.text.type.length)])
    optional_assays = FormField(OptionalAssaysForm)
    additional_services = FormField(AdditionalSerevicesForm)

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict = {}, previous_form: Optional[MultiStepForm] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=SelectAssayForm._workflow_name,
            step_name=SelectAssayForm._step_name, previous_form=previous_form,
            step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def validate(self) -> bool:
        if not super().validate():
            return False

        if self.assay_type.data is None or AssayType.get(self.assay_type.data) == AssayType.CUSTOM:
            self.assay_type.errors = ("Please select an assay type.",)
            return False

        selected_library_types = [t.abbreviation for t in AssayType.get(self.assay_type.data).library_types]
        if self.optional_assays.antibody_capture.data:
            selected_library_types.append(LibraryType.TENX_ANTIBODY_CAPTURE.abbreviation)
        if self.optional_assays.vdj_b.data:
            selected_library_types.append(LibraryType.TENX_VDJ_B.abbreviation)
        if self.optional_assays.vdj_t.data:
            selected_library_types.append(LibraryType.TENX_VDJ_T.abbreviation)
        if self.optional_assays.vdj_t_gd.data:
            selected_library_types.append(LibraryType.TENX_VDJ_T_GD.abbreviation)
        if self.optional_assays.crispr_screening.data:
            selected_library_types.append(LibraryType.TENX_CRISPR_SCREENING.abbreviation)
        if self.additional_services.multiplexing.data:
            selected_library_types.append(LibraryType.TENX_MULTIPLEXING_CAPTURE.abbreviation)
        
        genome_map = {}
        for id, e in GenomeRef.as_tuples():
            genome_map[e.display_name] = id
        
        try:
            self.assay_type_enum = AssayType.get(int(self.assay_type.data))
        except ValueError:
            self.assay_type.errors = ("Invalid assay type",)
            return False

        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        assay_type = AssayType.get(self.assay_type.data)
        self.metadata["assay_type_id"] = assay_type.id
        self.metadata["antibody_multiplexing"] = self.additional_services.multiplexing.data
        self.metadata["nuclei_isolation"] = self.additional_services.nuclei_isolation.data
        self.metadata["antibody_capture"] = self.optional_assays.antibody_capture.data
        self.metadata["vdj_b"] = self.optional_assays.vdj_b.data
        self.metadata["vdj_t"] = self.optional_assays.vdj_t.data
        self.metadata["vdj_t_gd"] = self.optional_assays.vdj_t_gd.data
        self.metadata["crispr_screening"] = self.optional_assays.crispr_screening.data

        if self.additional_info.data:
            comment_table = pd.DataFrame({
                "context": ["assay_tech_selection"],
                "text": [self.additional_info.data]
            })
            self.add_table("comment_table", comment_table)
        self.update_data()

        multiplexed = self.additional_services.multiplexing.data | (assay_type in [AssayType.TENX_SC_4_PLEX_FLEX, AssayType.TENX_SC_16_PLEX_FLEX])

        if multiplexed:
            next_form = DefineMultiplexedSamplesForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        else:
            next_form = DefineSamplesForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)

        return next_form.make_response()
        
        
