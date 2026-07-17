import pandas as pd
from fastapi import Depends

from opengsync_db import models, queries as Q, SyncSession

from ...core import dependencies, responses
from ...components import inputs
from ...components.tables.spreadsheet import CategoricalDropDown, IntegerColumn, MissingCellValue, DuplicateCellValue
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class AddKitsToProtocolAction(HTMXForm):
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        CategoricalDropDown("kit_identifier", "Kit", 600, categories={}, required=True),
        IntegerColumn("combination_num", "Combination", 200, required=False),
    ])

    def __init__(self, protocol: models.Protocol) -> None:
        super().__init__()
        self.protocol = protocol
        self._context["protocol"] = protocol
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", protocol_id=protocol.id)
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            protocol_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "AddKitsToProtocolAction":
            
            protocol = session.get_one(Q.protocol.select(id=protocol_id))
            kit_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in session.get_all(Q.kit.select(), limit=None)}

            form = AddKitsToProtocolAction(protocol=protocol)
            form.spreadsheet.columns["kit_identifier"].set_categories(kit_mapping)
            return form
        return dependency

    @htmx_route("GET", "/{protocol_id}/add-kits")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "AddKitsToProtocolAction" = Depends(AddKitsToProtocolAction.Init()),
            _ = Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{protocol_id}/add-kits")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "AddKitsToProtocolAction" = Depends(AddKitsToProtocolAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _ = Depends(dependencies.require_insider),
        ):
            df = form.spreadsheet.data

            if df["combination_num"].isna().all():
                df["combination_num"] = 1

            duplicate = df.duplicated(subset=["kit_identifier", "combination_num"], keep=False)

            for idx, row in df.iterrows():
                if duplicate.at[idx]:
                    form.spreadsheet.add_error(idx, "kit_identifier", DuplicateCellValue("Duplicate kit and combination number."))
                if pd.isna(row["combination_num"]):
                    form.spreadsheet.add_error(idx, "combination_num", MissingCellValue("Combination number is required."))

            form.assert_valid()

            form.protocol.kit_links = []
        
            for _, row in df.iterrows():
                kit = session.get_one(Q.kit.select(identifier=row["kit_identifier"]))
                
                form.protocol.kit_links.append(
                    models.links.ProtocolKitLink(
                        protocol_id=form.protocol.id,
                        kit_id=kit.id,
                        combination_num=int(row["combination_num"]),
                    )
                )

            session.save(form.protocol)

            return responses.htmx_response(
                redirect=responses.url_for("protocol_page", protocol_id=form.protocol.id).include_query_params(tab="protocol-kits-tab"),
                flash=responses.flash("Changes Saved!", "success"),
            )
                
        return route