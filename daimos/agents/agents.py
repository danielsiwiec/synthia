import re
from textwrap import dedent

from loguru import logger


class TaskAgentException(Exception):
    pass


agents: dict[str, str] = {
    "magazines": dedent("""
        ## Overall guidance
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
        Files should be saved in the `/Volumes/media/magazines` folder in the current working directory,
        according to the following folder organization:

        ```
        magazines/
            National Geographic USA/
                National Geographic USA - Aug 2025.pdf
            The Economist USA/
                The Economist USA - Sep 27, 2025.pdf
        ```
    """),
    "arr": dedent("""
        ## Overall guidance
        - The arr services are served by a docker compose stack, configured in /Users/dansiwiec/arr/docker-compose.yaml
        - Term 'arr services' refers to all services running in this docker compose stack
        - Use APIs below to query those services

        ## Available APIs
        qbittorrent: http://localhost:8080
    """),
    "airesearch": dedent("""
        ## Overall guidance
        - Perform a deep web research on user's query, by creating and publishing a report.
        - Respond only with the response structure below. Do not include any other text.
        - Combine patterns, libraries, frameworks, approaches from the web to create a comprehensive answer.
        - Especially point out recent, popular, or upcoming developments, libraries, frameworks, etc.
        - Point out which solutions are open source.
        - Use sources like: GitHub, bensbites.com, tech blogs from prominent companies, etc.
        - When listing GitHub repos, add an image for star history, like this: https://api.star-history.com/svg?repos=owner/repository&type=Date
        - For each item, include a resources section with helpful links and references to the item at hand

        ## Steps
        1. Perform the deep research, as described in the overall guidance
        2. Upload the document to MarkdownPaste, as described below
        3. Respond back to the user with the "response structure" below

        ## Response structure
        ```
        **Research Complete:**
        [Document Title](Share Link)

        ## Using MarkdownPaste
        - Post the content to https://markdownpaste-api.onrender.com/api/documents using the following JSON payload:
        ```
        {
          "title":FILL_THIS,
          "content":FILL_THIS,
          "visibility":"public",
          "password":"",
          "editKey":"",
          "expiresAt":""}
        ```
        - Pipe it through `jq -r '.data.slug'` to only get slug, as the response is very long
        - Save the request in a temporary json file and use `curl -d @file.json` syntax to send it
        - The link to the document will be: https://www.markdownpaste.com/document/[slug]
    """),
}


def get_agent_system_prompt(objective: str) -> str | None:
    agent_tags = re.findall(r"#(\w+)", objective)

    if len(agent_tags) > 1:
        raise TaskAgentException(f"Multiple tags found: {agent_tags}. Only one tag is allowed.")

    if agent_tags:
        agent_name = agent_tags[0]

        if agent_name not in agents:
            raise TaskAgentException(f"Agent '{agent_name}' not found")

        logger.info(f"Using agent: {agent_name}")
        return agents[agent_name]

    logger.info("No agent tag found, no system prompt")
    return None
