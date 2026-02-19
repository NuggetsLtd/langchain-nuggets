import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { NuggetsApiClient } from "@nuggetslife/langchain";
import type { NuggetsConfig } from "@nuggetslife/langchain";
import { registerTools } from "./tools.js";

export interface McpServerConfig {
  apiUrl?: string;
  partnerId?: string;
  partnerSecret?: string;
}

export function createNuggetsMcpServer(config?: McpServerConfig): McpServer {
  const resolvedConfig: NuggetsConfig = {
    apiUrl: config?.apiUrl || process.env.NUGGETS_API_URL || "",
    partnerId: config?.partnerId || process.env.NUGGETS_PARTNER_ID || "",
    partnerSecret: config?.partnerSecret || process.env.NUGGETS_PARTNER_SECRET || "",
  };

  if (!resolvedConfig.apiUrl || !resolvedConfig.partnerId || !resolvedConfig.partnerSecret) {
    throw new Error(
      "Nuggets MCP server requires apiUrl, partnerId, and partnerSecret. " +
        "Set NUGGETS_API_URL, NUGGETS_PARTNER_ID, NUGGETS_PARTNER_SECRET environment variables.",
    );
  }

  const client = new NuggetsApiClient(resolvedConfig);
  const server = new McpServer({
    name: "nuggets-identity",
    version: "0.1.0",
  });

  registerTools(server, client);

  return server;
}

export { registerTools } from "./tools.js";
