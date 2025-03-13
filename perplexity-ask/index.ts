#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool,
} from "@modelcontextprotocol/sdk/types.js";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { fileURLToPath } from "url";

/**
 * Find the repository root by looking for package.json or .git directory
 * @returns {string} The path to the repository root
 */
function findRepoRoot(): string {
  // For ES modules, we use import.meta.url to get the current file path
  const currentFilePath = fileURLToPath(import.meta.url);
  let currentDir = path.dirname(currentFilePath);
  
  // Navigate up until we find package.json or .git
  while (currentDir !== path.parse(currentDir).root) {
    // Check if this directory has markers of a repo root
    if (
      fs.existsSync(path.join(currentDir, 'package.json')) ||
      fs.existsSync(path.join(currentDir, '.git'))
    ) {
      return currentDir;
    }
    
    // Go up one directory
    currentDir = path.dirname(currentDir);
  }
  
  // If we can't find the repo root, fall back to the directory containing this file
  return path.dirname(currentFilePath);
}

// Configure logging
const REPO_ROOT = findRepoRoot();
const LOG_FILE_PATH = path.join(REPO_ROOT, "mcp-server.log");
const MAX_LOG_SIZE_BYTES = 20 * 1024 * 1024; // 20MB

// Log the paths to help with debugging
console.error(`Using repository root: ${REPO_ROOT}`);
console.error(`Log file will be created at: ${LOG_FILE_PATH}`);

/**
 * Custom logger function that writes to a file with size limitation
 * @param {string} message - The message to log
 */
async function logToFile(message: string): Promise<void> {
  const timestamp = new Date().toISOString();
  const logEntry = `[${timestamp}] ${message}\n`;

  try {
    // Check if the log file exists and get its size
    let fileSize = 0;
    try {
      const stats = await fs.promises.stat(LOG_FILE_PATH);
      fileSize = stats.size;
    } catch (error) {
      // File doesn't exist yet, which is fine
    }

    // If file exceeds max size, truncate it to half its size to keep newer logs
    if (fileSize >= MAX_LOG_SIZE_BYTES) {
      try {
        // Read the file content
        const data = await fs.promises.readFile(LOG_FILE_PATH, "utf8");
        // Split by lines and keep only the second half
        const lines = data.split("\n");
        const halfwayPoint = Math.floor(lines.length / 2);
        const newContent = lines.slice(halfwayPoint).join("\n");
        // Write back the second half
        await fs.promises.writeFile(LOG_FILE_PATH, newContent, "utf8");
      } catch (error) {
        // If something goes wrong with truncation, just overwrite the file
        await fs.promises.writeFile(LOG_FILE_PATH, logEntry, "utf8");
        return;
      }
    }

    // Append the new log entry
    await fs.promises.appendFile(LOG_FILE_PATH, logEntry, "utf8");
  } catch (error) {
    // If file operations fail, fall back to console.error
    console.error(`Logging error: ${error}`);
    console.error(message);
  }
}

/**
 * Logger function that wraps logToFile and provides convenience methods
 */
const logger = {
  info: (message: string) => logToFile(`INFO: ${message}`),
  error: (message: string, error?: any) => {
    const errorMessage = error
      ? `${message}: ${
          error instanceof Error ? error.stack || error.message : String(error)
        }`
      : message;
    return logToFile(`ERROR: ${errorMessage}`);
  },
  warn: (message: string) => logToFile(`WARN: ${message}`),
};

/**
 * Definition of the Perplexity Ask Tool.
 * This tool accepts an array of messages and returns a chat completion response
 * from the Perplexity API, with citations appended to the message if provided.
 */
const PERPLEXITY_ASK_TOOL: Tool = {
  name: "perplexity_ask",
  description:
    "Engages in a conversation using the Sonar API. " +
    "Accepts an array of messages (each with a role and content) " +
    "and returns a ask completion response from the Perplexity model.",
  inputSchema: {
    type: "object",
    properties: {
      messages: {
        type: "array",
        items: {
          type: "object",
          properties: {
            role: {
              type: "string",
              description:
                "Role of the message (e.g., system, user, assistant)",
            },
            content: {
              type: "string",
              description: "The content of the message",
            },
          },
          required: ["role", "content"],
        },
        description: "Array of conversation messages",
      },
    },
    required: ["messages"],
  },
};

// Retrieve the Perplexity API key from environment variables
const PERPLEXITY_API_KEY = process.env.PERPLEXITY_API_KEY;
if (!PERPLEXITY_API_KEY) {
  logger.error("PERPLEXITY_API_KEY environment variable is required");
  process.exit(1);
}

// Retrieve the model name from environment variables, defaulting to "sonar-pro" if not set
const PERPLEXITY_MODEL = process.env.PERPLEXITY_MODEL || "sonar-pro";
logger.info(`Using Perplexity model: ${PERPLEXITY_MODEL}`);

