"""Input documents: one text file, one image, or a folder of page images."""

from dataclasses import dataclass
from pathlib import Path

from .errors import UnsupportedFileTypeError

TEXT_SUFFIXES = {".txt"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


@dataclass
class Document:
    source: str
    files: list[Path]

    @property
    def is_text(self) -> bool:
        return self.files[0].suffix.lower() in TEXT_SUFFIXES


def find_documents(path: Path) -> list[Document]:
    """A file is one document; in a directory every text/image file is one document and every
    subdirectory is one multi-page document (pages = images sorted by name)."""
    if path.is_file():
        if path.suffix.lower() not in IMAGE_SUFFIXES | TEXT_SUFFIXES:
            raise UnsupportedFileTypeError(
                f"{path}: unsupported file type (expected .txt or an image)"
            )
        return [Document(path.name, [path])]
    if not path.is_dir():
        raise FileNotFoundError(f"{path} does not exist")

    documents = []
    for entry in sorted(path.iterdir()):
        suffix = entry.suffix.lower()
        if entry.is_file() and suffix in IMAGE_SUFFIXES | TEXT_SUFFIXES:
            documents.append(Document(entry.name, [entry]))
        elif entry.is_dir():
            pages = sorted(p for p in entry.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
            if pages:
                documents.append(Document(entry.name, pages))
    return documents
