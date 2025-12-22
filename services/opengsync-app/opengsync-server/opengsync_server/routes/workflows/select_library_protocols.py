import os
import pandas as pd

from flask import Blueprint, request, flash

from opengsync_db import models
from opengsync_db.categories import PoolStatus, LibraryStatus
from opengsync_server.routes.htmx import lab_preps_htmx

from ... import db, logger  # noqa
from ...core import runtime
from ...forms.workflows import select_library_protocols as wff
from ...core import wrappers, exceptions

select_library_protocols_workflow = Blueprint("select_library_protocols_workflow", __name__, url_prefix="/workflows/select_library_protocols/")


@wrappers.htmx_route(select_library_protocols_workflow, db=db)
def begin(current_user: models.User, lab_prep_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()
    
    if lab_prep.prep_file is None:
        data = {
            "library_id": [],
            "protocol_id": [],
        }
        for library in lab_prep.libraries:
            data["library_id"].append(library.id)
            data["protocol_id"].append(library.protocol_id)
            
        library_table = pd.DataFrame(data)
        return wff.LibraryProtocolSelectForm(lab_prep=lab_prep, uuid=None, library_table=library_table).make_response()
        
    if os.path.exists(path := os.path.join(runtime.app.media_folder, lab_prep.prep_file.path)):
        df = pd.read_excel(path, sheet_name="prep_table")
    else:
        flash("Library prep file not found..", "warning")
        df = pd.DataFrame()
    if "library_kits" not in df.columns or df["library_kits"].isna().all():
        data = {
            "library_id": [],
            "protocol_id": [],
        }
        for library in lab_prep.libraries:
            data["library_id"].append(library.id)
            data["protocol_id"].append(library.protocol_id)
            
        library_table = pd.DataFrame(data)
        return wff.LibraryProtocolSelectForm(lab_prep=lab_prep, uuid=None, library_table=library_table).make_response()
        
    return wff.ProtocolMappingForm(lab_prep=lab_prep, uuid=None).make_response()



@wrappers.htmx_route(select_library_protocols_workflow, db=db, methods=["POST"])
def map_protocols(current_user: models.User, lab_prep_id: int, uuid: str):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()
    
    form = wff.ProtocolMappingForm(lab_prep=lab_prep, uuid=uuid, formdata=request.form)
    return form.process_request()

@wrappers.htmx_route(select_library_protocols_workflow, db=db, methods=["POST"])
def submit(current_user: models.User, lab_prep_id: int, uuid: str):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
        raise exceptions.NotFoundException()
    
    form = wff.LibraryProtocolSelectForm(lab_prep=lab_prep, uuid=uuid, formdata=request.form)
    return form.process_request()