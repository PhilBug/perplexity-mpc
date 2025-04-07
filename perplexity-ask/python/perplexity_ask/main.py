#!/usr/bin/env python3

import os
import sys
import asyncio
import datetime
import traceback
from pathlib import Path
from typing import List, Dict, Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool
from mcp.server.models import InitializationOptions


def find_repo_root() -> Path:
    """Find the repository root by looking for .git directory or pyproject.toml file."""
    current_file = Path(__file__).resolve()
    current_dir = current_file.parent

    # Navigate up until we find .git or pyproject.toml
    while current_dir != current_dir.parent:
        if (current_dir / ".git").exists() or (current_dir / "pyproject.toml").exists():
            return current_dir
        current_dir = current_dir.parent

    # If we can't find the repo root, fall back to the directory containing this file
    return current_file.parent


# Configure logging
REPO_ROOT = find_repo_root()
LOG_FILE_PATH = REPO_ROOT / "mcp-server.log"
MAX_LOG_SIZE_BYTES = 20 * 1024 * 1024  # 20MB

print(f"Using repository root: {REPO_ROOT}", file=sys.stderr)
print(f"Log file will be created at: {LOG_FILE_PATH}", file=sys.stderr)


class FileRotatingLogger:
    """Custom logger that writes to a file with size limitation."""

    @staticmethod
    async def log_to_file(message: str) -> None:
        timestamp = datetime.datetime.now().isoformat()
        log_entry = f"[{timestamp}] {message}\n"

        try:
            # Check if the log file exists and get its size
            file_size = 0
            if LOG_FILE_PATH.exists():
                file_size = LOG_FILE_PATH.stat().st_size

            # If file exceeds max size, truncate it to half its size to keep newer logs
            if file_size >= MAX_LOG_SIZE_BYTES:
                try:
                    # Read the file content
                    content = LOG_FILE_PATH.read_text(encoding="utf-8")
                    # Split by lines and keep only the second half
                    lines = content.split("\n")
                    halfway_point = len(lines) // 2
                    new_content = "\n".join(lines[halfway_point:])
                    # Write back the second half
                    LOG_FILE_PATH.write_text(new_content, encoding="utf-8")
                except Exception:
                    # If something goes wrong with truncation, just overwrite the file
                    LOG_FILE_PATH.write_text(log_entry, encoding="utf-8")
                    return

            # Append the new log entry
            with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            # If file operations fail, fall back to stderr
            print(f"Logging error: {e}", file=sys.stderr)
            print(message, file=sys.stderr)

    @classmethod
    async def info(cls, message: str) -> None:
        await cls.log_to_file(f"INFO: {message}")

    @classmethod
    async def error(cls, message: str, error: Optional[Exception] = None) -> None:
        if error:
            error_message = f"{message}: {error}"
        else:
            error_message = message
        await cls.log_to_file(f"ERROR: {error_message}")

    @classmethod
    async def warn(cls, message: str) -> None:
        await cls.log_to_file(f"WARN: {message}")


# Tool definitions
PERPLEXITY_ASK_TOOL = Tool(
    name="perplexity_ask",
    description=(
        "Engages in a conversation using the Sonar API. "
        "Accepts an array of messages (each with a role and content) "
        "and returns a ask completion response from the Perplexity model."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {
                            "type": "string",
                            "description": "Role of the message (e.g., system, user, assistant)",
                        },
                        "content": {
                            "type": "string",
                            "description": "The content of the message",
                        },
                    },
                    "required": ["role", "content"],
                },
                "description": "Array of conversation messages",
            },
        },
        "required": ["messages"],
    },
)

PERPLEXITY_REASON_TOOL = Tool(
    name="perplexity_reason",
    description=(
        "Performs reasoning tasks using the Perplexity API. "
        "Accepts an array of messages (each with a role and content) "
        "and returns a well-reasoned response using the sonar-reasoning-pro model."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {
                            "type": "string",
                            "description": "Role of the message (e.g., system, user, assistant)",
                        },
                        "content": {
                            "type": "string",
                            "description": "The content of the message",
                        },
                    },
                    "required": ["role", "content"],
                },
                "description": "Array of conversation messages",
            },
        },
        "required": ["messages"],
    },
)


