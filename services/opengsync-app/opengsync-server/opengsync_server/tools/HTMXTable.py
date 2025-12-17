import json
from flask import url_for

from opengsync_db import categories as cats

from .TableCol import TableCol

class HTMXTable:
    columns: list[TableCol] = []
    def __init__(self, route: str, page: int | None = 0):
        self.active_search_var: str | None = None
        self.active_sort_var: str | None = None
        self.active_sort_descending: bool = False
        self.active_query_value: str | None = None
        self.filter_values: dict[str, list] = {}
        self.route = route
        self.num_pages: int | None = None
        self.active_page: int | None = page
        self.url_params: dict = {}

    def __getitem__(self, item: str) -> TableCol:
        for col in self.columns:
            if col.label == item:
                return col
        raise KeyError(f"Column with label '{item}' not found in table.")
    
    @property
    def url(self) -> str:
        state = self.url_params.copy()
        if self.num_pages is not None:
            state["page"] = self.active_page
        return url_for(self.route, **state)
    
    def get_state(self) -> dict:
        state = self.url_params.copy()
        if self.num_pages is not None:
            state["page"] = self.active_page
        if self.active_sort_var is not None:
            state["sort_by"] = self.active_sort_var
            state["sort_order"] = "desc" if self.active_sort_descending else "asc"
        if self.active_query_value is not None:
            state[self.active_search_var] = self.active_query_value
        if self.filter_values:
            for key, values in self.filter_values.items():
                state[key + "_in"] = json.dumps([v.id for v in values])
        return state
    
    def page_url(self, page: int) -> str:
        return url_for(self.route, page=page, **self.url_params)
    

class ProjectTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=1, search_type="text", sortable=True),
        TableCol(title="Title", label="title", col_size=3, search_type="text", sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=2, choices=cats.LibraryType.as_list()),
        TableCol(title="Status", label="status", col_size=1, search_type="text", sort_by="status_id", sortable=True, choices=cats.ProjectStatus.as_list()),
        TableCol(title="Group", label="group", col_size=2),
        TableCol(title="Owner", label="owner_name", col_size=2, search_type="text"),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
    ]


class SeqRequestTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=4, search_type="text", sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=cats.LibraryType.as_list()),
        TableCol(title="Status", label="status", col_size=1, search_type="text", sortable=True, sort_by="status_id", choices=cats.SeqRequestStatus.as_list()),
        TableCol(title="Submission Type", label="submission_type", col_size=1, choices=cats.SubmissionType.as_list()),
        TableCol(title="Group", label="group", col_size=2, search_type="text"),
        TableCol(title="Requestor", label="requestor", col_size=2, search_type="text"),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
        TableCol(title="Submitted", label="timestamp_submitted", col_size=2, sortable=True, sort_by="timestamp_submitted_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]

class PoolTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=2, choices=cats.LibraryType.as_list()),
        TableCol(title="Status", label="status", col_size=2, sortable=True, sort_by="status_id", choices=cats.PoolStatus.as_list()),
        TableCol(title="Type", label="type", col_size=1, sortable=True, sort_by="type_id", choices=cats.PoolType.as_list()),
        TableCol(title="Owner", label="owner", col_size=2, search_type="text"),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
    ]

class LibraryTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Pool", label="pool_name", col_size=1, search_type="text", sortable=True, sort_by="pool_id"),
        TableCol(title="Library Type", label="type", col_size=1, choices=cats.LibraryType.as_list()),
        TableCol(title="Status", label="status", col_size=1, sortable=True, sort_by="status_id", choices=cats.LibraryStatus.as_list()),
        TableCol(title="Request", label="seq_request", col_size=2),
        TableCol(title="Owner", label="owner", col_size=1),
    ]

class SampleTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Project", label="project", col_size=2),
        TableCol(title="Status", label="status", col_size=2, sortable=True, sort_by="status_id", choices=cats.SampleStatus.as_list()),
        TableCol(title="Owner", label="owner", col_size=1),
        TableCol(title="# Libraries", label="num_libraries", col_size=1),
    ]

class UserTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text"),
        TableCol(title="Email", label="email", col_size=3, sortable=True),
        TableCol(title="Role", label="role", col_size=2, choices=cats.UserRole.as_list(), sortable=True, sort_by="role_id"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="# Projects", label="num_projects", col_size=1, sortable=True),
    ]


class AffiliationTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1),
        TableCol(title="User", label="user_name", col_size=3, search_type="text"),
        TableCol(title="Group", label="group_name", col_size=3, search_type="text"),
        TableCol(title="Email", label="email", col_size=3),
        TableCol(title="Affiliation", label="affiliation", col_size=2, choices=cats.UserRole.as_list(), sortable=True, sort_by="role_id"),
    ]

class GroupTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text"),
        TableCol(title="Type", label="type", col_size=2, choices=cats.GroupType.as_list(), sortable=True, sort_by="type_id"),
        TableCol(title="# Users", label="num_users", col_size=1, sortable=True),
        TableCol(title="# Projects", label="num_projects", col_size=1, sortable=True),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
    ]

class ExperimentTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Workflow", label="workflow", col_size=2, choices=cats.ExperimentWorkFlow.as_list(), sortable=True, sort_by="workflow_id"),
        TableCol(title="Status", label="status", col_size=2, choices=cats.ExperimentStatus.as_list(), sortable=True, sort_by="status_id"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=2, choices=cats.LibraryType.as_list()),
        TableCol(title="Operator", label="operator", col_size=2, search_type="text"),
        TableCol(title="Created", label="timestamp_created", col_size=2, sortable=True, sort_by="timestamp_created_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]


class LabPrepTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Checklist", label="checklist", col_size=2, choices=cats.LabChecklistType.as_list(), sortable=True, sort_by="checklist_type_id"),
        TableCol(title="Service", label="service", col_size=2, choices=cats.ServiceType.as_list(), sortable=True, sort_by="service_type_id"),
        TableCol(title="Status", label="status", col_size=2, choices=cats.PrepStatus.as_list(), sortable=True, sort_by="status_id"),
        TableCol(title="# Samples", label="num_samples", col_size=1, sortable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
        TableCol(title="Creator", label="creator", col_size=2, search_type="text"),
    ]
    
class KitTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, search_type="text", sortable=True),
        TableCol(title="Type", label="type", col_size=2, choices=cats.KitType.as_list(), sortable=True, sort_by="kit_type_id"),
    ]

class IndexKitTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, search_type="text", sortable=True),
        TableCol(title="Index Type", label="type", col_size=2, choices=cats.IndexType.as_list(), sortable=True, sort_by="type_id"),
        TableCol(title="Protocols", label="protocols", col_size=2),
    ]

class FeatureKitTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, search_type="text", sortable=True),
        TableCol(title="Feature Type", label="type", col_size=2, choices=cats.FeatureType.as_list(), sortable=True, sort_by="type_id"),
    ]

class AdapterTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Well", label="well", col_size=3, search_type="text", sortable=True),
        TableCol(title="Name", label="name", col_size=2, sortable=True),
        TableCol(title="Name i7", label="name_i7", col_size=2),
        TableCol(title="Name i5", label="name_i5", col_size=2),
        TableCol(title="Sequence i7", label="sequence_i7", col_size=2),
        TableCol(title="Sequence i5", label="sequence_i5", col_size=2),
        TableCol(title="Sequence 1", label="sequence_1", col_size=2),
        TableCol(title="Sequence 2", label="sequence_2", col_size=2),
        TableCol(title="Sequence 3", label="sequence_3", col_size=2),
        TableCol(title="Sequence 4", label="sequence_4", col_size=2),
    ]

class SeqRunTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Experiment", label="experiment", col_size=2, search_type="text", sortable=True, sort_by="experiment_name"),
        TableCol(title="Status", label="status", col_size=1, choices=cats.RunStatus.as_list(), sortable=True, sort_by="status_id"),
        TableCol(title="Cycles", label="cycles", col_size=1),
        TableCol(title="Flow Cell ID", label="flow_cell_id", search_type="text", col_size=1),
        TableCol(title="Run Folder", label="run_folder", col_size=4, search_type="text"),
        TableCol(title="Started", label="started", col_size=2),
        TableCol(title="Completed", label="completed", col_size=2),
    ]

class ProtocolTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Read Structure", label="read_structure", col_size=3),
        TableCol(title="Assay", label="service_type", col_size=2, choices=cats.ServiceType.as_list(), sortable=True, sort_by="service_type_id"),
    ]

class SequencerTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Name", label="name", col_size=3, search_type="text", sortable=True),
        TableCol(title="Model", label="model", col_size=2, choices=cats.SequencerModel.as_list(), sortable=True, sort_by="model_id"),
    ]