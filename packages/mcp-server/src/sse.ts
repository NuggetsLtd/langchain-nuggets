import express, { type Express } from "express";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { createNuggetsMcpServer } from "./index.js";

const PORT = parseInt(process.env.PORT || "3001", 10);

const app: Express = express();
const server = createNuggetsMcpServer();

let transport: SSEServerTransport | null = null;

app.get("/sse", async (_req, res) => {
  transport = new SSEServerTransport("/messages", res);
  await server.connect(transport);
});

app.post("/messages", async (req, res) => {
  if (!transport) {
    res.status(400).json({ error: "No SSE connection established" });
    return;
  }
  await transport.handlePostMessage(req, res);
});

app.get("/health", (_req, res) => {
  res.json({ status: "ok", server: "nuggets-mcp", version: "0.1.0" });
});

app.listen(PORT, () => {
  console.log(`Nuggets MCP server (SSE) listening on port ${PORT}`);
  console.log(`  SSE endpoint: http://localhost:${PORT}/sse`);
  console.log(`  Messages:     http://localhost:${PORT}/messages`);
});

export { app };
