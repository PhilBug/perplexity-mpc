# Perplexity Ask MCP Server

An MCP server implementation that integrates the Sonar API to provide Claude with unparalleled real-time, web-wide research.

![Demo](perplexity-ask/assets/demo_screenshot.png)

## Tools

- **perplexity_ask**
  - Engage in a conversation with the Sonar API for live web searches.
  - **Inputs:**
    - `messages` (array): An array of conversation messages.
      - Each message must include:
        - `role` (string): The role of the message (e.g., `system`, `user`, `assistant`).
        - `content` (string): The content of the message.

- **perplexity_reason**
  - Perform reasoning tasks using the Perplexity API with the sonar-reasoning-pro model.
  - **Inputs:**
    - `messages` (array): An array of conversation messages.
      - Each message must include:
        - `role` (string): The role of the message (e.g., `system`, `user`, `assistant`).
        - `content` (string): The content of the message.

## Configuration

### Step 1

Clone the MCP repository:

```bash
git@github.com:modelcontextprotocol/servers.git
```

Navigate to the `perplexity-ask` directory and install the necessary dependencies:

```bash
cd servers/src/perplexity-ask && npm install
```

### Step 2: Get a Sonar API Key

1. Sign up for a [Sonar API account](https://docs.perplexity.ai/guides/getting-started).
2. Follow the account setup instructions and generate your API key from the developer dashboard.
3. Set the API key in your environment as `PERPLEXITY_API_KEY`.

### Step 3: Configure Claude Desktop

1. Download Claude desktop [here](https://claude.ai/download).

2. Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "perplexity-ask": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "PERPLEXITY_API_KEY",
        "-e",
        "PERPLEXITY_MODEL",
        "-e",
        "PERPLEXITY_REASONING_MODEL",
        "mcp/perplexity-ask"
      ],
      "env": {
        "PERPLEXITY_API_KEY": "YOUR_API_KEY_HERE",
        "PERPLEXITY_MODEL": "sonar-pro",
        "PERPLEXITY_REASONING_MODEL": "sonar-reasoning-pro"
      }
    }
  }
}
```

You can specify which Perplexity model to use by setting the `PERPLEXITY_MODEL` environment variable. If not specified, it defaults to "sonar-pro".
You can also specify which Perplexity reasoning model to use by setting the `PERPLEXITY_REASONING_MODEL` environment variable. If not specified, it defaults to "sonar-reasoning-pro".

### NPX

```json
{
  "mcpServers": {
    "perplexity-ask": {
      "command": "npx",
      "args": [
        "npx ~/your-repo-path/perplexity/perplexity-ask"
      ],
      "env": {
        "PERPLEXITY_API_KEY": "YOUR_API_KEY_HERE",
        "PERPLEXITY_MODEL": "sonar-pro",
        "PERPLEXITY_REASONING_MODEL": "sonar-reasoning-pro"
      }
    }
  }
}
```

You can access the file using:

```bash
vim ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Step 4: Build the Docker Image

Docker build:

```bash
docker build -t mcp/perplexity-ask:latest -f src/perplexity-ask/Dockerfile .
```

### Step 5: Testing

Let's make sure Claude for Desktop is picking up the two tools we've exposed in our `perplexity-ask` server. You can do this by looking for the hammer icon:

![Claude Visual Tools](perplexity-ask/assets/visual-indicator-mcp-tools.png)

After clicking on the hammer icon, you should see the tools that come with the Filesystem MCP Server:

![Available Integration](perplexity-ask/assets/available_tools.png)

If you see both of these this means that the integration is active. Congratulations! This means Claude can now ask Perplexity. You can then simply use it as you would use the Perplexity web app.  

### Step 6: Advanced parameters

Currently, the search parameters used are the default ones. You can modify any search parameter in the API call directly in the `index.ts` script. For this, please refer to the official [API documentation](https://docs.perplexity.ai/api-reference/chat-completions).

### Troubleshooting

The Claude documentation provides an excellent [troubleshooting guide](https://modelcontextprotocol.io/docs/tools/debugging) you can refer to. However, you can still reach out to us at <api@perplexity.ai> for any additional support or [file a bug](https://github.com/ppl-ai/api-discussion/issues).

## Logging and Debugging

The perplexity-ask tool includes comprehensive logging and error handling to improve reliability and debuggability:

- Log files are stored in `mcp-server.log` at the repository root
- Logs include detailed information about:
  - API requests and responses
  - Tool call processing
  - Errors (network errors, JSON parsing errors, API errors)
  - General operation information
- Log rotation is implemented to prevent excessive disk usage (maximum size: 20MB)
- When the log file reaches the size limit, it's automatically truncated to preserve the most recent logs

These logging capabilities make it easier to identify and resolve issues when using the perplexity-ask tool. When reporting problems, including relevant log entries can help with faster resolution.

## License

This MCP server is licensed under the MIT License. This means you are free to use, modify, and distribute the software, subject to the terms and conditions of the MIT License. For more details, please see the LICENSE file in the project repository.
