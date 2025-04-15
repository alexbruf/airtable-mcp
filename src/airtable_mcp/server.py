#!/usr/bin/env python3
"""
Airtable MCP Local Server
-------------------------
A simple local MCP server that implements the Airtable tools.
Relies on environment variables for configuration:
- AIRTABLE_PERSONAL_ACCESS_TOKEN
- AIRTABLE_BASE_ID (optional, can be set via tool)
"""
import os
import sys
import json
import logging
import requests
import traceback
from typing import Optional, Dict, Any, List
from mcp.server.fastmcp import FastMCP

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("airtable-mcp-local")

# Create MCP server instance
# The name "Airtable Tools" will be used if connecting via Claude Desktop config
mcp = FastMCP("Airtable Tools")

# Get token and base_id from environment variables
token = os.environ.get("AIRTABLE_PERSONAL_ACCESS_TOKEN", "")
base_id = os.environ.get("AIRTABLE_BASE_ID", "") # This can be overridden by the set_base_id tool

if not token:
    logger.warning("No Airtable API token found in AIRTABLE_PERSONAL_ACCESS_TOKEN environment variable.")
else:
    logger.info(f"Using Airtable token: {token[:5]}...{token[-5:]}")

if base_id:
    logger.info(f"Using default base ID: {base_id}")
else:
    logger.info("No default base ID set in AIRTABLE_BASE_ID. provide 'base_id_param'.")

# Helper function for Airtable API calls (remains largely the same)
# Note: Using synchronous 'requests' here. If performance becomes an issue with many tools,
# consider using an async HTTP client like 'httpx'.
def api_call(endpoint, method="GET", data=None, params=None) -> Dict[str, Any]:
    """Make an Airtable API call using synchronous requests."""
    if not token:
        # Raising an exception might be better for tools to handle, but returning error dict for now
        return {"error": {"message": "No Airtable API token provided. Set AIRTABLE_PERSONAL_ACCESS_TOKEN."}}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    url = f"https://api.airtable.com/v0/{endpoint}"

    try:
        response = requests.request(method, url, headers=headers, json=data, params=params)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        # Handle potential empty response body for certain successful calls (e.g., DELETE)
        if response.status_code == 204 or not response.content:
            return {"success": True}
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API call error to {method} {url}: {e}")
        # Attempt to get more specific error from response body if available
        error_detail = str(e)
        if e.response is not None:
            try:
                error_json = e.response.json()
                error_detail = error_json.get("error", {}).get("message", error_detail)
            except json.JSONDecodeError:
                pass # Use the original exception string
        return {"error": {"message": f"API Request Failed: {error_detail}"}}
    except Exception as e:
        logger.error(f"Unexpected error during API call: {e}\n{traceback.format_exc()}")
        return {"error": {"message": f"An unexpected error occurred: {e}"}}

# --- Tool Definitions ---
# Using @mcp.tool() decorator from the standard SDK

@mcp.tool()
def list_bases() -> str:
    """List all accessible Airtable bases."""
    if not token:
        return "Error: No Airtable API token provided. Set AIRTABLE_PERSONAL_ACCESS_TOKEN environment variable."

    result = api_call("meta/bases")

    if "error" in result:
        return f"Error fetching bases: {result['error'].get('message', 'Unknown API error')}"

    bases = result.get("bases", [])
    if not bases:
        return "No bases found accessible with your token."

    base_list = [f"- {base.get('name', 'Unnamed Base')} (ID: {base.get('id', 'No ID')})" for base in bases]
    return "Available bases:\n" + "\n".join(base_list)

