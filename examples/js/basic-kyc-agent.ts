/**
 * Basic KYC Agent Example
 *
 * Demonstrates how to create a LangChain agent that can verify
 * a user's identity using Nuggets KYC tools.
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
 *   npx tsx examples/js/basic-kyc-agent.ts
 */

import { ChatOpenAI } from "@langchain/openai";
import { AgentExecutor, createOpenAIToolsAgent } from "langchain/agents";
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { NuggetsToolkit } from "@nuggetslife/langchain";

async function main() {
  // 1. Create the Nuggets toolkit (reads config from env vars)
  const toolkit = new NuggetsToolkit();
  const tools = toolkit.getTools();

  // 2. Set up the LLM
  const llm = new ChatOpenAI({ model: "gpt-4o", temperature: 0 });

  // 3. Create a prompt that instructs the agent about identity verification
  const prompt = ChatPromptTemplate.fromMessages([
    [
      "system",
      "You are a helpful assistant that can verify user identities using Nuggets. " +
        "When a user needs to be verified, use the KYC tools to initiate verification " +
        "and guide them through the process. Always explain what you're doing and why.",
    ],
    ["human", "{input}"],
    ["placeholder", "{agent_scratchpad}"],
  ]);

  // 4. Create the agent
  const agent = await createOpenAIToolsAgent({ llm, tools, prompt });
  const executor = new AgentExecutor({ agent, tools, verbose: true });

  // 5. Run a verification flow
  const result = await executor.invoke({
    input:
      "I need to verify my identity. My email is alice@example.com. " +
      "Can you start the KYC process for me?",
  });

  console.log("Agent response:", result.output);
}

main().catch(console.error);
