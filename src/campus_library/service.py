"""Deterministic library operations; no model, network, or MCP dependency."""

import json
import logging
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from campus_library.models import (
    Book,
    BookAvailability,
    Reservation,
    ReservationResult,
    SearchResult,
    WorkflowResult,
)

logger = logging.getLogger("campus_library")


class LibraryError(ValueError):
    """An expected domain failure with a stable, human-readable code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class LibraryService:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        catalog = json.loads(files("campus_library").joinpath("catalog.json").read_text())
        self.books = {book.book_id: book for book in map(Book.model_validate, catalog)}

    @contextmanager
    def _connection(self):
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.db_path, timeout=5)) as connection, connection:
                connection.row_factory = sqlite3.Row
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS reservations ("
                    "reservation_id TEXT PRIMARY KEY, book_id TEXT NOT NULL, "
                    "title TEXT NOT NULL, student_id TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "UNIQUE(book_id, student_id))"
                )
                yield connection
        except (sqlite3.Error, OSError) as exc:
            raise LibraryError(
                "STORAGE_UNAVAILABLE",
                "Reservation storage is unavailable; check its path/permissions.",
            ) from exc

    @staticmethod
    def _query(query: str) -> str:
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 120:
            raise LibraryError("INVALID_QUERY", "Query must contain 1 to 120 non-blank characters.")
        return query.strip()

    @staticmethod
    def _student(student_id: str) -> str:
        if not isinstance(student_id, str) or not re.fullmatch(r"S[0-9]{4,8}", student_id):
            raise LibraryError("INVALID_STUDENT_ID", "Use S followed by 4 to 8 digits, e.g. S1001.")
        return student_id

    def _counts(self) -> dict[str, int]:
        # Read-only search does not create files, tables, or directories.
        if not self.db_path.exists():
            return {}
        try:
            uri = self.db_path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=5)) as connection:
                return dict(
                    connection.execute(
                        "SELECT book_id, COUNT(*) FROM reservations GROUP BY book_id"
                    )
                )
        except sqlite3.Error as exc:
            raise LibraryError(
                "STORAGE_UNAVAILABLE", "Cannot read reservation availability."
            ) from exc

    def search_catalog(self, query: str, limit: int = 5) -> SearchResult:
        """Read matching books; AND-match query words; sort by book ID."""
        query = self._query(query)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise LibraryError("INVALID_LIMIT", "Limit must be an integer from 1 to 20.")
        logger.info("DATA search_catalog query=%r", query)
        counts = self._counts()
        matches = []
        for book in sorted(self.books.values(), key=lambda item: item.book_id):
            searchable = " ".join([book.book_id, book.title, book.author, *book.topics]).casefold()
            if all(word in searchable for word in query.casefold().split()):
                matches.append(
                    BookAvailability(
                        **book.model_dump(),
                        available_copies=max(0, book.copies - counts.get(book.book_id, 0)),
                    )
                )
        # No matches is a valid search result, not a transport failure.
        return SearchResult(query=query, total_matches=len(matches), books=matches[:limit])

    def reserve_book(self, book_id: str, student_id: str) -> ReservationResult:
        """Persist one reservation; repeated student/book requests are idempotent."""
        student_id = self._student(student_id)
        if book_id not in self.books:
            raise LibraryError(
                "BOOK_NOT_FOUND", f"Unknown book ID {book_id!r}; search the catalog first."
            )
        book = self.books[book_id]
        logger.info("ACTION reserve_book book=%s student=%s", book_id, student_id)
        with self._connection() as connection:
            # Serialize read/check/write so concurrent callers cannot overbook a copy.
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM reservations WHERE book_id=? AND student_id=?",
                (book_id, student_id),
            ).fetchone()
            if existing:
                return ReservationResult(
                    reservation=Reservation(**dict(existing)), already_reserved=True
                )
            used = connection.execute(
                "SELECT COUNT(*) FROM reservations WHERE book_id=?", (book_id,)
            ).fetchone()[0]
            if used >= book.copies:
                raise LibraryError(
                    "NO_COPIES", f"No reservable copies remain for {book_id}: {book.title}."
                )
            reservation = Reservation(
                reservation_id="R-" + uuid4().hex[:12],
                book_id=book_id,
                title=book.title,
                student_id=student_id,
                created_at=datetime.now(UTC).isoformat(),
            )
            connection.execute(
                "INSERT INTO reservations VALUES (?, ?, ?, ?, ?)",
                (
                    reservation.reservation_id,
                    book_id,
                    book.title,
                    student_id,
                    reservation.created_at,
                ),
            )
        return ReservationResult(reservation=reservation, already_reserved=False)

    def reserve_matching_book(self, query: str, student_id: str) -> WorkflowResult:
        """Coordinate search_catalog then reserve_book, without duplicating either."""
        query = self._query(query)
        self._student(student_id)
        logger.info("ORCHESTRATION reserve_matching_book begin")
        search = self.search_catalog(query, limit=20)
        if not search.books:
            raise LibraryError("NO_MATCH", f"No books match {query!r}; try a broader topic.")
        # Existing reservations are returned by reserve_book; trying every candidate also
        # handles availability changing between search and the transactional action.
        for book in search.books:
            try:
                result = self.reserve_book(book.book_id, student_id)
            except LibraryError as exc:
                if exc.code == "NO_COPIES":
                    continue
                raise
            return WorkflowResult(
                query=query,
                selection_policy="First reservable match by book_id; reuse existing reservation.",
                steps=["search_catalog", "reserve_book"],
                result=result,
            )
        raise LibraryError("NO_AVAILABLE_MATCH", "Matching books exist, but none can be reserved.")
