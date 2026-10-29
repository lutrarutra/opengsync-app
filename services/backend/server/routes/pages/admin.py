from fastapi import APIRouter, Depends, Request

from ...core import dependencies, responses, config, audit_reader, affiliation_values

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(dependencies.require_admin)])


@router.get("/chat", name="admin_chat_page")
def admin_chat_page():
    return responses.html_response(template="admin_chat_page.html", title="Chat")


@router.get("/audits", name="admin_audits_page")
def admin_audits_page(request: Request):
    # the filters are passed on to the audit log so links to a filtered view work
    filters = {k: request.query_params.get(k, "") for k in audit_reader.FILTERS}
    today = config.settings.now().date()
    try:
        # show the dates the log will cover, also when they are left out
        flt = audit_reader.parse_filter(filters, today=today)
        filters |= {"start": flt.start.isoformat(), "end": flt.end.isoformat()}
    except ValueError:
        pass  # the log shows the error
    return responses.html_response(
        template="audits_page.html", title="Audit Log", filters=filters, today=today,
        methods=audit_reader.METHODS, ops=audit_reader.OPS, tables=audit_reader.known_tables(),
    )


@router.get("/shares", name="admin_shares_page")
def admin_shares_page():
    return responses.html_response(template="admin_shares_page.html", title="Shares")


@router.get("/affiliations", name="admin_affiliations_page")
def admin_affiliations_page():
    return responses.html_response(template="admin_affiliations_page.html", title="Affiliations", kinds=list(affiliation_values.Kind))
