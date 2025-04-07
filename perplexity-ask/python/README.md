# Perplexity Ask MCP Server

A Python implementation of a Model Context Protocol (MCP) server that integrates with the Perplexity API.

## Features

- Provides two MCP tools:
  - `perplexity_ask`: General-purpose chat completion using the Perplexity Sonar API
  - `perplexity_reason`: Advanced reasoning using the Perplexity reasoning model

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/perplexity-ask.git
cd perplexity-ask/python

# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

## Usage

### Environment Variables

The server requires the following environment variables:

- `PERPLEXITY_API_KEY`: Your Perplexity API key (required)
- `PERPLEXITY_MODEL`: Model to use for standard completions (default: "sonar-pro")
- `PERPLEXITY_REASONING_MODEL`: Model to use for reasoning tasks (default: "sonar-reasoning-pro")

### Running the Server

```bash
# Run directly
python -m perplexity_ask.main

# Or via the entry point
perplexity-ask
```

### Install in MCP Client

```bash
# Install in an MCP-compatible client like Claude Desktop
mcp install perplexity-ask/python/perplexity_ask/main.py

# With environment variables
mcp install perplexity-ask/python/perplexity_ask/main.py -v PERPLEXITY_API_KEY=your_api_key
```

## Development

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Format code
black .
isort .

# Type checking
mypy perplexity_ask
```

## License

MIT
