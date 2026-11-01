import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from campus_library.service import LibraryError, LibraryService


@pytest.fixture
def service(tmp_path):
    return LibraryService(tmp_path / "nested" / "library.sqlite3")


def test_data_tool_never_creates_storage(service):
    result = service.search_catalog("PYTHON")
    assert [book.book_id for book in result.books] == ["B001", "B002"]
    assert result.books[0].available_copies == 2
    assert not service.db_path.parent.exists()
    assert service.search_catalog("no such book").books == []


@pytest.mark.parametrize(
    "query,limit,code",
    [
        (" ", 5, "INVALID_QUERY"),
        ("x" * 121, 5, "INVALID_QUERY"),
        ("python", 0, "INVALID_LIMIT"),
        ("python", 21, "INVALID_LIMIT"),
        ("python", True, "INVALID_LIMIT"),
    ],
)
def test_data_failures(service, query, limit, code):
    with pytest.raises(LibraryError, match=code):
        service.search_catalog(query, limit)


def test_search_limit_and_all_word_matching(service):
    result = service.search_catalog("python", limit=1)
    assert result.total_matches == 2 and len(result.books) == 1
    assert service.search_catalog("async python").books[0].book_id == "B002"
    assert service.search_catalog("python sql").total_matches == 0


def test_action_persistence_idempotency_and_data_purity(service):
    first = service.reserve_book("B001", "S1001")
    assert not first.already_reserved
    restarted = LibraryService(service.db_path)
    duplicate = restarted.reserve_book("B001", "S1001")
    assert duplicate.already_reserved and duplicate.reservation == first.reservation
    before = service.db_path.read_bytes()
    assert restarted.search_catalog("B001").books[0].available_copies == 1
    assert service.db_path.read_bytes() == before
    with closing(sqlite3.connect(service.db_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 1


@pytest.mark.parametrize(
    "book_id,student_id,code",
    [
        ("B999", "S1001", "BOOK_NOT_FOUND"),
        ("B006", "S1001", "NO_COPIES"),
        ("B001", "1001", "INVALID_STUDENT_ID"),
        ("B001", "S1001'; DROP TABLE reservations;--", "INVALID_STUDENT_ID"),
    ],
)
def test_action_failures(service, book_id, student_id, code):
    with pytest.raises(LibraryError, match=code):
        service.reserve_book(book_id, student_id)


def test_concurrent_reservations_cannot_overbook(service):
    def reserve(student):
        try:
            return service.reserve_book("B002", student)
        except LibraryError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(reserve, [f"S100{i}" for i in range(5)]))
    assert sum(not isinstance(result, str) for result in results) == 1
    assert results.count("NO_COPIES") == 4
    assert service.search_catalog("B002").books[0].available_copies == 0


def test_orchestration_calls_both_shared_operations(service, monkeypatch):
    calls = []
    original_search, original_reserve = service.search_catalog, service.reserve_book

    def search(*args, **kwargs):
        calls.append("search_catalog")
        return original_search(*args, **kwargs)

    def reserve(*args):
        calls.append("reserve_book")
        return original_reserve(*args)

    monkeypatch.setattr(service, "search_catalog", search)
    monkeypatch.setattr(service, "reserve_book", reserve)
    first = service.reserve_matching_book("agents", "S1001")
    assert calls == first.steps == ["search_catalog", "reserve_book"]
    assert first.result.reservation.book_id == "B003"
    assert service.reserve_matching_book("agents", "S1001").result.already_reserved


def test_orchestration_skips_full_books(service):
    service.reserve_book("B001", "S1001")
    service.reserve_book("B001", "S1002")
    result = service.reserve_matching_book("python", "S1003")
    assert result.result.reservation.book_id == "B002"


@pytest.mark.parametrize(
    "query,student,code",
    [
        ("dragons", "S1001", "NO_MATCH"),
        ("robotics", "S1001", "NO_AVAILABLE_MATCH"),
        (" ", "S1001", "INVALID_QUERY"),
        ("agents", "bad", "INVALID_STUDENT_ID"),
    ],
)
def test_orchestration_failure_no_reservation(service, query, student, code):
    with pytest.raises(LibraryError, match=code):
        service.reserve_matching_book(query, student)
    if service.db_path.exists():
        with closing(sqlite3.connect(service.db_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 0


def test_storage_failure_is_explicit(tmp_path):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("file")
    service = LibraryService(blocked / "library.sqlite3")
    with pytest.raises(LibraryError, match="STORAGE_UNAVAILABLE"):
        service.reserve_book("B001", "S1001")


def test_database_connections_are_closed(service):
    service.reserve_book("B001", "S1001")
    service.search_catalog("python")
    # Windows refuses to unlink a database when a SQLite connection still owns it.
    service.db_path.unlink()
    assert not service.db_path.exists()
