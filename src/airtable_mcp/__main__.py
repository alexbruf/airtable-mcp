from .server import logger, mcp

if __name__ == "__main__":
    logger.info("Starting local Airtable MCP server...")
    logger.info("Make sure AIRTABLE_PERSONAL_ACCESS_TOKEN is set.")
    logger.info("Use 'set_base_id' tool or set AIRTABLE_BASE_ID environment variable.")
    # This runs the server, making tools available to connected clients (like Claude Desktop)
    mcp.run() 