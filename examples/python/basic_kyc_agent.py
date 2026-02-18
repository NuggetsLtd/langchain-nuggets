"""
Basic KYC Agent Example

Demonstrates how to create a LangChain agent that can verify
a user's identity using Nuggets KYC tools.

Prerequisites:
- A Nuggets partner account (partnerId + partnerSecret)
- An OpenAI API key (or any LangChain-supported LLM)

Usage:
  NUGGETS_API_URL=https://api.nuggets.life \
  NUGGETS_PARTNER_ID=your-partner-id \
  NUGGETS_PARTNER_SECRET=your-secret \
  OPENAI_API_KEY=your-key \
  python examples/python/basic_kyc_agent.py
"""

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate

from langchain_nuggets import NuggetsToolkit


def main():
    # 1. Create the Nuggets toolkit (reads config from env vars)
    toolkit = NuggetsToolkit()
    tools = toolkit.get_tools()

    # 2. Set up the LLM
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # 3. Create a prompt that instructs the agent about identity verification
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a helpful assistant that can verify user identities using Nuggets. "
            "When a user needs to be verified, use the KYC tools to initiate verification "
            "and guide them through the process. Always explain what you're doing and why.",
        ),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    # 4. Create the agent
    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    # 5. Run a verification flow
    result = executor.invoke({
        "input": (
            "I need to verify my identity. My email is alice@example.com. "
            "Can you start the KYC process for me?"
        ),
    })

    print("Agent response:", result["output"])


if __name__ == "__main__":
    main()
