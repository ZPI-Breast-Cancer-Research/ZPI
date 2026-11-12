import pytest

from workers.extraction.documents import Document, find_documents
from workers.extraction.errors import UnsupportedFileTypeError


@pytest.mark.parametrize("name", ["opis.txt", "skan.jpg", "skan.PNG"])
def test_single_supported_file_is_one_document(tmp_path, name):
    # Arrange
    path = tmp_path / name
    path.write_bytes(b"x")

    # Act
    documents = find_documents(path)

    # Assert
    assert documents == [Document(name, [path])]


def test_single_unsupported_file_is_rejected(tmp_path):
    # Arrange
    path = tmp_path / "opis.pdf"
    path.write_bytes(b"x")

    # Act / Assert
    with pytest.raises(UnsupportedFileTypeError, match="opis.pdf"):
        find_documents(path)


def test_missing_path_is_rejected(tmp_path):
    # Act / Assert
    with pytest.raises(FileNotFoundError):
        find_documents(tmp_path / "nie-ma")


def test_directory_lists_files_sorted_and_skips_unsupported(tmp_path):
    # Arrange
    for name in ("b.jpg", "a.txt", "notes.pdf", "c.png"):
        (tmp_path / name).write_bytes(b"x")

    # Act
    documents = find_documents(tmp_path)

    # Assert
    assert [d.source for d in documents] == ["a.txt", "b.jpg", "c.png"]


def test_subdirectory_is_one_document_with_pages_sorted_by_name(tmp_path):
    # Arrange
    folder = tmp_path / "skan"
    folder.mkdir()
    for name in ("page2.jpg", "page1.jpg", "readme.txt"):
        (folder / name).write_bytes(b"x")

    # Act
    documents = find_documents(tmp_path)

    # Assert
    assert len(documents) == 1
    assert documents[0].source == "skan"
    assert [p.name for p in documents[0].files] == ["page1.jpg", "page2.jpg"]


def test_subdirectory_without_images_is_skipped(tmp_path):
    # Arrange
    folder = tmp_path / "pusty"
    folder.mkdir()
    (folder / "readme.txt").write_text("x")

    # Act
    documents = find_documents(tmp_path)

    # Assert
    assert documents == []


@pytest.mark.parametrize(("name", "expected"), [("opis.TXT", True), ("skan.jpg", False)])
def test_document_is_text_by_first_file_suffix(tmp_path, name, expected):
    # Arrange
    document = Document(name, [tmp_path / name])

    # Act / Assert
    assert document.is_text is expected
