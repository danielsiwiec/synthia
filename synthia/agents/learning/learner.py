from collections import defaultdict
from pathlib import Path
from typing import Any

from claude_agent_sdk import Message, ResultMessage
from loguru import logger
from pydantic import BaseModel

from synthia.agents.claude import run_for_result
from synthia.helpers.pubsub import pubsub
from synthia.output import parse_from_type
from synthia.service.models import TaskCompletion

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
            skills_dir = Path(__file__).parent.parent.parent.parent / "claude_sessions" / ".claude" / "skills"
        self.skills_dir = skills_dir
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.sessions = defaultdict(list)
        pubsub.subscribe(Message, self.process_message)
        pubsub.subscribe(TaskCompletion, self._on_task_completion)

    async def process_message(self, message: Message) -> None:
        # skip ResultMessage, as it's just a duplication
        if not isinstance(message, ResultMessage):
            self.sessions[message.session_id].append(message)

    async def _on_task_completion(self, task_completion: TaskCompletion) -> None:
        session_id = task_completion.session_id

        if session_id in self.sessions:
            await self.process_completed_task(session_id)

    async def process_completed_task(self, session_id: str) -> None:
        messages = self.sessions[session_id]
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

A "skill" is a reusable pattern or technique for accomplishing a specific type of task. Skills are stored in the
Claude Agent SDK format as SKILL.md files that Claude autonomously invokes when relevant.

=== AVAILABLE SKILLS ===
"""

        if available_skills:
            for skill in available_skills:
                prompt += f"\n**{skill['name']}**: {skill['description']}"
        else:
            prompt += "(No existing skills)"

        prompt += "\n\n=== SESSION MESSAGES ===\n"

        for i, msg in enumerate(messages, 1):
            prompt += f"Message {i}: {msg}\n"

        prompt += """

Please analyze the session and identify ALL reusable skills that were performed:

1. **Identify** all distinct skills or techniques used in this session (can be multiple)
2. **Determine** if each skill matches an existing skill or is a new skill
3. **For existing skills**: Extract any NEW insights that should be added to that skill
4. **For new skills**: Define the skill name, description, and key learnings

For each skill you identify, provide:
- **skill_name**: A descriptive name following these STRICT requirements:
  * Use gerund form (verb + -ing): e.g., "processing-pdfs", "analyzing-data", "managing-apis"
  * Only lowercase letters, numbers, and hyphens (no underscores, no uppercase)
  * Maximum 64 characters
  * Be specific and action-oriented
  * Use existing name if updating an existing skill
- **description**: One-line description (max 1024 characters) that articulates:
  * What the skill does (functionality)
  * When to use it (appropriate use cases)
  * Must be non-empty and specific
- **content**: The markdown-formatted learning content:
  * For new skills: Complete instructions (keep under 500 lines)
  * For existing skills: Only NEW insights to merge
  * Act as a concise overview that points to detailed materials as needed
  * Use progressive disclosure pattern
- **is_new**: Boolean indicating if this is a new skill (true) or an update to existing (false)

IMPORTANT:
- Generate multiple skills if the session involved multiple distinct techniques or patterns
- Each skill should focus on a specific, reusable capability
- Only include skills with genuinely valuable, actionable insights
- Skill names MUST use hyphens (not underscores) and be all lowercase
- Keep content concise and focused (under 500 lines per skill)"""

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

            normalized_name = self._normalize_skill_name(skill_name)
            if not self._validate_skill_name(normalized_name):
                logger.warning(f"Skipping skill with invalid name: {skill_name}")
                continue

            skill_dir = self.skills_dir / normalized_name
            skill_file = skill_dir / "SKILL.md"

            if is_new or not skill_file.exists():
                full_content = f"---\nname: {normalized_name}\ndescription: {description}\n---\n\n{content}"
                operation = "Created new"
                skill_dir.mkdir(parents=True, exist_ok=True)
            else:
                existing_content = skill_file.read_text(encoding="utf-8")
                full_content = self._merge_skill_content(existing_content, content, description)
                operation = "Updated"

            try:
                skill_file.write_text(full_content, encoding="utf-8")
                logger.info(f"{operation} skill '{normalized_name}' at {skill_file}")
            except Exception as e:
                logger.error(f"Failed to save skill '{normalized_name}': {e}")

    def _normalize_skill_name(self, name: str) -> str:
        import re

        normalized = name.lower()
        normalized = re.sub(r"[^a-z0-9-]", "-", normalized)
        normalized = re.sub(r"-+", "-", normalized)
        normalized = normalized.strip("-")
        return normalized[:64]

    def _validate_skill_name(self, name: str) -> bool:
        import re

        if not name or len(name) > 64:
            return False
        if not re.match(r"^[a-z0-9-]+$", name):
            return False
        if "anthropic" in name or "claude" in name:
            return False
        if "<" in name or ">" in name:
            return False
        return True

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

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

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
                                "file": skill_dir.name,
                            }
                        )
            except Exception as e:
                logger.error(f"Failed to load skill from {skill_file}: {e}")

        return skills