@mcp.tool()
def list_tables(base_id_param: Optional[str] = None) -> str:
    """List all tables in the specified base or the default base."""
    global base_id # Allow modifying the global base_id if set via tool
    current_base = base_id_param or base_id

    if not token:
        return "Error: No Airtable API token provided. Set AIRTABLE_PERSONAL_ACCESS_TOKEN."
    if not current_base:
        return "Error: No base ID provided. Use 'set_base_id' tool first or provide 'base_id_param'."

    result = api_call(f"meta/bases/{current_base}/tables")

    if "error" in result:
        return f"Error fetching tables: {result['error'].get('message', 'Unknown API error')}"

    tables = result.get("tables", [])
    if not tables:
        return f"No tables found in base {current_base}."

    table_list = [
        f"- {table.get('name', 'Unnamed Table')} (ID: {table.get('id', 'No ID')}, "
        f"Fields: {len(table.get('fields', []))})"
        for table in tables
    ]
    return f"Tables in base {current_base}:\n" + "\n".join(table_list)

@mcp.tool()
def list_records(table_name_or_id: str, base_id_param: Optional[str] = None, max_records: int = 10, view: Optional[str] = None, filter_formula: Optional[str] = None, fields: Optional[List[str]] = None) -> str:
    """
    List records from a table. Specify table by name or ID.
    Can filter by view, formula, or select specific fields. Max 100 records.
    Args:
        table_name_or_id: The name or ID of the table.
        base_id_param: Optional Base ID to use, overrides default.
        max_records: Maximum records to return (default 10, max 100).
        view: Name or ID of a view to use for filtering/sorting.
        filter_formula: Airtable formula to filter records.
        fields: List of field names to return. If None, returns all.
    Returns:
        A string listing the records or an error message.
    """
    global base_id
    current_base = base_id_param or base_id

    if not token: return "Error: No Airtable API token."
    if not current_base: return "Error: No base ID set. Use 'set_base_id' or provide 'base_id_param'."
    if not table_name_or_id: return "Error: Please provide a table name or ID."

    # Clamp max_records between 1 and 100
    max_records = max(1, min(max_records, 100))

    params = {"maxRecords": max_records}
    if view: params["view"] = view
    if filter_formula: params["filterByFormula"] = filter_formula
    if fields: params["fields[]"] = fields # Pass list of fields

    endpoint = f"{current_base}/{table_name_or_id}"
    result = api_call(endpoint, params=params)

    if "error" in result:
        return f"Error listing records: {result['error'].get('message', 'Unknown API error')}"

    records = result.get("records", [])
    if not records:
        return f"No records found in table '{table_name_or_id}' matching the criteria."

    formatted_records = []
    for i, record in enumerate(records):
        record_id = record.get("id", "unknown_id")
        fields_dict = record.get("fields", {})
        # Limit display length of field values
        field_strs = []
        for k, v in fields_dict.items():
            v_str = str(v)
            if len(v_str) > 50: v_str = v_str[:47] + "..."
            field_strs.append(f"{k}: {v_str}")
        field_text = ", ".join(field_strs)
        formatted_records.append(f"{i+1}. (ID: {record_id}) {field_text}")

    offset = result.get('offset')
    footer = f"\n(Showing {len(records)} records"
    if offset:
        footer += f", more available with offset='{offset}'" # Note: Need tool to handle pagination
    footer += ")"

    return f"Records from '{table_name_or_id}':\n" + "\n".join(formatted_records) + footer

@mcp.tool()
def get_record(table_name_or_id: str, record_id: str, base_id_param: Optional[str] = None) -> str:
    """Get a specific record from a table by its ID."""
    global base_id
    current_base = base_id_param or base_id

    if not token: return "Error: No Airtable API token."
    if not current_base: return "Error: No base ID set. Use 'set_base_id' or provide 'base_id_param'."
    if not table_name_or_id: return "Error: Please provide a table name or ID."
    if not record_id: return "Error: Please provide a record ID."

    endpoint = f"{current_base}/{table_name_or_id}/{record_id}"
    result = api_call(endpoint)

    if "error" in result:
        return f"Error getting record {record_id}: {result['error'].get('message', 'Unknown API error')}"

    fields_dict = result.get("fields", {})
    record_id_resp = result.get("id", record_id) # Use returned ID if available
    created_time = result.get("createdTime", "")

    if not fields_dict:
        return f"Record {record_id_resp} found but contains no fields."

    formatted_fields = [f"- {key}: {value}" for key, value in fields_dict.items()]
    return f"Record ID: {record_id_resp}\nCreated: {created_time}\nFields:\n" + "\n".join(formatted_fields)

