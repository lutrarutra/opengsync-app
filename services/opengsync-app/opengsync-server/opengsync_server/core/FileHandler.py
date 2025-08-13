from pathlib import Path


class FileHandler:
    def __init__(self):
        self.__media_folder: Path | None = None
        self.__uploads_folder: Path | None = None
        self.__app_data_folder: Path | None = None
        self.__share_root: Path | None = None

    def init_app(
        self,
        media_folder: str | Path,
        uploads_folder: str | Path,
        app_data_folder: str | Path,
        share_root: str | Path
    ):
        self.__media_folder = media_folder if isinstance(media_folder, Path) else Path(media_folder)
        self.__uploads_folder = uploads_folder if isinstance(uploads_folder, Path) else Path(uploads_folder)
        self.__app_data_folder = app_data_folder if isinstance(app_data_folder, Path) else Path(app_data_folder)
        self.__share_root = share_root if isinstance(share_root, Path) else Path(share_root)

    @property
    def media_folder(self) -> Path:
        if not self.__media_folder:
            raise ValueError("Media folder is not initialized")
        return self.__media_folder

    @property
    def uploads_folder(self) -> Path:
        if not self.__uploads_folder:
            raise ValueError("Uploads folder is not initialized")
        return self.__uploads_folder

    @property
    def app_data_folder(self) -> Path:
        if not self.__app_data_folder:
            raise ValueError("App data folder is not initialized")
        return self.__app_data_folder

    @property
    def share_root(self) -> Path:
        if not self.__share_root:
            raise ValueError("Share root is not initialized")
        return self.__share_root
        