async def perform_chat_completion(
    messages: List[Dict[str, str]], model: Optional[str] = None
) -> str:
    """
    Performs a chat completion by sending a request to the Perplexity API.
    Appends citations to the returned message content if they exist.

    Args:
        messages: An array of message objects with role and content.
        model: Optional model to use for the completion. Defaults to the value from environment variable.

    Returns:
        The chat completion result with appended citations.

    Raises:
        Exception: If the API request fails.
    """
    # Use default model if not specified
    if model is None:
        model = os.environ.get("PERPLEXITY_MODEL", "sonar-pro")

    # Construct request body
    body = {
        "model": model,
        "messages": messages,
        # Additional parameters can be added here if required
    }

    # Send request to Perplexity API
    url = "https://api.perplexity.ai/chat/completions"

    await FileRotatingLogger.info(
        f"Sending request to Perplexity API with {len(messages)} messages using model {model}"
    )

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
                },
                timeout=30.0,
            )
        except Exception as e:
            await FileRotatingLogger.error(
                "Network error while calling Perplexity API", e
            )
            raise Exception(f"Network error while calling Perplexity API: {e}")

        # Check for non-successful HTTP status
        if response.status_code != 200:
            try:
                error_text = response.text
            except Exception:
                error_text = "Unable to parse error response"

            await FileRotatingLogger.error(
                f"Perplexity API error: {response.status_code} {response.reason_phrase}\n{error_text}"
            )
            raise Exception(
                f"Perplexity API error: {response.status_code} {response.reason_phrase}\n{error_text}"
            )

        # Parse the JSON response
        try:
            data = response.json()
            await FileRotatingLogger.info(
                "Successfully received and parsed response from Perplexity API"
            )
        except Exception as e:
            await FileRotatingLogger.error(
                "Failed to parse JSON response from Perplexity API", e
            )
            raise Exception(f"Failed to parse JSON response from Perplexity API: {e}")

        # Extract the message content
        message_content = data["choices"][0]["message"]["content"]

        # Add citations if present
        if (
            "citations" in data
            and isinstance(data["citations"], list)
            and data["citations"]
        ):
            await FileRotatingLogger.info(
                f"Adding {len(data['citations'])} citations to response"
            )
            message_content += "\n\nCitations:\n"
            for i, citation in enumerate(data["citations"]):
                message_content += f"[{i + 1}] {citation}\n"

        return message_content


async def setup_server():
    """Initialize the server and configure tool handlers."""
    # Check for required environment variables
    if "PERPLEXITY_API_KEY" not in os.environ:
        await FileRotatingLogger.error(
            "PERPLEXITY_API_KEY environment variable is required"
        )
        sys.exit(1)

    # Log model information
    perplexity_model = os.environ.get("PERPLEXITY_MODEL", "sonar-pro")
    perplexity_reasoning_model = os.environ.get(
        "PERPLEXITY_REASONING_MODEL", "sonar-reasoning-pro"
    )
    await FileRotatingLogger.info(f"Using Perplexity model: {perplexity_model}")
    await FileRotatingLogger.info(
        f"Using Perplexity reasoning model: {perplexity_reasoning_model}"
    )

    # Create a new server instance without lifespan
    server = Server("perplexity-ask-python")

    # Register handlers for tools
    @server.list_tools()
    async def handle_list_tools():
        """Handle tool listing requests."""
        return [PERPLEXITY_ASK_TOOL, PERPLEXITY_REASON_TOOL]

    @server.call_tool()
    async def handle_call_tool(name, arguments):
        """Handle tool call requests."""
        try:
            if not arguments:
                await FileRotatingLogger.error("No arguments provided for tool call")
                raise ValueError("No arguments provided")

            if name == "perplexity_ask":
                if not isinstance(arguments.get("messages"), list):
                    await FileRotatingLogger.error(
                        "Invalid arguments for perplexity_ask: 'messages' must be an array"
                    )
                    raise ValueError(
                        "Invalid arguments for perplexity_ask: 'messages' must be an array"
                    )

                await FileRotatingLogger.info(
                    f"Processing perplexity_ask tool call with {len(arguments['messages'])} messages"
                )
                messages = arguments["messages"]
                result = await perform_chat_completion(messages)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": result
                        }
                    ]
                }

            elif name == "perplexity_reason":
                if not isinstance(arguments.get("messages"), list):
                    await FileRotatingLogger.error(
                        "Invalid arguments for perplexity_reason: 'messages' must be an array"
                    )
                    raise ValueError(
                        "Invalid arguments for perplexity_reason: 'messages' must be an array"
                    )

                await FileRotatingLogger.info(
                    f"Processing perplexity_reason tool call with {len(arguments['messages'])} messages"
                )
                messages = arguments["messages"]
                reasoning_model = os.environ.get(
                    "PERPLEXITY_REASONING_MODEL", "sonar-reasoning-pro"
                )
                result = await perform_chat_completion(messages, reasoning_model)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": result
                        }
                    ]
                }

            else:
                await FileRotatingLogger.error(f"Unknown tool requested: {name}")
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Unknown tool: {name}"
                        }
                    ]
                }

        except Exception as e:
            await FileRotatingLogger.error("Error processing tool call", e)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: {str(e)}"
                    }
                ]
            }

    return server


async def run_server():
    """Start the server and handle any startup errors."""
    try:
        await FileRotatingLogger.info("Starting Perplexity Ask MCP Server")
        server = await setup_server()

        try:
            # Use the stdio_server context manager which provides the transport streams
            async with stdio_server() as (read_stream, write_stream):
                # Create initialization options
                init_options = InitializationOptions(
                    server_name="perplexity-ask-python",
                    server_version="0.1.0",
                    capabilities={"tools": {"listChanged": True}},
                )

                # Run the server with the provided streams and options
                await server.run(read_stream, write_stream, init_options)
        except Exception as e:
            tb = traceback.format_exc()
            await FileRotatingLogger.error(f"Server execution error: {e}\n{tb}")
            raise

        await FileRotatingLogger.info("Perplexity Ask MCP Server running on stdio")

    except Exception as e:
        tb = traceback.format_exc()
        await FileRotatingLogger.error(f"Fatal error running server: {e}\n{tb}")
        sys.exit(1)


def main():
    """Entry point for the server."""
    try:
        asyncio.run(run_server())
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
