import { StructuredTool } from "@langchain/core/tools";
import { NuggetsApiClient, NuggetsApiClientError } from "../client/nuggets-api-client.js";

export interface NuggetsBaseToolParams {
  client: NuggetsApiClient;
}

export abstract class NuggetsBaseTool extends StructuredTool {
  protected client: NuggetsApiClient;

  constructor({ client }: NuggetsBaseToolParams) {
    super();
    this.client = client;
  }

  async invoke(
    input: Record<string, unknown>,
    config?: unknown
  ): Promise<string> {
    try {
      return await super.invoke(input, config as any);
    } catch (error) {
      if (error instanceof NuggetsApiClientError) {
        return JSON.stringify({
          error: true,
          code: error.code,
          message: error.message,
          statusCode: error.statusCode,
        });
      }
      throw error;
    }
  }
}
