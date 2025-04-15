from .server import logger, mcp

def main():
    """Entry point function called by the script defined in pyproject.toml"""
    logger.info("Starting local Airtable MCP server via __main__.main()...")
    logger.info("Make sure AIRTABLE_PERSONAL_ACCESS_TOKEN is set.")
    logger.info("Use 'set_base_id' tool or set AIRTABLE_BASE_ID environment variable.")
    # This runs the server, making tools available to connected clients (like Claude Desktop)
    mcp.run()

if __name__ == "__main__":
    main() 