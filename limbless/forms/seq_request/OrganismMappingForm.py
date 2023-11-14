from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import FieldList, FormField, TextAreaField, IntegerField, BooleanField, StringField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import tools, models, db, logger
from ...core.DBHandler import DBHandler
from ...core.DBSession import DBSession
from .TableDataForm import TableDataForm


class OrganismSubForm(FlaskForm):
    raw_category = StringField("Raw Label", validators=[OptionalValidator()])
    category = IntegerField("Organism", validators=[DataRequired()], default=None)


# 4. Select organism for samples
class OrganismMappingForm(TableDataForm):
    input_fields = FieldList(FormField(OrganismSubForm), min_entries=1)

    def prepare(self, seq_request_id: int, df: Optional[pd.DataFrame] = None) -> dict:
        if df is None:
            df = self.get_df()

        with DBSession(db.db_handler) as session:
            if (seq_request := session.get_seq_request(seq_request_id)) is None:
                raise Exception(f"Seq request with id {seq_request_id} does not exist.")
            
            projects: dict[int, models.Project] = {}
            project_samples: dict[int, dict[str, models.Sample]] = {}
            for project_id in df["project_id"].unique():
                if not pd.isnull(project_id):
                    project_id = int(project_id)
                    if (project := session.get_project(project_id)) is None:
                        raise Exception(f"Project with id {project_id} does not exist.")
                    
                    projects[project_id] = project
                    project_samples[project_id] = dict([(sample.name, sample) for sample in project.samples])
            
        df["sample_id"] = None
        df["tax_id"] = None
        df["duplicate"] = False

        for i, row in df.iterrows():
            if row["project_id"] is None:
                _project_samples = {}
            else:
                _project_samples = project_samples[row["project_id"]]
            if row["sample_name"] in _project_samples.keys():
                project = projects[row["project_id"]]

                df.at[i, "sample_id"] = _project_samples[row["sample_name"]].id
                df.at[i, "tax_id"] = _project_samples[row["sample_name"]].organism.tax_id

        self.set_df(df)
        organisms = sorted(df["organism"].unique())
        selected: list[Optional[str]] = []    # TODO: selected

        for i, entry in enumerate(self.input_fields):
            if (selected_id := entry.category.data) is not None:
                selected_organism = db.db_handler.get_organism(selected_id)
            else:
                if organisms[i] is None:
                    selected_organism = None
                else:
                    selected_organism = next(iter(db.db_handler.query_organisms(word=organisms[i], limit=1)), None)
                    entry.category.data = selected_organism.id if selected_organism is not None else None

            selected.append(selected_organism.to_str() if selected_organism is not None else None)

        logger.debug(selected)
        return {
            "categories": organisms,
            "selected": selected,
        }

    def custom_validate(self, db_handler: DBHandler):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self