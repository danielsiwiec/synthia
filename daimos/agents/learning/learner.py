from collections import defaultdict
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel

from daimos.agents.claude import Message, run_for_result
from daimos.helpers.pubsub import pubsub
from daimos.output import parse_from_type
from daimos.service.models import TaskCompletion


class Skill(BaseModel):
    skill_name: str
    description: str
    content: str
    is_new: bool


class SkillsResponse(BaseModel):
    skills: list[Skill]


class Learner:
    def __init__(self, skills_dir: Path | None = None):
        if skills_dir is None:
            skills_dir = Path(__file__).parent.parent / "skills"
        self.skills_dir = skills_dir
        self.skills_dir.mkdir(exist_ok=True)
        self.sessions = defaultdict(list)
        pubsub.subscribe(TaskCompletion, self._on_task_completion)

    async def process_message(self, message: Message) -> None:
        session_id = message.session_id
        self.sessions[session_id].append(message)

    async def _on_task_completion(self, task_completion: TaskCompletion) -> None:
        session_id = task_completion.session_id

        if session_id in self.sessions:
            messages = self.sessions[session_id]
            await self._process_completed_task(session_id, messages)

    async def _process_completed_task(self, session_id: str, messages: list[Message]) -> None:
        await self.process_completed_task(session_id, messages)

    async def process_completed_task(self, session_id: str, messages: list[Message]) -> None:
        if not messages:
            logger.debug(f"No messages for session {session_id}, skipping learning")
            return

        skills_content = await self._generate_skills(messages)
        if skills_content:
            logger.info(f"Generated {len(skills_content)} skill(s) from session {session_id}")
            await self._save_skills(skills_content)
        else:
            logger.debug(f"No skills generated for session {session_id}")

    async def _generate_skills(self, messages: list[Message]) -> list[dict[str, Any]] | None:
        analysis_prompt = self._build_skills_prompt(messages)

        logger.debug("Generating skills from task session")

        result = await run_for_result(analysis_prompt)
        if result and result.success:
            return await self._parse_skills_response(result.result)
        else:
            logger.error("Failed to generate skills")
            return None

    def _build_skills_prompt(self, messages: list[Message]) -> str:
        available_skills = self.load_all_skills()

        prompt = """You are analyzing a completed task session to identify reusable skills that were performed.
Your goal is to extract skill-based learnings that can be applied to similar tasks in the future.

A "skill" is a reusable pattern or technique for accomplishing a specific type of task. For example:
- "browser_magazine_downloads" - handling browser-based downloads with token limits
- "api_data_extraction" - extracting and transforming data from APIs
- "file_processing" - processing and organizing files in specific formats

=== AVAILABLE SKILLS ===
"""

        if available_skills:
            for skill in available_skills:
                prompt += f"\n**{skill['name']}**: {skill['description']}"
        else:
            prompt += "(No existing skills)"

        prompt += "\n\n=== SESSION MESSAGES ===\n"

        for i, msg in enumerate(messages, 1):
            prompt += f"Message {i}: {msg.render()}\n"

        prompt += """

Please analyze the session and identify ALL reusable skills that were performed:

1. **Identify** all distinct skills or techniques used in this session (can be multiple)
2. **Determine** if each skill matches an existing skill or is a new skill
3. **For existing skills**: Extract any NEW insights that should be added to that skill
4. **For new skills**: Define the skill name, description, and key learnings

For each skill you identify, provide:
- **skill_name**: A short, descriptive snake_case name (use existing name if it matches)
- **description**: One-line description of what this skill helps accomplish
- **content**: The markdown-formatted learning content (for new skills, the complete content;
  for existing skills, only the NEW insights to merge)
- **is_new**: Boolean indicating if this is a new skill (true) or an update to existing (false)

IMPORTANT:
- Generate multiple skills if the session involved multiple distinct techniques or patterns
- Each skill should focus on a specific, reusable capability
- Only include skills with genuinely valuable, actionable insights
- Be concise and specific for each skill"""

        return prompt

    async def _parse_skills_response(self, response: str) -> list[dict[str, Any]] | None:
        try:
            parsed = await parse_from_type(response, SkillsResponse)
            return [skill.model_dump() for skill in parsed.skills]
        except Exception as e:
            logger.error(f"Failed to parse skills response: {e}")
            return None

    async def _save_skills(self, skills: list[dict]) -> None:
        for skill in skills:
            skill_name = skill.get("skill_name")
            description = skill.get("description")
            content = skill.get("content")
            is_new = skill.get("is_new", False)

            if not skill_name or not description or not content:
                logger.warning(f"Skipping incomplete skill: {skill}")
                continue

            skill_file = self.skills_dir / f"{skill_name}.md"

            if is_new or not skill_file.exists():
                full_content = f"---\nname: {skill_name}\ndescription: {description}\n---\n\n{content}"
                operation = "Created new"
            else:
                existing_content = skill_file.read_text(encoding="utf-8")
                full_content = self._merge_skill_content(existing_content, content, description)
                operation = "Updated"

            try:
                skill_file.write_text(full_content, encoding="utf-8")
                logger.info(f"{operation} skill '{skill_name}' at {skill_file}")
            except Exception as e:
                logger.error(f"Failed to save skill '{skill_name}': {e}")

    def _merge_skill_content(self, existing: str, new_content: str, new_description: str) -> str:
        import re

        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", existing, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            existing_body = frontmatter_match.group(2)

            description_match = re.search(r"^description:\s*(.*)$", frontmatter, re.MULTILINE)
            if description_match and new_description:
                frontmatter = re.sub(
                    r"^description:.*$", f"description: {new_description}", frontmatter, flags=re.MULTILINE
                )

            merged_body = f"{existing_body.strip()}\n\n{new_content.strip()}"
            return f"---\n{frontmatter}\n---\n\n{merged_body}"
        else:
            return f"{existing.strip()}\n\n{new_content.strip()}"

    def load_all_skills(self) -> list[dict]:
        import re

        skills = []

        if not self.skills_dir.exists():
            return skills

        for skill_file in self.skills_dir.glob("*.md"):
            try:
                content = skill_file.read_text(encoding="utf-8")
                frontmatter_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)

                if frontmatter_match:
                    frontmatter = frontmatter_match.group(1)
                    name_match = re.search(r"^name:\s*(.*)$", frontmatter, re.MULTILINE)
                    desc_match = re.search(r"^description:\s*(.*)$", frontmatter, re.MULTILINE)

                    if name_match and desc_match:
                        skills.append(
                            {
                                "name": name_match.group(1).strip(),
                                "description": desc_match.group(1).strip(),
                                "file": skill_file.name,
                            }
                        )
            except Exception as e:
                logger.error(f"Failed to load skill from {skill_file}: {e}")

        return skills
