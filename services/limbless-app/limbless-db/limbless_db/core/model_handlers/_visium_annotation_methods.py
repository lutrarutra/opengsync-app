from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..DBHandler import DBHandler
from ... import models


def create_visium_annotation(
    self: "DBHandler", area: str, image: str, slide: str, commit: bool = True
) -> models.VisiumAnnotation:
    if not (persist_session := self._session is not None):
        self.open_session()

    visium_annotation = models.VisiumAnnotation(
        area=area.strip(),
        image=image.strip(),
        slide=slide.strip()
    )
    self.session.add(visium_annotation)

    if commit:
        self.session.commit()
        self.session.refresh(visium_annotation)

    if not persist_session:
        self.close_session()

    return visium_annotation


def get_visium_annotation(self: "DBHandler", visium_annotation_id: int) -> Optional[models.VisiumAnnotation]:
    if not (persist_session := self._session is not None):
        self.open_session()

    visium_annotation = self.session.get(models.VisiumAnnotation, visium_annotation_id)

    if not persist_session:
        self.close_session()

    return visium_annotation