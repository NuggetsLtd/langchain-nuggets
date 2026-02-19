"""
Selective Disclosure Example

Demonstrates Nuggets selective disclosure capabilities:
1. Age verification — prove 18+ without revealing date of birth
2. Credential verification — verify a specific credential type
3. Credential presentation — request and verify multiple credentials

These tools enable privacy-preserving identity checks where only
the minimum required information is shared.

Prerequisites:
- A Nuggets partner account (partnerId + partnerSecret)
- An OpenAI API key (or any LangChain-supported LLM)

Usage:
  NUGGETS_API_URL=https://api.nuggets.life \
  NUGGETS_PARTNER_ID=your-partner-id \
  NUGGETS_PARTNER_SECRET=your-secret \
  OPENAI_API_KEY=your-key \
  python examples/python/selective_disclosure.py
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
            "You are an identity verification assistant that prioritizes user privacy. "
            "Use Nuggets selective disclosure tools to verify only what's needed:\n\n"
            "- Use verify_age for age-gated operations (proves 18+ without revealing DOB)\n"
            "- Use verify_credential for single credential checks\n"
            "- Use request_credential_presentation + verify_presentation for multi-credential flows\n\n"
            "Always explain to the user what information will be disclosed and why.",
        ),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    # Scenario 1: Age verification for restricted content
    print("--- Scenario 1: Age verification ---")
    age_result = executor.invoke({
        "input": (
            "User alice@example.com wants to access age-restricted content. "
            "Verify they are at least 18 years old without asking for their date of birth."
        ),
    })
    print("Age verification:", age_result["output"])

    # Scenario 2: Credential-based access (nationality check)
    print("\n--- Scenario 2: Credential verification ---")
    cred_result = executor.invoke({
        "input": (
            "User bob@example.com needs to prove their country of residence "
            "for regulatory compliance. Verify their address credential."
        ),
    })
    print("Credential verification:", cred_result["output"])

    # Scenario 3: Multi-credential presentation
    print("\n--- Scenario 3: Multi-credential presentation ---")
    present_result = executor.invoke({
        "input": (
            "For onboarding, user carol@example.com needs to share their "
            "email and phone credentials. Request both and verify the presentation."
        ),
    })
    print("Presentation:", present_result["output"])


if __name__ == "__main__":
    main()
