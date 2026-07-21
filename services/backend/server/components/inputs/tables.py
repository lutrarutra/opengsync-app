import json
from typing import Any
from uuid import uuid4

from opengsync_db import models, SyncSession, categories as C, queries as Q, utils as db_utils

from ...core.context import ctx
from ...core import responses
from .BaseInputField import BaseInputField


class SelectTableField(BaseInputField):
    """Base for table-select fields that store selected IDs as a JSON string.

    Provides shared ``data`` property (``list[int]``) and ``validate()`` that
    parse a JSON array of int IDs from the form. Subclasses only need to
    define ``__init__``, ``table_url``, and a ``get_selected_*`` method.
    """

    entity_type: str
    """Lowercase entity name used in CSS classes and DOM IDs (e.g. 'sample', 'library')."""

    _uid: str
    """Unique suffix for JS variable names so multiple instances on one page don't collide."""

    @property
    def data(self) -> list[int]:
        """Return the list of selected IDs as ints."""
        if hasattr(self, "_SelectTableField__data"):
            return self.__data
        if self._validated:
            return self.__data
        if self.default:
            try:
                return [int(i) for i in json.loads(self.default)]
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @data.setter
    def data(self, value: list[int]) -> None:
        self.__data = value
        self._data = json.dumps(self.__data)
        self._validated = True

    def validate(self, raw_data: dict[str, Any]) -> bool:
        """Validate the submitted IDs."""
        value = raw_data.get(self.name, "")
        self.raw_data = value

        if not value or value.strip() == "" or value.strip() == "[]":
            if self.required:
                self.errors = ["Please select at least one item."]
                return False
            self.data = []
            return True

        try:
            ids = json.loads(value)
        except json.JSONDecodeError:
            self.errors = ["Invalid selection data."]
            return False

        if not isinstance(ids, list):
            self.errors = ["Invalid selection data."]
            return False

        int_ids: list[int] = []
        for sid in ids:
            try:
                int_ids.append(int(sid))
            except (ValueError, TypeError):
                self.errors = ["Invalid ID."]
                return False

        if self.required and len(int_ids) == 0:
            self.errors = ["Please select at least one item."]
            return False

        self.data = int_ids
        self._self_validated = True
        return True


class SampleSelectTableField(SelectTableField):
    """A reusable input component for selecting multiple samples."""

    def __init__(
        self,
        label: str,
        browse_context: str,
        *,
        status_in: list[C.SampleStatus] | None = None,
        select_all: bool = False,
        required: bool = True,
        default: list[int] | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/table-select.html",
            type="sample-select",
            required=required,
            default=json.dumps(default) if default else "",
            pydantic_type=str,
            hidden=hidden,
            read_only=read_only,
        )
        self.entity_type = "sample"
        self._uid = uuid4().hex[:8]
        self.select_all = select_all
        self.query_params: dict[str, Any] = {"browse": browse_context}
        self.browse_context = browse_context
        if status_in:
            self.query_params["status_in"] = json.dumps([s.id for s in status_in])

    @property
    def table_url(self) -> responses.URL:
        return responses.url_for('render_sample_table').include_query_params(**self.query_params)

    def get_selected_samples(self, session: SyncSession, options: db_utils.QueryOptions = None) -> list[models.Sample]:
        """Query the database for the selected :class:`Sample` objects."""
        if not self.data:
            return []
        return [session.get_one(Q.sample.select(id=sid), options=options) for sid in self.data]

    def render_selected_table(self) -> str:
        """Render the selected samples table as HTML."""
        selected_samples = self.get_selected_samples(ctx.session)
        return responses.render_template(
            "components/tables/selected-sample.html",
            field=self,
            selected_samples=selected_samples,
            browse_context=self.browse_context,
        )


class LibrarySelectTableField(SelectTableField):
    """A reusable input component for selecting multiple libraries."""

    def __init__(
        self,
        label: str,
        browse_context: str,
        *,
        status_in: list[C.LibraryStatus] | None = None,
        type_in: list[C.LibraryType] | None = None,
        indexed: bool | None = None,
        pooled: bool | None = None,
        select_all: bool = False,
        required: bool = True,
        default: list[int] | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/table-select.html",
            type="library-select",
            required=required,
            default=json.dumps(default) if default else "",
            pydantic_type=str,
            hidden=hidden,
            read_only=read_only,
        )
        self.entity_type = "library"
        self._uid = uuid4().hex[:8]
        self.select_all = select_all
        self.query_params: dict[str, Any] = {"browse": browse_context}
        self.browse_context = browse_context
        if status_in:
            self.query_params["status_in"] = json.dumps([s.id for s in status_in])
        if type_in:
            self.query_params["type_in"] = json.dumps([t.id for t in type_in])
        if indexed is not None:
            self.query_params["indexed"] = json.dumps(indexed)
        if pooled is not None:
            self.query_params["pooled"] = json.dumps(pooled)

    @property
    def table_url(self) -> responses.URL:
        return responses.url_for('render_library_table').include_query_params(**self.query_params)

    def get_selected_libraries(self, session: SyncSession, options: db_utils.QueryOptions = None) -> list[models.Library]:
        """Query the database for the selected :class:`Library` objects."""
        if not self.data:
            return []
        return [session.get_one(Q.library.select(id=lid), options=options) for lid in self.data]


