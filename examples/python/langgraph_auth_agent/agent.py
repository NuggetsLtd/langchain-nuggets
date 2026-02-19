"""Simple ReAct agent with Nuggets identity tools, secured by Nuggets OIDC.

The agent can verify user identities, check KYC status, manage credentials,
and more — all gated behind Nuggets OIDC authentication.
"""
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from langchain_nuggets import NuggetsToolkit

toolkit = NuggetsToolkit()
tools = toolkit.get_tools()

llm = ChatOpenAI(model="gpt-4o", temperature=0)

graph = create_react_agent(
    llm,
    tools=tools,
    state_modifier=(
        "You are an identity verification assistant powered by Nuggets. "
        "The user calling you has been authenticated via Nuggets OIDC. "
        "You can help them with KYC verification, credential management, "
        "agent identity verification, and authentication flows. "
        "Always explain what you're doing and why."
    ),
)
