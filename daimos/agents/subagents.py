import re

from claude_agent_sdk import AgentDefinition

subagents: dict[str, AgentDefinition] = {}


def get_matching_subagents(objective: str) -> dict[str, AgentDefinition]:
    agent_tags = re.findall(r"#(\w+)", objective)
    if not agent_tags:
        return {}

    matching_agents = {}
    for agent_name in agent_tags:
        if agent_name in subagents:
            matching_agents[agent_name] = subagents[agent_name]

    return matching_agents
