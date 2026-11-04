"""String form fields must declare ``max_length`` so an overlong value is a field error, not a 500 at commit.

Regression for the customer test 2026-11-04: a 300-character request name passed every step and the
Create then failed with ``StringDataRightTruncation``. Fields that write to a length-limited column take
``max_length=models.<Model>.<column>.type.length``. ``KNOWN_MISSING`` lists the fields not yet limited;
it may only shrink.
"""
from fastapi.testclient import TestClient

from server.components.inputs.string import StringInputField, PasswordInputField

KNOWN_MISSING: set[str] = {
    # Text columns (unlimited) and values that are only looked up or parsed, never stored as is
    "actions.GenerateSequencerLoadingChecklistAction.ParameterSubForm.param_label",
    "actions.GenerateSequencerLoadingChecklistAction.ParameterSubForm.var_name",
    "actions.QueryBarcodeSequencesAction.QueryBarcodeSequencesAction.sequence",
    "actions.SharePathAction.RecipientSubForm.email",
    "actions.ShareProjectDataAction.ShareProjectDataAction.custom_email",
    "actions.ShareProjectDataAction.ShareProjectDataAction.recipients",
    "actions.dist_reads.DistributeReadsCombinedAction.PoolSubForm.pool_name",
    "actions.lane_pools.LanePoolsCombinedAction.SampleSubForm.dilution",
    "actions.lane_pools.LanePoolsSeparateAction.SampleSubForm.dilution",
    "auth.ActivationForm.ActivationForm.email",
    "auth.CompleteRegistrationForm.CompleteRegistrationForm.email",
    "auth.LoginForm.LoginForm.email",
    "auth.RegisterForm.RegisterForm.email",
    "auth.ResetPasswordForm.ResetPasswordForm.email",
    "common.SelectedPathsMixin.SelectedPathSubForm.path",
    "models.SeqRequestForm.BillingSubForm.address",
    "models.SeqRequestForm.OrganizationSubForm.address",
    "workflows.ba_report.BAReportForm.SubForm.name",
    "workflows.ba_report.BAReportForm.SubForm.type",
    "workflows.ba_report.CompleteBAReport.SubForm.name",
    "workflows.ba_report.CompleteBAReport.SubForm.type",
    "workflows.ba_report.ParseBAExcelFileForm.ParseBAExcelFileForm.left_order",
    "workflows.ba_report.ParseBAExcelFileForm.ParseBAExcelFileForm.right_order",
    "workflows.library_annotation.BarcodeMatchForm.BarcodeMatchForm.i5_primer",
    "workflows.library_annotation.BarcodeMatchForm.BarcodeMatchForm.i7_primer",
    "workflows.library_annotation.PoolMappingForm.PoolMappingSubForm.raw_label",
    "workflows.library_annotation.ProjectSelectForm.ProjectSelectForm.replaces_uuid",
    "workflows.qubit_measure.QubitMeasureForm.SubForm.name",
    "workflows.reindex.BarcodeMatchForm.BarcodeMatchForm.i5_primer",
    "workflows.reindex.BarcodeMatchForm.BarcodeMatchForm.i7_primer",
    "workflows.select_library_protocols.ProtocolMappingForm.ProtocolMappingSubForm.kit_combination",
}


def _form_classes():
    from server.forms.HTMXForm import HTMXForm
    from server.forms.SubHTMXForm import SubHTMXForm

    seen, stack = set(), [HTMXForm, SubHTMXForm]
    while stack:
        cls = stack.pop()
        for sub in cls.__subclasses__():
            if sub not in seen:
                seen.add(sub)
                stack.append(sub)
    return seen


def _unlimited_fields() -> set[str]:
    missing = set()
    for cls in _form_classes():
        if not cls.__module__.startswith("server.forms."):  # not test-local form classes
            continue
        for name, field in vars(cls).items():
            if isinstance(field, StringInputField) and not isinstance(field, PasswordInputField):
                if getattr(field, "max_length", None) is None:
                    missing.add(f"{cls.__module__.removeprefix('server.forms.')}.{cls.__name__}.{name}")
    return missing


def test_string_fields_declare_max_length(client: TestClient):
    missing = _unlimited_fields()
    assert missing - KNOWN_MISSING == set(), "add max_length=models.<Model>.<column>.type.length"
    assert KNOWN_MISSING - missing == set(), "remove fixed entries from KNOWN_MISSING"