@mcp.tool()
def create_records(table_name_or_id: str, records_json: str, base_id_param: Optional[str] = None, typecast: bool = False) -> str:
    """
    Create one or more records in a table. Input is a JSON string.
    Args:
        table_name_or_id: The name or ID of the table.
        records_json: JSON string representing a single record object (fields only) or a list of record objects.
                      Example for single: '{"Name": "New Task", "Status": "Todo"}'
                      Example for multiple: '[{"fields": {"Name": "Task 1"}}, {"fields": {"Name": "Task 2"}}]'
        base_id_param: Optional Base ID to use, overrides default.
        typecast: Attempt automatic data type conversion (e.g., string to number). Defaults to False.
    Returns:
        A string confirming creation or an error message.
    """
    global base_id
    current_base = base_id_param or base_id

    if not token: return "Error: No Airtable API token."
    if not current_base: return "Error: No base ID set. Use 'set_base_id' or provide 'base_id_param'."
    if not table_name_or_id: return "Error: Please provide a table name or ID."

    try:
        records_data = json.loads(records_json)

        # Standardize input format to list of {"fields": {...}}
        if isinstance(records_data, dict): # Single record provided directly
            records_list = [{"fields": records_data}]
        elif isinstance(records_data, list):
            # Check if list items already have the 'fields' structure
            if all(isinstance(item, dict) and 'fields' in item for item in records_data):
                 records_list = records_data
            else: # Assume list of field objects
                 records_list = [{"fields": record} for record in records_data if isinstance(record, dict)]
        else:
            return "Error: Invalid JSON format. Expected a JSON object or a list of objects."

        if not records_list:
             return "Error: No valid records found in JSON data."

        data = {"records": records_list, "typecast": typecast}
        endpoint = f"{current_base}/{table_name_or_id}"
        result = api_call(endpoint, method="POST", data=data)

        if "error" in result:
            # Provide more specific error if available (e.g., validation error)
            error_msg = result['error'].get('message', 'Unknown API error')
            error_type = result['error'].get('type')
            if error_type: error_msg = f"({error_type}) {error_msg}"
            return f"Error creating records: {error_msg}"

        created_records = result.get("records", [])
        created_ids = [r.get('id', 'unknown') for r in created_records]
        return f"Successfully created {len(created_records)} record(s). IDs: {', '.join(created_ids)}"

    except json.JSONDecodeError:
        return "Error: Invalid JSON format provided in 'records_json'."
    except Exception as e:
        logger.error(f"Unexpected error creating records: {e}\n{traceback.format_exc()}")
        return f"Error: An unexpected error occurred: {str(e)}"

