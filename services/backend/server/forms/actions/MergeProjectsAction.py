from fastapi import Depends
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, actions

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class MergeProjectsAction(HTMXForm):
    template_path = "workflows/merge_projects.html"

    project_dst = inputs.searchable.SearchableInputField(
        "Destination Project", route="search_projects", required=True,
    )
    project_src = inputs.searchable.SearchableInputField(
        "Source Project", route="search_projects", required=True,
    )

    def __init__(self) -> None:
        super().__init__()
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit")

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency() -> "MergeProjectsAction":
            return MergeProjectsAction()
        return dependency

    def _raise_if_attribute_conflicts(
        self,
        project_dst: models.Project,
        project_src: models.Project,
    ) -> None:
        dst_sample_mapping = {sample.name: sample for sample in project_dst.samples}
        for sample in project_src.samples:
            if sample.name not in dst_sample_mapping:
                continue
            dst_sample = dst_sample_mapping[sample.name]
            for attr in sample.attributes:
                dst_attr = dst_sample.get_attribute(attr.name)
                if dst_attr is None:
                    continue
                if dst_attr.type_id != attr.type_id:
                    msg = f"Sample name conflict for sample '{sample.name}' with incompatible attribute types."
                elif dst_attr.value != attr.value:
                    msg = f"Sample name conflict for sample '{sample.name}' with incompatible attribute values."
                else:
                    continue
                self.project_src.errors.append(msg)
                self.project_dst.errors.append(msg)
                raise exc.FormValidationException(self)

    @htmx_route("GET", "/merge-projects")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "MergeProjectsAction" = Depends(MergeProjectsAction.Init()),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/merge-projects")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "MergeProjectsAction" = Depends(MergeProjectsAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ) -> responses.Response:
            if form.project_dst.data is None:
                form.project_dst.errors.append("Please select a destination project to merge into.")
                raise exc.FormValidationException(form)

            if form.project_src.data is None:
                form.project_src.errors.append("Please select a source project to merge from.")
                raise exc.FormValidationException(form)

            if form.project_dst.data == form.project_src.data:
                form.project_src.errors.append("Source and destination projects cannot be the same.")
                form.project_dst.errors.append("Source and destination projects cannot be the same.")
                raise exc.FormValidationException(form)

            sample_options = [orm.selectinload(models.Project.samples)]
            if (project_dst := session.first(
                Q.project.select(id=int(form.project_dst.data)),
                options=sample_options,
            )) is None:
                form.project_dst.errors.append("Selected project not found.")
                raise exc.FormValidationException(form)

            if (project_src := session.first(
                Q.project.select(id=int(form.project_src.data)),
                options=sample_options,
            )) is None:
                form.project_src.errors.append("Selected project not found.")
                raise exc.FormValidationException(form)

            form._raise_if_attribute_conflicts(project_dst, project_src)

            project = actions.merge_projects(session, project_dst=project_dst, project_src=project_src)

            return responses.htmx_response(
                redirect=responses.url_for("project_page", project_id=project.id),
                flash=responses.flash("Projects merged successfully!", "success"),
            )
        return route
