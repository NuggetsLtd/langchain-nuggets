"""
Multi-Agent Trust Example

Demonstrates how an AI agent can use Nuggets KYA (Know Your Agent)
tools to establish trust in multi-agent systems:
1. Register its own identity with provenance signals
2. Verify another agent's identity
3. Check trust scores before sharing sensitive data

Prerequisites:
- A Nuggets partner account (partnerId + partnerSecret)
- An OpenAI API key (or any LangChain-supported LLM)

Usage:
  NUGGETS_API_URL=https://api.nuggets.life \
  NUGGETS_PARTNER_ID=your-partner-id \
  NUGGETS_PARTNER_SECRET=your-secret \
  OPENAI_API_KEY=your-key \
  python examples/python/multi_agent_trust.py
"""

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate

from langchain_nuggets import NuggetsToolkit


def main():
    toolkit = NuggetsToolkit()
    tools = toolkit.get_tools()

    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a data-sharing agent that uses Nuggets KYA tools to establish trust "
            "before exchanging information with other agents.\n\n"
            "Your workflow:\n"
            "1. First, register your own identity using register_agent_identity\n"
            "2. When asked to interact with another agent, verify their identity first\n"
            "3. Check their trust score — only share data if score >= 0.7\n"
            "4. Explain your trust decisions clearly",
        ),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    # Step 1: Register this agent's identity
    print("--- Step 1: Registering agent identity ---")
    register_result = executor.invoke({
        "input": (
            "Register my identity as 'DataShareBot' with GitHub URL "
            "https://github.com/NuggetsLtd/langchain-nuggets and "
            "Twitter handle @nugaborat"
        ),
    })
    print("Register result:", register_result["output"])

    # Step 2: Verify and score another agent before trusting it
    print("\n--- Step 2: Verify another agent ---")
    trust_result = executor.invoke({
        "input": (
            "I need to share customer data with agent 'agent-abc-123'. "
            "First verify their identity and check their trust score. "
            "Only approve data sharing if the trust score is 0.7 or higher."
        ),
    })
    print("Trust result:", trust_result["output"])


if __name__ == "__main__":
    main()