@mcp.tool()
def update_records(table_name_or_id: str, records_json: str, base_id_param: Optional[str] = None, typecast: bool = False) -> str:
    """
    Update one or more records. Input JSON requires record 'id' and 'fields'.
    Args:
        table_name_or_id: The name or ID of the table.
        records_json: JSON string representing a list of objects, each with 'id' and 'fields'.
                      Example: '[{"id": "recXXXX", "fields": {"Status": "Done"}}]'
        base_id_param: Optional Base ID to use, overrides default.
        typecast: Attempt automatic data type conversion. Defaults to False.
    Returns:
        A string confirming update or an error message.
    """
    global base_id
    current_base = base_id_param or base_id

    if not token: return "Error: No Airtable API token."
    if not current_base: return "Error: No base ID set. Use 'set_base_id' or provide 'base_id_param'."
    if not table_name_or_id: return "Error: Please provide a table name or ID."

    try:
        records_data = json.loads(records_json)

        if not isinstance(records_data, list):
            return "Error: Invalid JSON format. Expected a list of record objects."

        # Validate format: list of {"id": "...", "fields": {...}}
        valid_records = []
        for item in records_data:
            if isinstance(item, dict) and "id" in item and "fields" in item and isinstance(item["fields"], dict):
                valid_records.append(item)
            else:
                return "Error: Each item in the JSON list must be an object with 'id' and 'fields' keys."

        if not valid_records:
            return "Error: No valid records found in JSON data for update."

        data = {"records": valid_records, "typecast": typecast}
        endpoint = f"{current_base}/{table_name_or_id}"
        # Airtable uses PATCH for updates
        result = api_call(endpoint, method="PATCH", data=data)

        if "error" in result:
            error_msg = result['error'].get('message', 'Unknown API error')
            error_type = result['error'].get('type')
            if error_type: error_msg = f"({error_type}) {error_msg}"
            return f"Error updating records: {error_msg}"

        updated_records = result.get("records", [])
        return f"Successfully updated {len(updated_records)} record(s)."

    except json.JSONDecodeError:
        return "Error: Invalid JSON format provided in 'records_json'."
    except Exception as e:
        logger.error(f"Unexpected error updating records: {e}\n{traceback.format_exc()}")
        return f"Error: An unexpected error occurred: {str(e)}"

@mcp.tool()
def delete_records(table_name_or_id: str, record_ids: List[str], base_id_param: Optional[str] = None) -> str:
    """
    Delete one or more records by their IDs. Max 10 IDs per call.
    Args:
        table_name_or_id: The name or ID of the table.
        record_ids: A list of record IDs (strings) to delete.
        base_id_param: Optional Base ID to use, overrides default.
    Returns:
        A string confirming deletion or an error message.
    """
    global base_id
    current_base = base_id_param or base_id

    if not token: return "Error: No Airtable API token."
    if not current_base: return "Error: No base ID set. Use 'set_base_id' or provide 'base_id_param'."
    if not table_name_or_id: return "Error: Please provide a table name or ID."
    if not record_ids: return "Error: Please provide a list of record IDs to delete."
    if not isinstance(record_ids, list): return "Error: 'record_ids' must be a list of strings."
    if len(record_ids) > 10: return "Error: Cannot delete more than 10 records per call."

    # Parameter format for DELETE is records[]=recId1&records[]=recId2
    params = [("records[]", rec_id) for rec_id in record_ids]

    endpoint = f"{current_base}/{table_name_or_id}"
    result = api_call(endpoint, method="DELETE", params=params)

    if "error" in result:
        return f"Error deleting records: {result['error'].get('message', 'Unknown API error')}"

    # Successful delete often returns {"records": [{"id": "...", "deleted": true}, ...]}
    deleted_info = result.get("records", [])
    deleted_count = sum(1 for item in deleted_info if item.get("deleted"))

    return f"Successfully deleted {deleted_count} record(s)."


@mcp.tool()
def set_base_id(new_base_id: str) -> str:
    """Set the active Airtable Base ID for subsequent tool calls."""
    global base_id
    if not new_base_id or not isinstance(new_base_id, str):
        return "Error: Please provide a valid Base ID string."
    base_id = new_base_id
    logger.info(f"Active Airtable Base ID set to: {base_id}")
    return f"Active Base ID set to: {base_id}"

# --- Server Entry Point ---

if __name__ == "__main__":
    logger.info("Starting local Airtable MCP server...")
    logger.info("Make sure AIRTABLE_PERSONAL_ACCESS_TOKEN is set.")
    logger.info("Use 'set_base_id' tool or set AIRTABLE_BASE_ID environment variable.")
    # This runs the server, making tools available to connected clients (like Claude Desktop)
    mcp.run() 