class PoolSelectTableField(SelectTableField):
    """A reusable input component for selecting multiple pools."""

    def __init__(
        self,
        label: str,
        browse_context: str,
        *,
        status_in: list[C.PoolStatus] | None = None,
        type_in: list[C.PoolType] | None = None,
        select_all: bool = False,
        required: bool = True,
        default: list[int] | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/table-select.html",
            type="pool-select",
            required=required,
            default=json.dumps(default) if default else "",
            pydantic_type=str,
            hidden=hidden,
            read_only=read_only,
        )
        self.entity_type = "pool"
        self._uid = uuid4().hex[:8]
        self.select_all = select_all
        self.query_params: dict[str, Any] = {"browse": browse_context}
        self.browse_context = browse_context
        if status_in:
            self.query_params["status_in"] = json.dumps([s.id for s in status_in])
        if type_in:
            self.query_params["type_in"] = json.dumps([t.id for t in type_in])

    @property
    def table_url(self) -> responses.URL:
        return responses.url_for('render_pool_table').include_query_params(**self.query_params)

    def get_selected_pools(self, session: SyncSession, options: db_utils.QueryOptions = None) -> list[models.Pool]:
        """Query the database for the selected :class:`Pool` objects."""
        if not self.data:
            return []
        return [session.get_one(Q.pool.select(id=pid), options=options) for pid in self.data]


class LaneSelectTableField(SelectTableField):
    """A reusable input component for selecting multiple lanes."""

    def __init__(
        self,
        label: str,
        browse_context: str,
        *,
        select_all: bool = False,
        required: bool = True,
        default: list[int] | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/table-select.html",
            type="lane-select",
            required=required,
            default=json.dumps(default) if default else "",
            pydantic_type=str,
            hidden=hidden,
            read_only=read_only,
        )
        self.entity_type = "lane"
        self._uid = uuid4().hex[:8]
        self.select_all = select_all
        self.query_params: dict[str, Any] = {"browse": browse_context}
        self.browse_context = browse_context

    @property
    def table_url(self) -> responses.URL:
        return responses.url_for('render_lane_table').include_query_params(**self.query_params)

    def get_selected_lanes(self, session: SyncSession, options: db_utils.QueryOptions = None) -> list[models.Lane]:
        """Query the database for the selected :class:`Lane` objects."""
        if not self.data:
            return []
        return [session.get_one(Q.lane.select(id=lid), options=options) for lid in self.data]


class ExperimentSelectTableField(SelectTableField):
    """A reusable input component for selecting multiple experiments."""

    def __init__(
        self,
        label: str,
        browse_context: str,
        *,
        status_in: list[C.ExperimentStatus] | None = None,
        workflow_in: list[C.ExperimentWorkFlow] | None = None,
        select_all: bool = False,
        required: bool = True,
        default: list[int] | None = None,
        hidden: bool = False,
        read_only: bool = False,
    ):
        super().__init__(
            label=label,
            template="components/inputs/table-select.html",
            type="experiment-select",
            required=required,
            default=json.dumps(default) if default else "",
            pydantic_type=str,
            hidden=hidden,
            read_only=read_only,
        )
        self.entity_type = "experiment"
        self._uid = uuid4().hex[:8]
        self.select_all = select_all
        self.query_params: dict[str, Any] = {"browse": browse_context}
        self.browse_context = browse_context
        if status_in:
            self.query_params["status_in"] = json.dumps([s.id for s in status_in])
        if workflow_in:
            self.query_params["workflow_in"] = json.dumps([w.id for w in workflow_in])

    @property
    def table_url(self) -> responses.URL:
        return responses.url_for('render_experiment_table').include_query_params(**self.query_params)

    def get_selected_experiments(self, session: SyncSession, options: db_utils.QueryOptions = None) -> list[models.Experiment]:
        """Query the database for the selected :class:`Experiment` objects."""
        if not self.data:
            return []
        return [session.get_one(Q.experiment.select(id=eid), options=options) for eid in self.data]