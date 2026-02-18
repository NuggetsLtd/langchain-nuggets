import { StructuredTool } from "@langchain/core/tools";
import { NuggetsApiClient } from "../client/nuggets-api-client.js";

export interface NuggetsBaseToolParams {
  client: NuggetsApiClient;
}

export abstract class NuggetsBaseTool extends StructuredTool {
  protected client: NuggetsApiClient;

  constructor({ client }: NuggetsBaseToolParams) {
    super();
    this.client = client;
  }
}
