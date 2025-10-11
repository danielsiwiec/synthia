import re

from claude_agent_sdk import AgentDefinition
from loguru import logger


class TaskAgentException(Exception):
    pass


subagents: dict[str, AgentDefinition] = {
    "magazines": AgentDefinition(
        description="fetches a single magazine from freemag website. Use one at a time, not concurrently",
        prompt="""## Overall guidance
- Do NOT use this agent concurrently. Execute it one at a time.
- Use a browser to download the magazine file, not HTTP requests, like WebFetch, curl or wget
- Do NOT use curl to download the magzine file, as it will be blocked. Use the downlaod button on the page,
  instead, using the browser.
- Do NOT save the magazine file the `~/Downloads` folder. Instead, follow the instructions below regarding
  the file's save location
- If magazines have localized issues, such as USA, UK, Global, etc, always pick the USA edition
- Look for a 'Download' button or link on the page. Click on it to download the magazine file.

## Steps
1. Navigate to https://freemagazines.top/ website using the browser.
2. Search for the requested title.
3. Compare the latest issue with the latest one in the `magazines/` folder.
4. If the folder already contains the latest issue, do nothing.
5. If the issue doesn't exist, keep navigating the website until you find the download button or link.
6. Save the file in the `magazines` directory in the current working folder, according to the 'Save
   location' section below
7. Verify the size of the file. It should be at least 5MBs. If it's less than that, the downloaded file is
   likely invalid. Try another method.

## Save location
Files should be saved in the `/Volumes/media/magazines` folder in the current working directory, according to the
following folder organization:

```
magazines/
    National Geographic USA/
        National Geographic USA - Aug 2025.pdf
    The Economist USA/
        The Economist USA - Sep 27, 2025.pdf
```""",
    ),
    "arr": AgentDefinition(
        description="answer questions and perform tasks related to 'arr' services",
        prompt="""## Overall guidance
- The arr services are served by a docker compose stack, configured in /Users/dansiwiec/arr/docker-compose.yaml
- Term 'arr services' refers to all services running in this docker compose stack
""",
    ),
}


def get_matching_subagents(objective: str) -> dict[str, AgentDefinition]:
    agent_tags = re.findall(r"#(\w+)", objective)
    if not agent_tags:
        return {}

    if len(agent_tags) > 1:
        raise TaskAgentException(f"Multiple tags found: {agent_tags}. Only one tag is allowed.")

    matching_agents = {}
    for agent_name in agent_tags:
        if agent_name in subagents:
            matching_agents[agent_name] = subagents[agent_name]

    if matching_agents:
        logger.info(f"Matching subagents: {list(matching_agents.keys())}")
    else:
        logger.info("No matching subagents found")
    return matching_agents
