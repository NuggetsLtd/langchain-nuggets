/**
 * Selective Disclosure Example
 *
 * Demonstrates Nuggets selective disclosure capabilities:
 * 1. Age verification — prove 18+ without revealing date of birth
 * 2. Credential verification — verify a specific credential type
 * 3. Credential presentation — request and verify multiple credentials
 *
 * These tools enable privacy-preserving identity checks where only
 * the minimum required information is shared.
 *
 * Prerequisites:
 * - A Nuggets partner account (partnerId + partnerSecret)
 * - An OpenAI API key (or any LangChain-supported LLM)
 *
 * Usage:
 *   NUGGETS_API_URL=https://api.nuggets.life \
 *   NUGGETS_PARTNER_ID=your-partner-id \
 *   NUGGETS_PARTNER_SECRET=your-secret \
 *   OPENAI_API_KEY=your-key \
 *   npx tsx examples/js/selective-disclosure.ts
 */

import { ChatOpenAI } from "@langchain/openai";
import { AgentExecutor, createOpenAIToolsAgent } from "langchain/agents";
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { NuggetsToolkit } from "@nuggetslife/langchain";

async function main() {
  const toolkit = new NuggetsToolkit();
  const tools = toolkit.getTools();

  const llm = new ChatOpenAI({ model: "gpt-4o", temperature: 0 });

  const prompt = ChatPromptTemplate.fromMessages([
    [
      "system",
      "You are an identity verification assistant that prioritizes user privacy. " +
        "Use Nuggets selective disclosure tools to verify only what's needed:\n\n" +
        "- Use verify_age for age-gated operations (proves 18+ without revealing DOB)\n" +
        "- Use verify_credential for single credential checks\n" +
        "- Use request_credential_presentation + verify_presentation for multi-credential flows\n\n" +
        "Always explain to the user what information will be disclosed and why.",
    ],
    ["human", "{input}"],
    ["placeholder", "{agent_scratchpad}"],
  ]);

  const agent = await createOpenAIToolsAgent({ llm, tools, prompt });
  const executor = new AgentExecutor({ agent, tools, verbose: true });

  // Scenario 1: Age verification for restricted content
  console.log("--- Scenario 1: Age verification ---");
  const ageResult = await executor.invoke({
    input:
      "User alice@example.com wants to access age-restricted content. " +
      "Verify they are at least 18 years old without asking for their date of birth.",
  });
  console.log("Age verification:", ageResult.output);

  // Scenario 2: Credential-based access (nationality check)
  console.log("\n--- Scenario 2: Credential verification ---");
  const credResult = await executor.invoke({
    input:
      "User bob@example.com needs to prove their country of residence " +
      "for regulatory compliance. Verify their address credential.",
  });
  console.log("Credential verification:", credResult.output);

  // Scenario 3: Multi-credential presentation
  console.log("\n--- Scenario 3: Multi-credential presentation ---");
  const presentResult = await executor.invoke({
    input:
      "For onboarding, user carol@example.com needs to share their " +
      "email and phone credentials. Request both and verify the presentation.",
  });
  console.log("Presentation:", presentResult.output);
}

main().catch(console.error);
