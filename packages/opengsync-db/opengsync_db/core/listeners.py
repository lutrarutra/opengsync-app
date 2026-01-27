import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session

from .. import models


# @event.listens_for(Session, "before_flush")
# def delete_orphan_samples(session, flush_context, instances):
#     # find libraries being deleted in this flush
#     for obj in session.deleted:
#         if isinstance(obj, models.Library):
#             library_id = obj.id
#             # Find samples linked only to this library
#             orphan_sample_ids_subq = (
#                 session.query(models.Sample.id)
#                 .join(models.links.SampleLibraryLink)
#                 .group_by(models.Sample.id)
#                 .having(sa.func.count(models.links.SampleLibraryLink.library_id) == 1)
#                 .filter(models.links.SampleLibraryLink.library_id == library_id)
#                 .subquery()
#             )
#             # Delete orphan samples
#             session.query(models.Sample).filter(models.Sample.id.in_(orphan_sample_ids_subq)).delete(synchronize_session=False)