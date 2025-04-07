import asyncio
import aiohttp
import sys
import logging
import os
import re

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from perplexity_mcp import __version__

server = Server("perplexity-mcp")


@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """
    List available prompts.
    Each prompt can have optional arguments to customize its behavior.
    """
    search_prompt = types.Prompt(
        name="perplexity_search",
        description="Search the web using Perplexity AI and filter results by recency",
        arguments=[
            types.PromptArgument(
                name="query",
                description="The search query to find information about",
                required=True,
            ),
            types.PromptArgument(
                name="recency",
                description="Filter results by how recent they are. Options: 'day' (last 24h), 'week' (last 7 days), 'month' (last 30 days), 'year' (last 365 days). Defaults to 'month'.",
                required=False,
            ),
        ],
    )
    reason_prompt = types.Prompt(
        name="perplexity_reason",
        description="Reason about a topic using Perplexity AI and filter context by recency",
        arguments=[
            types.PromptArgument(
                name="query",
                description="The topic or question to reason about",
                required=True,
            ),
            types.PromptArgument(
                name="recency",
                description="Filter context by how recent it is. Options: 'day' (last 24h), 'week' (last 7 days), 'month' (last 30 days), 'year' (last 365 days). Defaults to 'month'.",
                required=False,
            ),
        ],
    )
    return [search_prompt, reason_prompt]


@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """
    Generate a prompt by combining arguments with server state.
    """
    if name not in ["perplexity_search", "perplexity_reason"]:
        raise ValueError(f"Unknown prompt: {name}")

    query = (arguments or {}).get("query", "")
    recency = (arguments or {}).get("recency", "month")

    if name == "perplexity_search":
        return types.GetPromptResult(
            description=f"Search the web for information about: {query}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=f"Find recent information about: {query}",
                    ),
                ),
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=f"Only include results from the last {recency}",
                    ),
                ),
            ],
        )
    elif name == "perplexity_reason":
        return types.GetPromptResult(
            description=f"Reason about the topic: {query}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=f"Reason about the following topic: {query}",
                    ),
                ),
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=f"Use context primarily from the last {recency}",
                    ),
                ),
            ],
        )
    raise ValueError(f"Unhandled prompt name: {name}")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    search_tool = types.Tool(
        name="perplexity_search",
        description="Search the web by asking Perplexity AI with recency filtering",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "recency": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "default": "month",
                },
            },
            "required": ["query"],
        },
    )
    reason_tool = types.Tool(
        name="perplexity_reason",
        description="Reason about a topic using Perplexity AI reasoning model with recency filtering for context",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "recency": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "default": "month",
                },
            },
            "required": ["query"],
        },
    )
    return [search_tool, reason_tool]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "perplexity_search":
        query = arguments["query"]
        recency = arguments.get("recency", "month")
        result = await call_perplexity_search(query, recency)
        return [types.TextContent(type="text", text=str(result))]
    elif name == "perplexity_reason":
        query = arguments["query"]
        recency = arguments.get("recency", "month")
        raw_result = await call_perplexity_reason(query, recency)
        # Remove <think>...</think> tags
        cleaned_result = re.sub(
            r"<think>.*?</think>", "", str(raw_result), flags=re.DOTALL
        ).strip()
        return [types.TextContent(type="text", text=cleaned_result)]
    raise ValueError(f"Tool not found: {name}")


async def _call_perplexity_base(query: str, recency: str, model: str) -> str:
    """Base function to call Perplexity API."""
    url = "https://api.perplexity.ai/chat/completions"

    # Set max_tokens based on model type (higher for reasoning)
    max_tokens = "4000" if "reasoning" in model else "2000"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Be precise and concise."},
            {"role": "user", "content": query},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "top_p": 0.95,
        "return_images": False,
        "return_related_questions": False,
        "search_recency_filter": recency,
        "top_k": 0,
        "stream": False,
        "presence_penalty": 0,
        "frequency_penalty": 1,
        "return_citations": True,
        "search_context_size": "low",
    }

    headers = {
        "Authorization": f"Bearer {os.getenv('PERPLEXITY_API_KEY')}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            response.raise_for_status()
            data = await response.json()
            content = data["choices"][0]["message"]["content"]

            # Format response with citations if available
            citations = data.get("citations", [])
            if citations:
                formatted_citations = "\n\nCitations:\n" + "\n".join(
                    f"[{i + 1}] {url}" for i, url in enumerate(citations)
                )
                return content + formatted_citations

            return content


async def call_perplexity_search(query: str, recency: str) -> str:
    """Calls Perplexity API using the search model."""
    model = os.getenv("PERPLEXITY_MODEL", "sonar")
    return await _call_perplexity_base(query, recency, model)


async def call_perplexity_reason(query: str, recency: str) -> str:
    """Calls Perplexity API using the reasoning model."""
    model = os.getenv("PERPLEXITY_REASONING_MODEL", "sonar-reasoning")
    return await _call_perplexity_base(query, recency, model)


async def main_async():
    API_KEY = os.getenv("PERPLEXITY_API_KEY")
    if not API_KEY:
        raise ValueError("PERPLEXITY_API_KEY environment variable is required")

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="perplexity-mcp",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main():
    """CLI entry point for perplexity-mcp"""
    logging.basicConfig(level=logging.INFO)

    API_KEY = os.getenv("PERPLEXITY_API_KEY")
    if not API_KEY:
        print(
            "Error: PERPLEXITY_API_KEY environment variable is required",
            file=sys.stderr,
        )
        sys.exit(1)

    # Log which models are being used (helpful for debug)
    search_model = os.getenv("PERPLEXITY_MODEL", "sonar")
    reasoning_model = os.getenv("PERPLEXITY_REASONING_MODEL", "sonar-reasoning")
    logging.info(
        f"Using Perplexity AI search model: {search_model} (set with PERPLEXITY_MODEL)"
    )
    logging.info(
        f"Using Perplexity AI reasoning model: {reasoning_model} (set with PERPLEXITY_REASONING_MODEL)"
    )

    # List available models (Consider adding more if API supports them)
    available_models = {
        # "sonar-deep-research": "128k context - Enhanced research capabilities",
        "sonar-reasoning-pro": "128k context - Advanced reasoning with professional focus",
        "sonar-reasoning": "128k context - Enhanced reasoning capabilities",
        "sonar-pro": "200k context - Professional grade model",
        "sonar": "128k context - General purpose model",
        # "r1-1776": "128k context - Alternative architecture",
    }

    logging.info(
        "Available Perplexity models (set with PERPLEXITY_MODEL or PERPLEXITY_REASONING_MODEL environment variables):"
    )
    for model_name, description in available_models.items():
        marker_search = "S→" if model_name == search_model else "  "
        marker_reason = "R→" if model_name == reasoning_model else "  "
        # Combine markers if a model is used for both
        marker = marker_search.strip() + marker_reason.strip()
        if marker:
            marker = f"{marker}→ "
        else:
            marker = "   "

        logging.info(f" {marker}{model_name}: {description}")

    asyncio.run(main_async())


if __name__ == "__main__":
    main()
