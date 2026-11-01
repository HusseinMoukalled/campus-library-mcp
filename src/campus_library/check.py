"""Credential-free integration check through the actual SDK MCP client and subprocess."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agents import set_tracing_disabled

from campus_library.agent import mcp_connection

EXPECTED_TOOLS = {"search_catalog", "reserve_book", "reserve_matching_book"}


def payload(result) -> dict:
    if result.structured_content:
        return result.structured_content
    return json.loads(result.content[0].text)


async def check(db_path: Path) -> None:
    set_tracing_disabled(True)
    async with mcp_connection(db_path) as server:
        tools = await server.list_tools()
        assert {tool.name for tool in tools} == EXPECTED_TOOLS
        assert all(tool.input_schema and tool.output_schema for tool in tools)
        print("PASS: SDK MCP client discovers exactly three typed tools.")
        for name, arguments in [
            ("search_catalog", {"query": "python"}),
            ("reserve_book", {"book_id": "B001", "student_id": "S1001"}),
            ("reserve_matching_book", {"query": "agents", "student_id": "S1001"}),
        ]:
            result = await server.call_tool(name, arguments)
            assert not result.is_error, result
            print(f"PASS: {name}: {json.dumps(payload(result))}")
        for name, arguments, error in [
            ("search_catalog", {"query": " "}, "INVALID_QUERY"),
            ("reserve_book", {"book_id": "B006", "student_id": "S1001"}, "NO_COPIES"),
            (
                "reserve_matching_book",
                {"query": "quantum dragons", "student_id": "S1001"},
                "NO_MATCH",
            ),
        ]:
            result = await server.call_tool(name, arguments)
            assert result.is_error and error in str(result.content)
            print(f"PASS: {name} returns explicit {error} error over MCP.")
    # New subprocess, same database: proves persistence across server restarts.
    async with mcp_connection(db_path) as server:
        result = await server.call_tool("reserve_book", {"book_id": "B001", "student_id": "S1001"})
        assert not result.is_error and payload(result)["already_reserved"]
        print("PASS: reservation survives restart; duplicate returns the original receipt.")


def main() -> None:
    with TemporaryDirectory(prefix="library-check-") as directory:
        asyncio.run(check(Path(directory) / "library.sqlite3"))
    print("All MCP integration checks passed. No model/API key was used.")


if __name__ == "__main__":
    main()
