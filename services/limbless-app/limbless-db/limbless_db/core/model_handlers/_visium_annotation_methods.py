from ...models import VisiumAnnotation
from .. import exceptions


def create_visium_annotation(
    self, area: str, image: str, slide: str, commit: bool = True
) -> VisiumAnnotation:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    visium_annotation = VisiumAnnotation(
        area=area,
        image=image,
        slide=slide
    )
    self._session.add(visium_annotation)

    if commit:
        self._session.commit()
        self._session.refresh(visium_annotation)

    if not persist_session:
        self.close_session()

    return visium_annotation


def get_visium_annotation(self, visium_annotation_id: int) -> VisiumAnnotation:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    visium_annotation = self._session.get(VisiumAnnotation, visium_annotation_id)

    if not visium_annotation:
        raise exceptions.ElementDoesNotExist(f"VisiumAnnotation with id {visium_annotation_id} does not exist")

    if not persist_session:
        self.close_session()

    return visium_annotation