import { describe, it, expect, vi } from "vitest";
import { z } from "zod";
import { NuggetsBaseTool } from "../../src/tools/base.js";
import { NuggetsApiClient } from "../../src/client/nuggets-api-client.js";
import type { NuggetsConfig } from "../../src/types.js";

const mockConfig: NuggetsConfig = {
  apiUrl: "https://api.nuggets.test",
  partnerId: "test-partner",
  partnerSecret: "test-secret",
};

class TestTool extends NuggetsBaseTool {
  name = "test_tool";
  description = "A test tool";
  schema = z.object({
    input: z.string().describe("Test input"),
  });

  async _call({ input }: { input: string }): Promise<string> {
    return `processed: ${input}`;
  }
}

describe("NuggetsBaseTool", () => {
  it("should accept a NuggetsApiClient via constructor", () => {
    const client = new NuggetsApiClient(mockConfig);
    const tool = new TestTool({ client });
    expect(tool).toBeDefined();
    expect(tool.name).toBe("test_tool");
  });

  it("should invoke _call with parsed input", async () => {
    const client = new NuggetsApiClient(mockConfig);
    const tool = new TestTool({ client });
    const result = await tool.invoke({ input: "hello" });
    expect(result).toBe("processed: hello");
  });
});
