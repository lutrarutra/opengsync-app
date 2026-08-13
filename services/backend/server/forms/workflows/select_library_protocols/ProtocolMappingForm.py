from typing import Self
import os

import pandas as pd
from fastapi import Depends, Response
from pydantic import BaseModel

from opengsync_db import models, SyncSession, queries as Q

from ....core import dependencies, exceptions as exc, config
from ....core.context import ctx
from ....utils import parsing
from ....components import inputs
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .SelectLibraryProtocolsWorkflow import SelectLibraryProtocolsWorkflow, SelectLibraryProtocolsWorkflowStep


class ProtocolComboKey(BaseModel):
    protocol_id: int
    combination_num: int


class ProtocolMappingSubForm(SubHTMXForm):
    kit_combination = inputs.string.StringInputField("Kit Combination", required=True, read_only=True)
    protocol = inputs.selectable.SelectableInputField(
        "Protocol",
        [(-1, "Unknown")],
        default=-1,
        required=True,
    )


class ProtocolMappingForm(SelectLibraryProtocolsWorkflowStep):
    workflow: SelectLibraryProtocolsWorkflow
    template_path = "workflows/select_library_protocols/map_protocols.html"
    subforms = inputs.dynamic.SubFormList[ProtocolMappingSubForm](min_elements=0)

    def __init__(self, workflow: SelectLibraryProtocolsWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.library_table = pd.DataFrame()

    @classmethod
    def build(cls, workflow: SelectLibraryProtocolsWorkflow, session: SyncSession) -> Self:
        lab_prep = session.get_one(Q.lab_prep.select(id=workflow.lab_prep_id))
        if lab_prep.prep_file is None:
            raise exc.BadRequestException("Lab prep has no prep file associated with it.")

        path = os.path.join(config.settings.app_config.media_folder, lab_prep.prep_file.path)
        if not os.path.exists(path):
            raise exc.BadRequestException("Library prep file not found..")

        df = pd.read_excel(path, sheet_name="prep_table")
        if "library_kits" not in df.columns or df["library_kits"].isna().all():
            raise exc.BadRequestException("Prep file does not contain library kit information.")

        kit_rows = session.pd.get_protocol_kits()
        protocol_combos: list[dict] = []
        if not kit_rows.empty:
            for key, group in parsing.safe_groupby(
                kit_rows,
                ["protocol_id", "combination_num"],
                ProtocolComboKey,
            ):
                protocol_combos.append({
                    "protocol_id": key.protocol_id,
                    "combination_num": key.combination_num,
                    "identifiers": ";".join(sorted(group["kit_identifier"].astype(str))),
                })
        protocols_df = pd.DataFrame(protocol_combos, columns=["protocol_id", "combination_num", "identifiers"])

        library_table = df[["library_id", "library_name", "library_kits"]].copy()
        library_table = library_table[library_table["library_id"].notna()]
        library_table["library_id"] = library_table["library_id"].astype(pd.Int64Dtype())
        library_table["combination"] = None
        library_table["protocol_id"] = None

        for library in lab_prep.libraries:
            library_table.loc[library_table["library_id"] == library.id, "protocol_id"] = library.protocol_id

        stored = workflow.tables.get("library_table")
        if stored is not None and "protocol_id" in stored.columns and "library_id" in stored.columns:
            library_table["protocol_id"] = parsing.map_columns(
                library_table, stored, "library_id", "protocol_id",
            )

        kit_combinations: set[str] = set()
        for idx, row in library_table.iterrows():
            if pd.isna(row["library_kits"]):
                continue
            combination = ";".join(sorted(
                kit.strip().removeprefix("#") for kit in str(row["library_kits"]).strip().split(";")
            ))
            library_table.at[idx, "combination"] = combination
            kit_combinations.add(combination)

        protocol_choices = [
            (p.id, p.name)
            for p in session.get_all(Q.protocol.select(), order_by=models.Protocol.name.desc(), limit=None)
        ]
        protocol_mapping = dict(protocol_choices)

        form = cls(workflow=workflow)
        form.library_table = library_table
        form._context["lab_prep"] = lab_prep

        for combination in sorted(kit_combinations):
            entry = form.subforms.append_entry()
            entry.kit_combination.data = combination
            choices: list[tuple[int, str]] = [(-1, "Unknown")]

            matches = protocols_df[protocols_df["identifiers"] == combination] if not protocols_df.empty else protocols_df
            for _, row in matches.iterrows():
                protocol = session.get_one(Q.protocol.select(id=int(row["protocol_id"])))
                choices.append((int(row["protocol_id"]), protocol.name))

            if len(choices) == 1:
                choices = [(-1, "Unknown")] + protocol_choices

            combination_protocol_ids = library_table.loc[
                library_table["combination"] == combination, "protocol_id"
            ].unique().tolist()
            if len(combination_protocol_ids) == 1 and pd.notna(combination_protocol_ids[0]):
                protocol_id = int(combination_protocol_ids[0])
                if protocol_id not in dict(choices):
                    choices.append((protocol_id, protocol_mapping[protocol_id]))

            entry.protocol.set_options(choices)
            if ctx.request.method == "GET":
                entry.protocol.data = choices[-1][0]
                if len(choices) > 2:
                    entry.protocol.errors.append(
                        "Multiple protocols found for this kit combination. Please select the correct one."
                    )
                elif len(choices) == 0:
                    entry.protocol.errors.append("No protocols found for this kit combination.")

        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: SelectLibraryProtocolsWorkflow = Depends(SelectLibraryProtocolsWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> ProtocolMappingForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: ProtocolMappingForm = Depends(ProtocolMappingForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: ProtocolMappingForm = Depends(ProtocolMappingForm.Validate()),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            library_table = form.library_table.copy()
            for entry in form.subforms:
                if entry.protocol.data == -1:
                    continue
                library_table.loc[
                    library_table["combination"] == entry.kit_combination.data, "protocol_id"
                ] = entry.protocol.data

            form.workflow.tables["library_table"] = library_table
            return form.workflow.get_next_step(form).make_response()
        return route
