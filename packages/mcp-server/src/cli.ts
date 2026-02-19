#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createNuggetsMcpServer } from "./index.js";

async function main() {
  const server = createNuggetsMcpServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error("Failed to start Nuggets MCP server:", error);
  process.exit(1);
});
