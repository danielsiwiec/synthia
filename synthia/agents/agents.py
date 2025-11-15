import re
from pathlib import Path

from loguru import logger

from synthia.agents.models import AgentSelection
from synthia.helpers.pubsub import pubsub


class TaskAgentException(Exception):
    pass


def _load_agents() -> dict[str, str]:
    agents = {}
    catalog_dir = Path(__file__).parent / "catalog"

    if not catalog_dir.exists():
        logger.warning(f"Catalog directory not found: {catalog_dir}")
        return agents

    for md_file in catalog_dir.glob("*.md"):
        agent_name = md_file.stem
        try:
            content = md_file.read_text(encoding="utf-8").strip()
            agents[agent_name] = content
            logger.debug(f"Loaded agent: {agent_name}")
        except Exception as e:
            logger.error(f"Failed to load agent {agent_name}: {e}")

    return agents


async def get_agent_system_prompt(objective: str) -> str | None:
    agent_tags = re.findall(r"#(\w+)", objective)

    if len(agent_tags) > 1:
        raise TaskAgentException(f"Multiple tags found: {agent_tags}. Only one tag is allowed.")

    if agent_tags:
        agent_name = agent_tags[0]
        agents = _load_agents()

        if agent_name not in agents:
            raise TaskAgentException(f"Agent '{agent_name}' not found")

        logger.info(f"Using agent: {agent_name}")
        agent = agents[agent_name]
    else:
        logger.info("No agent tag found, no system prompt")
        agent = None
        agent_name = None

    await pubsub.publish(AgentSelection(agent_name=agent_name if agent else None))
    return agent
