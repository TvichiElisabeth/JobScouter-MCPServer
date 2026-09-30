from mcp.server.mcpserver import MCPServer

mcp = MCPServer("JobScouterMCP")


@mcp.tool()
def list_companies() -> list[str]:
    """Names of all companies whose job boards JobScouterMCP tracks."""
    return ["Anthropic"]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()