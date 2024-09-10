from typing import Optional

from ... import models


def create_visium_annotation(
    self, area: str, image: str, slide: str, commit: bool = True
) -> models.VisiumAnnotation:
    if not (persist_session := self._session is not None):
        self.open_session()

    visium_annotation = models.VisiumAnnotation(
        area=area.strip(),
        image=image.strip(),
        slide=slide.strip()
    )
    self._session.add(visium_annotation)

    if commit:
        self._session.commit()
        self._session.refresh(visium_annotation)

    if not persist_session:
        self.close_session()

    return visium_annotation


def get_visium_annotation(self, visium_annotation_id: int) -> Optional[models.VisiumAnnotation]:
    if not (persist_session := self._session is not None):
        self.open_session()

    visium_annotation = self._session.get(models.VisiumAnnotation, visium_annotation_id)

    if not persist_session:
        self.close_session()

    return visium_annotation