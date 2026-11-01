"""Verify Gemini actually selects each MCP tool. Uses a temporary reservation database.

Run from the repository root: python scripts/live_smoke.py
This is a functional integration test, not a recording/presentation guide.
"""

import asyncio
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from agents import OpenAIChatCompletionsModel, set_tracing_disabled
from openai import AsyncOpenAI

from campus_library.agent import (
    build_agent,
    explain_api_error,
    mcp_connection,
    run_turn,
    tool_names,
)
from campus_library.config import load_settings


async def main() -> None:
    load_settings()
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise SystemExit("Set GEMINI_API_KEY in .env before running the live test.")
    set_tracing_disabled(True)
    with TemporaryDirectory(prefix="library-live-") as directory:
        db_path = Path(directory) / "library.sqlite3"
        async with AsyncOpenAI(
            api_key=key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            max_retries=0,
            timeout=60,
        ) as client:
            async with mcp_connection(db_path) as server:
                model = OpenAIChatCompletionsModel(
                    os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"), client
                )
                agent = build_agent(server, model)
                cases = [
                    ("Find books about python. Only look up information.", "search_catalog", None),
                    ("Reserve book B001 for student S1001.", "reserve_book", None),
                    (
                        "Reserve an available book about agents for student S1002.",
                        "reserve_matching_book",
                        None,
                    ),
                    (
                        "Test the search tool with a blank query consisting of a single space.",
                        "search_catalog",
                        "INVALID_QUERY",
                    ),
                    (
                        "Try to reserve book B006 for student S1003 to test the failure case.",
                        "reserve_book",
                        "NO_COPIES",
                    ),
                    (
                        "Try to reserve a book about quantum dragons for student S1004.",
                        "reserve_matching_book",
                        "NO_MATCH",
                    ),
                ]
                for prompt, expected, error in cases:
                    print(f"\nLIVE REQUEST: {prompt}")
                    result = await run_turn(agent, prompt)
                    assert expected in tool_names(result), (expected, tool_names(result))
                    if error:
                        outputs = " ".join(
                            str(item.output)
                            for item in result.new_items
                            if item.type == "tool_call_output_item"
                        )
                        assert error in outputs, (error, outputs)
                    print(
                        f"PASS: Gemini selected {expected}"
                        + (f"; received {error}" if error else "")
                    )
                with closing(sqlite3.connect(db_path)) as connection:
                    assert (
                        connection.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 2
                    )
    print("PASS: live Gemini + Agents SDK + MCP round trips, including all three failures.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(explain_api_error(exc))
        raise SystemExit(1) from None
