import express, { type Express } from "express";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import { createNuggetsMcpServer } from "./index.js";

const PORT = parseInt(process.env.PORT || "3001", 10);

const app: Express = express();

const transports = new Map<string, SSEServerTransport>();

app.get("/sse", async (_req, res) => {
  const server = createNuggetsMcpServer();
  const transport = new SSEServerTransport("/messages", res);
  const sessionId = transport.sessionId;
  transports.set(sessionId, transport);

  res.on("close", () => {
    transports.delete(sessionId);
  });

  await server.connect(transport);
});

app.post("/messages", async (req, res) => {
  const sessionId = req.query.sessionId as string;
  const transport = transports.get(sessionId);
  if (!transport) {
    res.status(400).json({ error: "No SSE connection found for this session" });
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
