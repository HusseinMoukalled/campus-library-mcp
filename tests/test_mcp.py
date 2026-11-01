from fastmcp import Client

from campus_library.check import EXPECTED_TOOLS, check
from campus_library.server import create_server


async def test_real_stdio_transport_and_sdk_client(tmp_path):
    await check(tmp_path / "library.sqlite3")


async def test_schemas_annotations_resource_and_input_validation(tmp_path):
    async with Client(create_server(tmp_path / "library.sqlite3")) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == EXPECTED_TOOLS
        for tool in tools:
            assert tool.description
            assert tool.output_schema
            assert tool.input_schema["properties"]
            assert tool.annotations.read_only_hint == (tool.name == "search_catalog")
        resources = await client.list_resources()
        assert [str(resource.uri) for resource in resources] == ["catalog://books"]
        content = await client.read_resource("catalog://books")
        assert "B001" in content[0].text
        assert not (tmp_path / "library.sqlite3").exists()
        # Wrong JSON type/missing argument must fail at the actual MCP boundary.
        for name, arguments in [
            ("search_catalog", {"query": ["python"]}),
            ("reserve_book", {"book_id": "B001"}),
            ("reserve_matching_book", {"query": "agents", "student_id": 1001}),
        ]:
            result = await client.call_tool(name, arguments, raise_on_error=False)
            assert result.is_error


async def test_action_error_result_over_transport(tmp_path):
    async with Client(create_server(tmp_path / "library.sqlite3")) as client:
        result = await client.call_tool(
            "reserve_book", {"book_id": "B999", "student_id": "S1001"}, raise_on_error=False
        )
        assert result.is_error and "BOOK_NOT_FOUND" in result.content[0].text
