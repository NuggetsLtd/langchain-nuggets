import { z } from "zod";
import type { NuggetsApiClient } from "@nuggetslife/langchain";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

type ToolResult = { content: { type: "text"; text: string }[]; isError?: boolean };

function wrapHandler<T>(fn: (args: T) => Promise<ToolResult>): (args: T) => Promise<ToolResult> {
  return async (args: T) => {
    try {
      return await fn(args);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        content: [{ type: "text" as const, text: JSON.stringify({ error: true, message }) }],
        isError: true,
      };
    }
  };
}

export function registerTools(server: McpServer, client: NuggetsApiClient): void {
  // --- KYC Tools ---

  server.registerTool(
    "initiate_kyc_verification",
    {
      description:
        "Start a KYC (Know Your Customer) identity verification flow for a user. Returns a deeplink and QR code URL that the user must scan with their Nuggets app to complete identity verification. Use check_kyc_status to poll for completion.",
      inputSchema: {
        userId: z
          .string()
          .describe(
            "The user's identifier (email or Nuggets address) to start KYC verification for",
          ),
      },
    },
    wrapHandler(async ({ userId }) => {
      const result = await client.post("/kyc/sessions", { userId });
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  server.registerTool(
    "check_kyc_status",
    {
      description:
        'Check the status of a KYC verification session. Returns status: "pending" (user has not yet completed), "completed" (verified), "failed" (verification failed), or "expired" (session timed out). If completed, includes the verified credentials.',
      inputSchema: {
        sessionId: z
          .string()
          .describe("The KYC session ID returned by initiate_kyc_verification"),
      },
    },
    wrapHandler(async ({ sessionId }) => {
      const result = await client.get(`/kyc/sessions/${encodeURIComponent(sessionId)}`);
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  server.registerTool(
    "verify_age",
    {
      description:
        "Request selective disclosure age verification for a user. Proves the user meets a minimum age requirement WITHOUT revealing their actual date of birth. Returns a deeplink/QR code for the user to approve the age proof in their Nuggets app. Use check_kyc_status with the returned sessionId to check if the user approved.",
      inputSchema: {
        userId: z.string().describe("The user's identifier (email or Nuggets address)"),
        minimumAge: z
          .number()
          .describe("The minimum age to verify (e.g. 18 for age-restricted content)"),
      },
    },
    wrapHandler(async ({ userId, minimumAge }) => {
      const result = await client.post("/kyc/verify-age", { userId, minimumAge });
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  server.registerTool(
    "verify_credential",
    {
      description:
        "Request selective disclosure verification of a specific credential for a user. The user will be asked to share only the requested credential type from their Nuggets app. Returns a deeplink/QR code for the user to approve. Use check_kyc_status with the returned sessionId to check completion.",
      inputSchema: {
        userId: z.string().describe("The user's identifier (email or Nuggets address)"),
        credentialType: z
          .string()
          .describe(
            'The type of credential to verify (e.g. "address", "nationality", "email", "phone")',
          ),
      },
    },
    wrapHandler(async ({ userId, credentialType }) => {
      const result = await client.post("/kyc/verify-credential", { userId, credentialType });
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  // --- KYA Tools ---

  server.registerTool(
    "register_agent_identity",
    {
      description:
        "Register this AI agent's identity with Nuggets to establish verifiable provenance. Provide developer provenance signals (GitHub, Twitter) so other agents and users can verify who built this agent. Returns a DID and agent identity record.",
      inputSchema: {
        agentName: z.string().describe("A human-readable name for this AI agent"),
        githubUrl: z
          .string()
          .optional()
          .describe("GitHub profile or repo URL for developer provenance verification"),
        twitterHandle: z
          .string()
          .optional()
          .describe("Twitter/X handle for social verification"),
      },
    },
    wrapHandler(async (input) => {
      const result = await client.post("/kya/agents", input);
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  server.registerTool(
    "verify_agent_identity",
    {
      description:
        "Verify another AI agent's identity through Nuggets. Returns the agent's registered identity including DID, developer provenance signals, and registration date. Use this before trusting data from or sharing data with another agent.",
      inputSchema: {
        agentId: z.string().describe("The agent ID or DID of the agent to verify"),
      },
    },
    wrapHandler(async ({ agentId }) => {
      const result = await client.get(`/kya/agents/${encodeURIComponent(agentId)}`);
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  server.registerTool(
    "get_agent_trust_score",
    {
      description:
        "Get the trust score and provenance signals for an AI agent. Returns a score (0-1) based on verified signals: GitHub account verification, social profile verification, and registration age. Higher scores indicate more trustworthy agents with stronger developer provenance.",
      inputSchema: {
        agentId: z.string().describe("The agent ID or DID to get the trust score for"),
      },
    },
    wrapHandler(async ({ agentId }) => {
      const result = await client.get(`/kya/agents/${encodeURIComponent(agentId)}/trust-score`);
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  // --- Auth Tools ---

  server.registerTool(
    "request_credential_presentation",
    {
      description:
        "Ask a user to present one or more verifiable credentials from their Nuggets app. Specify which credential types you need. The user will see a request in their app and can approve or reject sharing each credential. Use verify_presentation with the returned sessionId to check if the user responded.",
      inputSchema: {
        userId: z.string().describe("The user's identifier (email or Nuggets address)"),
        credentialTypes: z
          .array(z.string())
          .describe(
            'Array of credential types to request (e.g. ["email", "phone", "address"])',
          ),
      },
    },
    wrapHandler(async (input) => {
      const result = await client.post("/credentials/presentations", input);
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  server.registerTool(
    "verify_presentation",
    {
      description:
        'Check the status of a credential presentation request and cryptographically verify any presented credentials. Returns status: "pending" (awaiting user), "presented" (user shared credentials), "rejected" (user declined), or "expired". If presented, includes the verified credentials and a verified boolean.',
      inputSchema: {
        sessionId: z
          .string()
          .describe(
            "The presentation session ID returned by request_credential_presentation",
          ),
      },
    },
    wrapHandler(async ({ sessionId }) => {
      const result = await client.get(`/credentials/presentations/${encodeURIComponent(sessionId)}`);
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  server.registerTool(
    "initiate_oauth_flow",
    {
      description:
        "Start an OAuth 2.0 / OpenID Connect authentication flow with Nuggets as the identity provider. Returns an authorization URL that the user should be redirected to. After the user authenticates via Nuggets (QR scan, biometrics, or WebAuthn), they will be redirected back to the redirectUri with an authorization code.",
      inputSchema: {
        redirectUri: z
          .string()
          .describe("The URL to redirect the user to after authentication"),
        scopes: z
          .array(z.string())
          .optional()
          .describe(
            'OAuth scopes to request (e.g. ["openid", "profile", "email"]). Defaults to ["openid"]',
          ),
      },
    },
    wrapHandler(async ({ redirectUri, scopes }) => {
      const result = await client.post("/oauth/authorize", {
        redirectUri,
        scopes: scopes ?? ["openid"],
      });
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );

  server.registerTool(
    "check_auth_status",
    {
      description:
        "Check whether a user is currently authenticated with Nuggets and their verification status. Returns whether the user is authenticated, their KYC verification status, and which credentials they have on file. Use this to gate access to sensitive operations that require verified identity.",
      inputSchema: {
        userId: z
          .string()
          .describe("The user's identifier to check authentication status for"),
      },
    },
    wrapHandler(async ({ userId }) => {
      const result = await client.get(`/auth/status/${encodeURIComponent(userId)}`);
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }),
  );
}
