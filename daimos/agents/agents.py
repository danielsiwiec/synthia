import re
from pathlib import Path

from loguru import logger

from daimos.agents.learning.learner import Learner
from daimos.agents.models import AgentSelection
from daimos.helpers.pubsub import pubsub


class TaskAgentException(Exception):
    pass


def _load_agents(learner: Learner) -> dict[str, str]:
    agents = {}
    catalog_dir = Path(__file__).parent / "catalog"

    if not catalog_dir.exists():
        logger.warning(f"Catalog directory not found: {catalog_dir}")
        return agents

    skills = learner.load_all_skills()
    skills_section = _build_skills_section(skills)

    for md_file in catalog_dir.glob("*.md"):
        agent_name = md_file.stem
        try:
            content = md_file.read_text(encoding="utf-8").strip()

            if skills_section:
                content = f"{content}\n\n{skills_section}"
                logger.debug(f"Added skills section to agent: {agent_name}")

            agents[agent_name] = content
            logger.debug(f"Loaded agent: {agent_name}")
        except Exception as e:
            logger.error(f"Failed to load agent {agent_name}: {e}")

    return agents


def _build_skills_section(skills: list[dict]) -> str:
    if not skills:
        return ""

    section = "## Available Skills\n\n"
    section += "The following skills contain learnings from previous tasks. "
    section += "If you are performing a task similar to any of these skills, "
    section += "read the corresponding skill file to incorporate the learnings:\n\n"

    for skill in skills:
        section += f"- **{skill['name']}**: {skill['description']}\n"

    return section


async def get_agent_system_prompt(objective: str, learner: Learner) -> str | None:
    agent_tags = re.findall(r"#(\w+)", objective)

    if len(agent_tags) > 1:
        raise TaskAgentException(f"Multiple tags found: {agent_tags}. Only one tag is allowed.")

    if agent_tags:
        agent_name = agent_tags[0]
        agents = _load_agents(learner)

        if agent_name not in agents:
            raise TaskAgentException(f"Agent '{agent_name}' not found")

        logger.info(f"Using agent: {agent_name}")
        agent = agents[agent_name]
    else:
        logger.info("No agent tag found, no system prompt")
        agent = None
        agent_name = None

    await pubsub.publish(AgentSelection, AgentSelection(agent_name=agent_name if agent else None))
    return agent
