from typing import TYPE_CHECKING

import pandas as pd

from flask import Blueprint, request, abort, Response
from flask_login import login_required

from opengsync_db import models, db_session
from opengsync_db.categories import HTTPResponse, IndexType

from .... import db, logger  # noqa
from ....forms.workflows import reindex as forms
from ....forms import SelectSamplesForm
from ....tools import exceptions
from ....forms.MultiStepForm import MultiStepForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user  # noqa

reindex_workflow = Blueprint("reindex_workflow", __name__, url_prefix="/api/workflows/reindex/")


def get_context(args: dict) -> dict:
    context = {}
    if (seq_request_id := args.get("seq_request_id")) is not None:
        seq_request_id = int(seq_request_id)
        if (seq_request := db.get_seq_request(seq_request_id)) is None:
            raise exceptions.NotFoundException()
        if not current_user.is_insider() and seq_request.requestor_id != current_user.id:
            affiliation = db.get_group_user_affiliation(user_id=current_user.id, group_id=seq_request.group_id) if seq_request.group_id else None
            if affiliation is None:
                raise exceptions.NoPermissionsException()
        context["seq_request"] = seq_request
        
    elif (lab_prep_id := args.get("lab_prep_id")) is not None:
        lab_prep_id = int(lab_prep_id)
        if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
            raise exceptions.NotFoundException()
        context["lab_prep"] = lab_prep

    if not current_user.is_insider():
        if "seq_request" not in context:
            return abort(HTTPResponse.FORBIDDEN.id)
        
    return context


@reindex_workflow.route("begin", methods=["GET"])
@db_session(db)
@login_required
def begin() -> Response:
    try:
        context = get_context(request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpenGSyncException as e:
        return abort(e.response.id)
        
    form = SelectSamplesForm(
        "reindex", context=context,
        select_libraries=True
    )
    return form.make_response()


@reindex_workflow.route("select", methods=["POST"])
@db_session(db)
@login_required
def select():
    try:
        context = get_context(request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpenGSyncException as e:
        return abort(e.response.id)
    
    form: SelectSamplesForm = SelectSamplesForm(
        "reindex", formdata=request.form, context=context,
        select_libraries=True
    )

    if not form.validate():
        return form.make_response()

    library_data = {
        "library_id": [],
        "library_name": [],
        "library_type_id": [],
        "index_well": [],
        "kit_i7": [],
        "name_i7": [],
        "sequence_i7": [],
        "kit_i5": [],
        "name_i5": [],
        "sequence_i5": [],
    }

    for _, row in form.library_table.iterrows():
        if (library := db.get_library(int(row["id"]))) is None:
            logger.error(f"Library {library} not found in database")
            raise Exception("Library not found in database")
        
        if len(library.indices) == 0:
            library_data["library_id"].append(library.id)
            library_data["index_well"].append(None)
            library_data["library_type_id"].append(library.type.id if library.type else None)
            library_data["library_name"].append(library.name)
            library_data["kit_i7"].append(None)
            library_data["name_i7"].append(None)
            library_data["sequence_i7"].append(None)
            library_data["kit_i5"].append(None)
            library_data["name_i5"].append(None)
            library_data["sequence_i5"].append(None)

        else:
            kit_i7s = []
            names_i7 = []
            sequences_i7 = []

            for (kit_i7_id, name_i7), seqs_i7 in library.adapters_i7().items():
                if kit_i7_id is not None:
                    if (kit_i7 := db.get_index_kit(kit_i7_id)) is None:
                        logger.error(f"Index kit {kit_i7_id} not found in database")
                        raise Exception("Index kit not found in database")
                    kit_i7 = kit_i7.identifier
                else:
                    kit_i7 = None
                kit_i7s.append(kit_i7)
                names_i7.append(name_i7)
                sequences_i7.append(";".join(seqs_i7))

            kit_i5s = []
            names_i5 = []
            sequences_i5 = []
            for (kit_i5_id, name_i5), seqs_i5 in library.adapters_i5().items():
                if kit_i5_id is not None:
                    if (kit_i5 := db.get_index_kit(kit_i5_id)) is None:
                        logger.error(f"Index kit {kit_i5_id} not found in database")
                        raise Exception("Index kit not found in database")
                    kit_i5 = kit_i5.identifier
                else:
                    kit_i5 = None
                kit_i5s.append(kit_i5)
                names_i5.append(name_i5)
                sequences_i5.append(";".join(seqs_i5))

            library_data["library_id"].append(library.id)
            library_data["index_well"].append(None)
            library_data["library_name"].append(library.name)
            library_data["library_type_id"].append(library.type.id if library.type else None)
            library_data["kit_i7"].append(";".join(kit_i7s))
            library_data["name_i7"].append(";".join(names_i7))
            library_data["sequence_i7"].append(";".join(sequences_i7))
            library_data["kit_i5"].append(";".join(kit_i5s))
            library_data["name_i5"].append(";".join(names_i5))
            library_data["sequence_i5"].append(";".join(sequences_i5))
    
    df = pd.DataFrame(library_data)
    form.add_table("library_table", df)
    form.update_data()

    next_form = forms.BarcodeInputForm(
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
        uuid=form.uuid,
        previous_form=form
    )
    return next_form.make_response()

        
@reindex_workflow.route("reindex/<string:uuid>", methods=["POST"])
@db_session(db)
@login_required
def reindex(uuid: str):
    try:
        context = get_context(request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpenGSyncException as e:
        return abort(e.response.id)
    
    form = forms.BarcodeInputForm(
        uuid=uuid, formdata=request.form,
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep")
    )
    return form.process_request()


@reindex_workflow.route("map_index_kits/<string:uuid>", methods=["POST"])
@db_session(db)
@login_required
def map_index_kits(uuid: str):
    try:
        context = get_context(request.args)
    except ValueError:
        return abort(HTTPResponse.BAD_REQUEST.id)
    except exceptions.OpenGSyncException as e:
        return abort(e.response.id)
    
    form = forms.IndexKitMappingForm(
        uuid=uuid, formdata=request.form,
        seq_request=context.get("seq_request"),
        lab_prep=context.get("lab_prep"),
    )
    return form.process_request()
    

    
    