/**
 * Performs a chat completion by sending a request to the Perplexity API.
 * Appends citations to the returned message content if they exist.
 *
 * @param {Array<{ role: string; content: string }>} messages - An array of message objects.
 * @returns {Promise<string>} The chat completion result with appended citations.
 * @throws Will throw an error if the API request fails.
 */
async function performChatCompletion(
  messages: Array<{ role: string; content: string }>
): Promise<string> {
  // Construct the API endpoint URL and request body
  const url = new URL("https://api.perplexity.ai/chat/completions");
  const body = {
    model: PERPLEXITY_MODEL, // Use the model from environment variable
    messages: messages,
    // Additional parameters can be added here if required (e.g., max_tokens, temperature, etc.)
    // See the Sonar API documentation for more details:
    // https://docs.perplexity.ai/api-reference/chat-completions
  };

  let response;
  try {
    logger.info(
      `Sending request to Perplexity API with ${messages.length} messages`
    );
    response = await fetch(url.toString(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${PERPLEXITY_API_KEY}`,
      },
      body: JSON.stringify(body),
    });
  } catch (error) {
    logger.error("Network error while calling Perplexity API", error);
    throw new Error(`Network error while calling Perplexity API: ${error}`);
  }

  // Check for non-successful HTTP status
  if (!response.ok) {
    let errorText;
    try {
      errorText = await response.text();
    } catch (parseError) {
      errorText = "Unable to parse error response";
    }
    logger.error(
      `Perplexity API error: ${response.status} ${response.statusText}\n${errorText}`
    );
    throw new Error(
      `Perplexity API error: ${response.status} ${response.statusText}\n${errorText}`
    );
  }

  // Attempt to parse the JSON response from the API
  let data;
  try {
    data = await response.json();
    logger.info(
      "Successfully received and parsed response from Perplexity API"
    );
  } catch (jsonError) {
    logger.error(
      "Failed to parse JSON response from Perplexity API",
      jsonError
    );
    throw new Error(
      `Failed to parse JSON response from Perplexity API: ${jsonError}`
    );
  }

  // Directly retrieve the main message content from the response
  let messageContent = data.choices[0].message.content;

  // If citations are provided, append them to the message content
  if (
    data.citations &&
    Array.isArray(data.citations) &&
    data.citations.length > 0
  ) {
    logger.info(`Adding ${data.citations.length} citations to response`);
    messageContent += "\n\nCitations:\n";
    data.citations.forEach((citation: string, index: number) => {
      messageContent += `[${index + 1}] ${citation}\n`;
    });
  }

  return messageContent;
}

// Initialize the server with tool metadata and capabilities
const server = new Server(
  {
    name: "example-servers/perplexity-ask",
    version: "0.1.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

/**
 * Registers a handler for listing available tools.
 * When the client requests a list of tools, this handler returns the Perplexity Ask Tool.
 */
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [PERPLEXITY_ASK_TOOL],
}));

/**
 * Registers a handler for calling a specific tool.
 * Processes requests by validating input and invoking the appropriate tool.
 *
 * @param {object} request - The incoming tool call request.
 * @returns {Promise<object>} The response containing the tool's result or an error.
 */
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  try {
    const { name, arguments: args } = request.params;
    if (!args) {
      logger.error("No arguments provided for tool call");
      throw new Error("No arguments provided");
    }
    switch (name) {
      case "perplexity_ask": {
        if (!Array.isArray(args.messages)) {
          logger.error(
            "Invalid arguments for perplexity-ask: 'messages' must be an array"
          );
          throw new Error(
            "Invalid arguments for perplexity-ask: 'messages' must be an array"
          );
        }
        logger.info(
          `Processing perplexity_ask tool call with ${args.messages.length} messages`
        );
        // Invoke the chat completion function with the provided messages
        const messages = args.messages;
        const result = await performChatCompletion(messages);
        return {
          content: [{ type: "text", text: result }],
          isError: false,
        };
      }
      default:
        // Respond with an error if an unknown tool is requested
        logger.error(`Unknown tool requested: ${name}`);
        return {
          content: [{ type: "text", text: `Unknown tool: ${name}` }],
          isError: true,
        };
    }
  } catch (error) {
    // Return error details in the response
    logger.error("Error processing tool call", error);
    return {
      content: [
        {
          type: "text",
          text: `Error: ${
            error instanceof Error ? error.message : String(error)
          }`,
        },
      ],
      isError: true,
    };
  }
});

/**
 * Initializes and runs the server using standard I/O for communication.
 * Logs an error and exits if the server fails to start.
 */
async function runServer() {
  try {
    logger.info("Starting Perplexity Ask MCP Server");
    const transport = new StdioServerTransport();
    await server.connect(transport);
    logger.info("Perplexity Ask MCP Server running on stdio");
  } catch (error) {
    logger.error("Fatal error running server", error);
    process.exit(1);
  }
}

// Start the server and catch any startup errors
runServer().catch((error) => {
  logger.error("Fatal error running server", error);
  process.exit(1);
});
