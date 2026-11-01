# Verification record

Verified on November 1, 2026 using Windows and Python 3.12.10.

## Dependency versions

- FastMCP 4.1.4
- OpenAI Agents SDK 0.24.0
- MCP Python SDK 2.3.0
- OpenAI Python client 3.42.0
- Gemini model: `gemini-3.1-flash-lite`

The complete environment is pinned in `requirements.lock`, with a Windows-only
marker for `pywin32`.

## Completed checks

| Check | Result |
|---|---|
| `python -m ruff check .` | Passed |
| `python -m pytest -q` | 24 passed, no warnings |
| `python -m pip check` | No broken requirements |
| Real SDK MCP client + stdio subprocess | Passed, including server restart |
| Exactly three tools, typed schemas and annotations | Passed |
| Static `catalog://books` resource | Passed |
| Concurrent single-copy reservations | Exactly one succeeds; others receive `NO_COPIES` |
| Read-only search | Creates no storage and leaves existing database bytes unchanged |
| Windows SQLite connection cleanup | Passed |
| Git-tracked files scanned for the configured API key | No matches; `.env` excluded |

## Live Gemini integration

`python scripts/live_smoke.py` completed successfully with the locally configured
Gemini key. The model chose tools from their discovered schemas; calls were not
forced or replaced with a fake model.

| Request | Actual selected tool | Observed result |
|---|---|---|
| Find Python books | `search_catalog` | B001 and B002 with availability |
| Reserve B001 for S1001 | `reserve_book` | Persisted reservation receipt |
| Reserve an agents book for S1002 | `reserve_matching_book` | Search then save B003 |
| Search with a blank query | `search_catalog` | `INVALID_QUERY` |
| Reserve B006 for S1003 | `reserve_book` | `NO_COPIES` |
| Reserve a quantum dragons book for S1004 | `reserve_matching_book` | `NO_MATCH` |

The final database contained exactly two reservations, and temporary storage was
cleaned up successfully. The test left the normal chat database untouched.

Model selection was checked against the actual account: Gemini 2.5 Flash rejected
generation for a new user, while Gemini 3.8 Flash showed poor response latency.
Gemini 3.1 Flash-Lite completed the required tool-calling checks and is the default.
Future API availability and quotas remain provider-controlled; rerun the live
check before relying on a different model.
