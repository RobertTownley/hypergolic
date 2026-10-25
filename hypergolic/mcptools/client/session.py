from mcp import ClientSession, types


class LenientClientSession(ClientSession):
    # Some gateways advertise outputSchema but only return unstructured content;
    # the SDK treats that as fatal, we treat it as plain content.
    async def validate_tool_result(self, name: str, result: types.CallToolResult) -> None:
        if result.structured_content is None:
            return
        await super().validate_tool_result(name, result)
