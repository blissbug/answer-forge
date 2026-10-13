import shutil
import uuid
from pathlib import Path
from typing import Protocol


class FileStorage(Protocol):
    def save(self, workspace_id: uuid.UUID, filename: str, source: Path) -> str: ...
    def exists(self, storage_path: str) -> bool: ...
    def get_path(self, storage_path: str) -> Path: ...
    def delete(self, storage_path: str) -> None: ...


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def save(self, workspace_id: uuid.UUID, filename: str, source: Path) -> str:
        return self._save_to_collection(workspace_id, "documents", filename, source)

    def save_questionnaire(self, workspace_id: uuid.UUID, filename: str, source: Path) -> str:
        return self._save_to_collection(workspace_id, "questionnaires", filename, source)

    def _save_to_collection(self, workspace_id: uuid.UUID, collection: str, filename: str, source: Path) -> str:
        safe_name = Path(filename).name
        relative = Path("workspaces") / str(workspace_id) / collection / f"{uuid.uuid4()}-{safe_name}"
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return str(relative)

    def exists(self, storage_path: str) -> bool:
        return self.get_path(storage_path).is_file()

    def get_path(self, storage_path: str) -> Path:
        path = (self.root / storage_path).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("Invalid storage path")
        return path

    def delete(self, storage_path: str) -> None:
        path = self.get_path(storage_path)
        if path.is_file():
            path.unlink()
