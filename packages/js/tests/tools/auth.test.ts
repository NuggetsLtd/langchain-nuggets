import { describe, it, expect, vi } from "vitest";
import { NuggetsApiClient } from "../../src/client/nuggets-api-client.js";
import { RequestCredentialPresentation } from "../../src/tools/auth/request-credential-presentation.js";
import { VerifyPresentation } from "../../src/tools/auth/verify-presentation.js";
import { InitiateOAuthFlow } from "../../src/tools/auth/initiate-oauth-flow.js";
import { CheckAuthStatus } from "../../src/tools/auth/check-auth-status.js";
import type {
  NuggetsConfig,
  CredentialPresentation,
  PresentationResult,
  OAuthSession,
  AuthStatus,
} from "../../src/types.js";

const mockConfig: NuggetsConfig = {
  apiUrl: "https://api.nuggets.test",
  partnerId: "test-partner",
  partnerSecret: "test-secret",
};

function createClient() {
  return new NuggetsApiClient(mockConfig);
}

describe("Auth Tools", () => {
  describe("RequestCredentialPresentation", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new RequestCredentialPresentation({ client });
      expect(tool.name).toBe("request_credential_presentation");
      expect(tool.description).toContain("credential");
      expect(tool.description).toContain("present");
    });

    it("should call client.post with userId and credentialTypes array", async () => {
      const client = createClient();
      const tool = new RequestCredentialPresentation({ client });

      const mockPresentation: CredentialPresentation = {
        sessionId: "pres-123",
        deeplink: "nuggets://present/pres-123",
        qrCodeUrl: "https://api.nuggets.test/qr/pres-123",
      };

      vi.spyOn(client, "post").mockResolvedValue(mockPresentation);

      const result = await tool.invoke({
        userId: "user@example.com",
        credentialTypes: ["email", "phone", "address"],
      });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockPresentation);
      expect(client.post).toHaveBeenCalledWith("/credentials/presentations", {
        userId: "user@example.com",
        credentialTypes: ["email", "phone", "address"],
      });
    });
  });

  describe("VerifyPresentation", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new VerifyPresentation({ client });
      expect(tool.name).toBe("verify_presentation");
      expect(tool.description).toContain("credential");
      expect(tool.description).toContain("presentation");
    });

    it("should call client.get with sessionId and return verified boolean", async () => {
      const client = createClient();
      const tool = new VerifyPresentation({ client });

      const mockResult: PresentationResult = {
        sessionId: "pres-123",
        status: "presented",
        credentials: [
          {
            id: "cred-1",
            type: ["VerifiableCredential", "EmailCredential"],
            issuer: "did:nuggets:issuer",
            issuanceDate: "2024-01-01T00:00:00Z",
            credentialSubject: { email: "user@example.com" },
          },
        ],
        verified: true,
      };

      vi.spyOn(client, "get").mockResolvedValue(mockResult);

      const result = await tool.invoke({ sessionId: "pres-123" });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockResult);
      expect(parsed.verified).toBe(true);
      expect(parsed.status).toBe("presented");
      expect(client.get).toHaveBeenCalledWith("/credentials/presentations/pres-123");
    });
  });

  describe("InitiateOAuthFlow", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new InitiateOAuthFlow({ client });
      expect(tool.name).toBe("initiate_oauth_flow");
      expect(tool.description).toContain("OAuth");
      expect(tool.description).toContain("authentication");
    });

    it("should call client.post with redirectUri and scopes, returns authorizationUrl", async () => {
      const client = createClient();
      const tool = new InitiateOAuthFlow({ client });

      const mockSession: OAuthSession = {
        authorizationUrl: "https://auth.nuggets.test/authorize?state=abc",
        state: "abc",
        codeVerifier: "verifier-123",
      };

      vi.spyOn(client, "post").mockResolvedValue(mockSession);

      const result = await tool.invoke({
        redirectUri: "https://myapp.test/callback",
        scopes: ["openid", "profile", "email"],
      });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockSession);
      expect(parsed.authorizationUrl).toBeDefined();
      expect(client.post).toHaveBeenCalledWith("/oauth/authorize", {
        redirectUri: "https://myapp.test/callback",
        scopes: ["openid", "profile", "email"],
      });
    });

    it("should default scopes to ['openid'] when not provided", async () => {
      const client = createClient();
      const tool = new InitiateOAuthFlow({ client });

      const mockSession: OAuthSession = {
        authorizationUrl: "https://auth.nuggets.test/authorize?state=def",
        state: "def",
        codeVerifier: "verifier-456",
      };

      vi.spyOn(client, "post").mockResolvedValue(mockSession);

      const result = await tool.invoke({
        redirectUri: "https://myapp.test/callback",
      });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockSession);
      expect(client.post).toHaveBeenCalledWith("/oauth/authorize", {
        redirectUri: "https://myapp.test/callback",
        scopes: ["openid"],
      });
    });
  });

  describe("CheckAuthStatus", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new CheckAuthStatus({ client });
      expect(tool.name).toBe("check_auth_status");
      expect(tool.description).toContain("authenticated");
      expect(tool.description).toContain("verification");
    });

    it("should call client.get with userId and return authenticated and kycVerified booleans", async () => {
      const client = createClient();
      const tool = new CheckAuthStatus({ client });

      const mockStatus: AuthStatus = {
        authenticated: true,
        userId: "user@example.com",
        kycVerified: true,
        credentials: ["email", "phone", "address"],
      };

      vi.spyOn(client, "get").mockResolvedValue(mockStatus);

      const result = await tool.invoke({ userId: "user@example.com" });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockStatus);
      expect(parsed.authenticated).toBe(true);
      expect(parsed.kycVerified).toBe(true);
      expect(client.get).toHaveBeenCalledWith("/auth/status/user@example.com");
    });
  });
});
