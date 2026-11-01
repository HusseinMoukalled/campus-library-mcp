"""FastMCP server: exactly three tools and one read-only catalog resource."""

import logging
import sys
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from campus_library.config import database_path
from campus_library.models import ReservationResult, SearchResult, WorkflowResult
from campus_library.service import LibraryError, LibraryService

Query = Annotated[str, Field(description="Title, author, topic or book ID; 1-120 characters.")]
Student = Annotated[
    str, Field(description="Demo student ID: S followed by 4-8 digits, e.g. S1001.")
]


def create_server(db_path: Path | None = None) -> FastMCP:
    service = LibraryService(db_path if db_path is not None else database_path())
    mcp = FastMCP("Campus Library")

    def invoke(operation, *args):
        try:
            return operation(*args)
        except LibraryError as exc:
            logging.getLogger("campus_library").warning("TOOL ERROR %s", exc)
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "idempotentHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        }
    )
    def search_catalog(
        query: Query,
        limit: Annotated[int, Field(description="Maximum returned books, from 1 to 20.")] = 5,
    ) -> SearchResult:
        """DATA: Find books with live availability without changing state. All query words
        must match the title, author, topics or ID (case insensitive). Returns books sorted
        by ID and the total match count; no matches returns an empty list. Blank/oversized
        queries and invalid limits produce clear errors. This never reserves a book.
        """
        return invoke(service.search_catalog, query, limit)

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "idempotentHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        }
    )
    def reserve_book(
        book_id: Annotated[str, Field(description="Exact catalog ID, e.g. B001.")],
        student_id: Student,
    ) -> ReservationResult:
        """ACTION: Save one book reservation in local SQLite. Use when the user asks to
        reserve a specific known book ID and supplies a student ID. Returns a persisted
        receipt, or the existing receipt for a repeated student/book pair. Unknown IDs,
        invalid student IDs, exhausted copies and unavailable storage return clear errors.
        """
        return invoke(service.reserve_book, book_id, student_id)

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "idempotentHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        }
    )
    def reserve_matching_book(query: Query, student_id: Student) -> WorkflowResult:
        """ORCHESTRATION: Fulfil a request to reserve a book by topic/title rather than
        exact ID. Calls search_catalog then reserve_book using their shared implementations.
        Selects the first reservable match by book ID, reusing an existing reservation when
        encountered. Returns the receipt and executed steps. Invalid input, no match,
        no available match or unavailable storage produces a clear error. Changes local state.
        """
        return invoke(service.reserve_matching_book, query, student_id)

    @mcp.resource("catalog://books")
    def catalog() -> str:
        """Static fictional book metadata; availability is provided by search_catalog."""
        return "\n".join(book.model_dump_json() for book in service.books.values())

    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[MCP server] %(message)s")
    # stdout belongs exclusively to MCP JSON-RPC messages.
    create_server().run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
