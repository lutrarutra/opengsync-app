from flask import Response, flash, url_for
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import FloatField, IntegerField, FieldList, FormField, StringField
from wtforms.validators import DataRequired, Optional as OptionalValidator

from opengsync_db import models

from ... import db, logger  # noqa
from ..HTMXFlaskForm import HTMXFlaskForm


class LaneSubForm(FlaskForm):
    lane_id = IntegerField(validators=[DataRequired()])
    lane_num = IntegerField()
    num_reads = FloatField(validators=[OptionalValidator()])


class PoolSubForm(FlaskForm):
    pool_id = IntegerField(validators=[DataRequired()])
    pool_name = StringField()
    reads_fields = FieldList(FormField(LaneSubForm), min_entries=1)

    def get_read_field(self, lane_num: int) -> LaneSubForm | None:
        for field in self.reads_fields:
            if field.lane_num.data == lane_num:
                return field  # type: ignore
        return None


class DistributeReadsSeparateForm(HTMXFlaskForm):
    _template_path = "workflows/dist_reads/separate.html"

    experiment_id = IntegerField(validators=[DataRequired()])
    pool_fields = FieldList(FormField(PoolSubForm), min_entries=1)

    def __init__(self, experiment: models.Experiment, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self.experiment_id.data = self.experiment.id
        self._context["experiment"] = experiment

    def prepare(self):
        for i, pool in enumerate(self.experiment.pools):
            if i > len(self.pool_fields) - 1:
                self.pool_fields.append_entry()

            pool_field: PoolSubForm = self.pool_fields[-1]  # type: ignore
            pool_field.pool_id.data = pool.id
            pool_field.pool_name.data = pool.name

            for j, pool_link in enumerate(pool.lane_links):
                if j > len(pool_field.reads_fields) - 1:
                    pool_field.reads_fields.append_entry()

                lane_field: LaneSubForm = pool_field.reads_fields[-1]  # type: ignore
                lane_field.num_reads.data = pool_link.num_m_reads
                lane_field.lane_id.data = pool_link.lane_id
                lane_field.lane_num.data = pool_link.lane.number

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True

    def process_request(self) -> Response:
        if not self.validate():
            logger.debug(self.errors)
            return self.make_response()

        links: dict[tuple[int, int], models.links.LanePoolLink] = {}
        for link in self.experiment.laned_pool_links:
            links[(link.lane_id, link.pool_id)] = link

        pool_field: PoolSubForm
        for pool_field in self.pool_fields:  # type: ignore
            if (pool := db.pools.get(pool_field.pool_id.data)) is None:  # type: ignore
                logger.error(f"Pool with id {pool_field.pool_id.data} does not exist")
                raise ValueError(f"Pool with id {pool_field.pool_id.data} does not exist")

            lane_field: LaneSubForm
            for lane_field in pool_field.reads_fields:  # type: ignore
                if (lane := db.lanes.get(lane_field.lane_id.data)) is None:  # type: ignore
                    logger.error(f"Lane with id {lane_field.lane_id.data} does not exist")
                    raise ValueError(f"Lane with id {lane_field.lane_id.data} does not exist")

                if (link := links.get((lane.id, pool.id))) is None:
                    logger.error(f"Link between lane {lane.id} and pool {pool.id} does not exist")
                    raise ValueError(f"Link between lane {lane.id} and pool {pool.id} does not exist")

                link.num_m_reads = lane_field.num_reads.data
                
        db.experiments.update(self.experiment)
        flash("Saved!", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))
    

class PoolReadsSubForm(FlaskForm):
    pool_id = IntegerField(validators=[DataRequired()])
    pool_name = StringField()
    num_reads = FloatField(validators=[OptionalValidator()])


class DistributeReadsCombinedForm(HTMXFlaskForm):
    _template_path = "workflows/dist_reads/combined.html"

    experiment_id = IntegerField(validators=[DataRequired()])
    pool_reads_fields = FieldList(FormField(PoolReadsSubForm), min_entries=1)

    def __init__(self, experiment: models.Experiment, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self.experiment_id.data = self.experiment.id
        self._context["experiment"] = experiment

    def prepare(self):
        for i, pool in enumerate(self.experiment.pools):
            if i > len(self.pool_reads_fields) - 1:
                self.pool_reads_fields.append_entry()

            pool_reads_field: PoolReadsSubForm = self.pool_reads_fields[-1]  # type: ignore
            pool_reads_field.pool_id.data = pool.id
            pool_reads_field.pool_name.data = pool.name
            pool_reads_field.num_reads.data = pool.lane_links[0].num_m_reads * self.experiment.num_lanes if pool.lane_links[0].num_m_reads is not None else None

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True

    def process_request(self) -> Response:
        if not self.validate():
            logger.debug(self.errors)  # FIXME: Erros not printed
            return self.make_response()

        links: dict[tuple[int, int], models.links.LanePoolLink] = {}
        for link in self.experiment.laned_pool_links:
            links[(link.lane_id, link.pool_id)] = link

        for pool_field in self.pool_reads_fields:
            if (pool := db.pools.get(pool_field.pool_id.data)) is None:
                logger.error(f"Pool with id {pool_field.pool_id.data} does not exist")
                raise ValueError(f"Pool with id {pool_field.pool_id.data} does not exist")

            for link in pool.lane_links:
                link.num_m_reads = pool_field.num_reads.data / self.experiment.num_lanes
                
        db.experiments.update(self.experiment)
        flash("Saved!", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))