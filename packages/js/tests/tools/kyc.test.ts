import { describe, it, expect, vi } from "vitest";
import { NuggetsApiClient } from "../../src/client/nuggets-api-client.js";
import { InitiateKycVerification } from "../../src/tools/kyc/initiate-kyc-verification.js";
import { CheckKycStatus } from "../../src/tools/kyc/check-kyc-status.js";
import { VerifyAge } from "../../src/tools/kyc/verify-age.js";
import { VerifyCredential } from "../../src/tools/kyc/verify-credential.js";
import type { NuggetsConfig, KycSession, KycResult } from "../../src/types.js";

const mockConfig: NuggetsConfig = {
  apiUrl: "https://api.nuggets.test",
  partnerId: "test-partner",
  partnerSecret: "test-secret",
};

function createClient() {
  return new NuggetsApiClient(mockConfig);
}

describe("KYC Tools", () => {
  describe("InitiateKycVerification", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new InitiateKycVerification({ client });
      expect(tool.name).toBe("initiate_kyc_verification");
      expect(tool.description).toContain("KYC");
      expect(tool.description).toContain("verification");
    });

    it("should call client.post and return session JSON", async () => {
      const client = createClient();
      const tool = new InitiateKycVerification({ client });

      const mockSession: KycSession = {
        sessionId: "sess-123",
        deeplink: "nuggets://kyc/sess-123",
        qrCodeUrl: "https://api.nuggets.test/qr/sess-123",
      };

      vi.spyOn(client, "post").mockResolvedValue(mockSession);

      const result = await tool.invoke({ userId: "user@example.com" });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockSession);
      expect(client.post).toHaveBeenCalledWith("/kyc/sessions", {
        userId: "user@example.com",
      });
    });
  });

  describe("CheckKycStatus", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new CheckKycStatus({ client });
      expect(tool.name).toBe("check_kyc_status");
      expect(tool.description).toContain("status");
      expect(tool.description).toContain("KYC");
    });

    it("should call client.get and return status JSON", async () => {
      const client = createClient();
      const tool = new CheckKycStatus({ client });

      const mockResult: KycResult = {
        sessionId: "sess-123",
        status: "completed",
        credentials: [
          {
            id: "cred-1",
            type: ["VerifiableCredential", "IdentityCredential"],
            issuer: "did:nuggets:issuer",
            issuanceDate: "2024-01-01T00:00:00Z",
            credentialSubject: { name: "Test User" },
          },
        ],
      };

      vi.spyOn(client, "get").mockResolvedValue(mockResult);

      const result = await tool.invoke({ sessionId: "sess-123" });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockResult);
      expect(client.get).toHaveBeenCalledWith("/kyc/sessions/sess-123");
    });
  });

  describe("VerifyAge", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new VerifyAge({ client });
      expect(tool.name).toBe("verify_age");
      expect(tool.description).toContain("age");
      expect(tool.description).toContain("minimum");
    });

    it("should call client.post with userId and minimumAge", async () => {
      const client = createClient();
      const tool = new VerifyAge({ client });

      const mockSession: KycSession = {
        sessionId: "age-sess-456",
        deeplink: "nuggets://kyc/age-sess-456",
        qrCodeUrl: "https://api.nuggets.test/qr/age-sess-456",
      };

      vi.spyOn(client, "post").mockResolvedValue(mockSession);

      const result = await tool.invoke({
        userId: "user@example.com",
        minimumAge: 18,
      });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockSession);
      expect(client.post).toHaveBeenCalledWith("/kyc/verify-age", {
        userId: "user@example.com",
        minimumAge: 18,
      });
    });
  });

  describe("VerifyCredential", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new VerifyCredential({ client });
      expect(tool.name).toBe("verify_credential");
      expect(tool.description).toContain("credential");
      expect(tool.description).toContain("selective disclosure");
    });

    it("should call client.post with userId and credentialType", async () => {
      const client = createClient();
      const tool = new VerifyCredential({ client });

      const mockSession: KycSession = {
        sessionId: "cred-sess-789",
        deeplink: "nuggets://kyc/cred-sess-789",
        qrCodeUrl: "https://api.nuggets.test/qr/cred-sess-789",
      };

      vi.spyOn(client, "post").mockResolvedValue(mockSession);

      const result = await tool.invoke({
        userId: "user@example.com",
        credentialType: "address",
      });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockSession);
      expect(client.post).toHaveBeenCalledWith("/kyc/verify-credential", {
        userId: "user@example.com",
        credentialType: "address",
      });
    });
  });
});
