import pandas as pd
import sqlalchemy as sa
from fastapi import Request
from fastapi.responses import Response

from opengsync_db import models, AsyncSession, queries as Q, categories as C

from loguru import logger

from ....core import exceptions as exc, responses, dependencies
from .... import utils
from ....components import inputs
from ....components.tables import IntegerColumn, TextColumn, CategoricalDropDown, DropdownColumn
from ....components.tables.spreadsheet import InvalidCellValue, MissingCellValue, DuplicateCellValue
from ...MultiStepForm import MultiStepForm


class PrepOligoMuxForm(MultiStepForm):
    """Oligo multiplexing annotation step of the mux_prep workflow.

    Ported from Flask ``CommonOligoMuxForm`` / ``OligoMuxForm`` to the
    FastAPI ``MultiStepForm`` base.
    """

    _step_name = "oligo_mux_annotation"
    _workflow_name = "mux_prep"
    _form_label = "form"

    template_path = "forms/workflows/mux_prep/mux_prep-oligo_mux_annotation.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("sample_name", "Sample Name", 170, required=True, read_only=True),
        TextColumn("sample_pool", "Multiplexing Pool", 170, required=True, read_only=True),
        CategoricalDropDown("kit", "Kit", 250, categories={}, required=False),
        TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length, clean_up_fnc=lambda x: utils.parsing.make_alpha_numeric(x)),
        TextColumn("barcode", "Sequence", 200, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: utils.parsing.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        TextColumn("pattern", "Pattern", 180, max_length=models.Feature.pattern.type.length, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        DropdownColumn("read", "Read", 80, choices=["R2", "R1"]),
    ])

    mux_type = C.MUXType.TENX_OLIGO

    def __init__(
        self,
        request: Request,
        lab_prep: models.LabPrep,
        uuid: str | None = None,
    ) -> None:
        super().__init__(
            request=request,
            workflow=self._workflow_name,
            uuid=uuid,
            step_name=self._step_name,
            step_args={},
        )
        self.lab_prep = lab_prep
        self._context["lab_prep"] = self.lab_prep

        self.pooling_table: pd.DataFrame | None = None
        self.mux_table: pd.DataFrame | None = None
        self.df: pd.DataFrame | None = None

        self.post_url = responses.url_for(
            "parse_oligo_mux_reference",
            lab_prep_id=self.lab_prep.id,
            uuid=self.uuid,
        )

    async def _init_msf_state(self) -> None:
        """Initialise step tracker, cache helpers, and load the pooling table."""
        await super()._init_msf_state()

        session: AsyncSession = self.request.state.db_session
        pooling_table = await session.pd.get_lab_prep_pooling_table(self.lab_prep.id, expand_mux=True)
        self.pooling_table = pooling_table[
            pooling_table["mux_type_id"].isin([C.MUXType.TENX_OLIGO.id, C.MUXType.TENX_ABC_HASH.id])
        ]
        self.mux_table = PrepOligoMuxForm.get_mux_table(self.pooling_table)

        # Load kit mapping
        kits_q = Q.feature_kit.select(type=C.FeatureType.CMO).order_by(models.FeatureKit.name.asc())
        kits = await session.get_all(kits_q, limit=None)
        self.kits_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in kits}

        editable = True  # insiders always have write access
        self.spreadsheet.configure(
            df=self.mux_table,
            post_url=self.post_url,
            csrf_token=self.csrf_token_value,
            editable=editable,
            allow_new_cols=False,
            allow_new_rows=False,
            allow_col_rename=False,
        )

    @staticmethod
    def get_mux_table(sample_pooling_table: pd.DataFrame) -> pd.DataFrame:
        """Extract unique mux rows from the pooling table."""
        df = sample_pooling_table.copy()
        for col in ("mux_read", "mux_pattern", "mux_barcode"):
            if col not in df.columns:
                df[col] = None

        mux_data: dict[str, list] = {
            "sample_name": [],
            "sample_pool": [],
            "barcode": [],
            "pattern": [],
            "read": [],
        }

        for (sample_name, sample_pool, mux_barcode, mux_pattern, mux_read), _ in df.groupby(
            ["sample_name", "sample_pool", "mux_barcode", "mux_pattern", "mux_read"],
            dropna=False, sort=False,
        ):
            mux_data["sample_name"].append(sample_name)
            mux_data["sample_pool"].append(sample_pool)
            mux_data["barcode"].append(mux_barcode)
            mux_data["pattern"].append(mux_pattern)
            mux_data["read"].append(mux_read)

        return pd.DataFrame(mux_data)

    async def validate(self):
        """Validate the submitted spreadsheet."""
        await super().validate()

        self.df = self.spreadsheet.data

        if "sample_name" not in self.df.columns or "sample_pool" not in self.df.columns:
            self.spreadsheet._add_general_error("Missing required columns: 'sample_name' and 'sample_pool'.")
            raise exc.FormValidationException(self)

        session: AsyncSession = self.request.state.db_session

        # Resolve kits
        kit_identifiers = self.df["kit"].dropna().unique().tolist()
        kits: dict[str, tuple[models.FeatureKit, pd.DataFrame]] = {}

        self.df["kit_id"] = None
        for identifier in kit_identifiers:
            kit = await session.get_one(Q.feature_kit.select(identifier=identifier))
            kit_df = await session.pd.get_feature_kit_features(kit.id)
            kits[identifier] = (kit, kit_df)
            self.df.loc[self.df["kit"] == identifier, "kit_id"] = kit.id

        kit_feature = pd.notna(self.df["kit"]) & pd.notna(self.df["feature"])
        custom_feature = pd.notna(self.df["barcode"]) & pd.notna(self.df["pattern"]) & pd.notna(self.df["read"])
        invalid_feature = (pd.notna(self.df["kit"]) | pd.notna(self.df["feature"])) & (pd.notna(self.df["barcode"]) | pd.notna(self.df["pattern"]) | pd.notna(self.df["read"]))

        # Fill barcode/pattern/read from kit features
        for identifier, (kit, kit_df) in kits.items():
            view = self.df[self.df["kit"] == identifier]
            kit_df_resolved = kit_df.copy()
            kit_df_resolved["barcode"] = kit_df_resolved["sequence"]
            mask = kit_df_resolved["name"].isin(view["feature"])

            for _, kit_row in kit_df_resolved[mask].iterrows():
                self.df.loc[
                    (self.df["kit"] == identifier) & (self.df["feature"] == kit_row["name"]),
                    ["barcode", "pattern", "read"]
                ] = kit_row[["barcode", "pattern", "read"]].values

        duplicate_oligo = (
            (self.df.duplicated(subset=["sample_pool", "barcode", "pattern", "read"], keep=False) & custom_feature)
            | (self.df.duplicated(subset=["sample_pool", "kit", "feature"], keep=False) & kit_feature)
        )

        for idx, row in self.df.iterrows():
            if kit_feature.at[idx]:
                identifier = row["kit"]
                _, kit_df = kits[identifier]
                if pd.notna(row["feature"]) and row["feature"] not in kit_df["name"].values:
                    self.spreadsheet._add_error(idx, "feature", InvalidCellValue(
                        f"Feature '{row['feature']}' not found in kit '{identifier}'"
                    ))
                    continue

            if not custom_feature.at[idx] and not kit_feature.at[idx]:
                for col in ("kit", "feature", "barcode", "pattern", "read"):
                    self.spreadsheet._add_error(idx, col, MissingCellValue(
                        "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."
                    ))
            elif custom_feature.at[idx] and kit_feature.at[idx]:
                for col in ("kit", "feature", "barcode", "pattern", "read"):
                    self.spreadsheet._add_error(idx, col, InvalidCellValue(
                        "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."
                    ))
            elif invalid_feature.at[idx]:
                if pd.notna(row["kit"]):
                    self.spreadsheet._add_error(idx, "kit", InvalidCellValue(
                        "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."
                    ))
                for col in ("feature", "barcode", "pattern", "read"):
                    if pd.notna(row[col]):
                        self.spreadsheet._add_error(idx, col, InvalidCellValue(
                            "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."
                        ))

            if duplicate_oligo.at[idx]:
                for col in ("barcode", "pattern", "read", "kit", "feature"):
                    self.spreadsheet._add_error(idx, col, DuplicateCellValue(
                        "Definitions must be unique for each sample."
                    ))

        self._kits = kits
        if len(self.spreadsheet._errors) > 0:
            raise exc.FormValidationException(self)

        self.df["custom_feature"] = custom_feature
        self.df["kit_feature"] = kit_feature

    async def process_request(self) -> Response:
        """Validate and persist mux annotations to the database."""
        await self.validate()

        assert self.df is not None
        assert self.pooling_table is not None

        self.df["mux_read"] = self.df["read"]
        self.df["mux_barcode"] = self.df["barcode"]
        self.df["mux_pattern"] = self.df["pattern"]

        session: AsyncSession = self.request.state.db_session

        self.pooling_table["mux_read"] = utils.parsing.map_columns(
            self.pooling_table, self.df, ["sample_name", "sample_pool"], "mux_read"
        )
        self.pooling_table["mux_barcode"] = utils.parsing.map_columns(
            self.pooling_table, self.df, ["sample_name", "sample_pool"], "mux_barcode"
        )
        self.pooling_table["mux_pattern"] = utils.parsing.map_columns(
            self.pooling_table, self.df, ["sample_name", "sample_pool"], "mux_pattern"
        )

        for _, row in self.pooling_table.iterrows():
            sample_id = int(row["sample_id"])
            library_id = int(row["library_id"])

            link = await session.first(
                sa.select(models.links.SampleLibraryLink).where(
                    models.links.SampleLibraryLink.sample_id == sample_id,
                    models.links.SampleLibraryLink.library_id == library_id,
                )
            )
            if link is None:
                logger.error(f"Could not find link for sample {sample_id} and library {library_id}")
                raise exc.OpeNGSyncServerException("Internal error")

            if link.mux is None:
                link.mux = {}

            link.mux["barcode"] = row["mux_barcode"]
            link.mux["read"] = row["mux_read"]
            link.mux["pattern"] = row["mux_pattern"]

            await session.save(link)

        flash = responses.flash("Changes saved!", "success")
        return await responses.htmx_response(
            redirect=responses.url_for("lab_prep_page", lab_prep_id=self.lab_prep.id),
            flash=flash,
        )

