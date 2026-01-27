import pandas as pd

from flask import Response

from opengsync_db import models
from opengsync_db.categories import FeatureType

from .... import tools, logger  # noqa
from ..common.CommonFeatureAnnotationForm import CommonFeatureAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm


class FeatureAnnotationForm(CommonFeatureAnnotationForm):
    _template_path = "workflows/library_annotation/sas-feature_annotation.html"
    _workflow_name = "library_annotation"
    seq_request: models.SeqRequest

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        CommonFeatureAnnotationForm.__init__(
            self, workflow=FeatureAnnotationForm._workflow_name,
            seq_request=seq_request, lab_prep=None, uuid=uuid,
            formdata=formdata, additional_columns=[]
        )

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.feature_table = self.get_feature_table()
        
        if (kit_table := self.tables.get("kit_table")) is None:  # type: ignore
            kit_table = self.feature_table.loc[self.feature_table["kit"].notna(), ["kit", "kit_id"]].drop_duplicates().copy().rename(columns={"kit": "name"})
            kit_table["type_id"] = FeatureType.ANTIBODY.id
            self.add_table("kit_table", kit_table)
        else:
            _kit_table = self.feature_table.loc[self.feature_table["kit"].notna(), ["kit", "kit_id"]].drop_duplicates().copy().rename(columns={"kit": "name"})
            _kit_table["type_id"] = FeatureType.ANTIBODY.id
            kit_table = pd.concat([kit_table[kit_table["type_id"] != FeatureType.ANTIBODY.id], _kit_table])
            self.update_table("kit_table", kit_table, False)

        self.add_table("feature_table", self.feature_table)
        self.update_data()

        if OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif ParseCRISPRGuideAnnotationForm.is_applicable(self):
            next_form = ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)
        
        return next_form.make_response()
        
