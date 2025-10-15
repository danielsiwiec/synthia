from collections import defaultdict
from pathlib import Path

from loguru import logger

from daimos.agents.claude import Message, run_for_result
from daimos.helpers.pubsub import pubsub
from daimos.service.models import TaskCompletion


class Learner:
    def __init__(self, learning_dir: Path | None = None):
        if learning_dir is None:
            learning_dir = Path(__file__).parent
        self.learning_dir = learning_dir
        self.learning_dir.mkdir(exist_ok=True)
        self.sessions = defaultdict(list)
        pubsub.subscribe(TaskCompletion, self._on_task_completion)

    async def process_message(self, message: Message) -> None:
        session_id = message.session_id
        self.sessions[session_id].append(message)

    async def _on_task_completion(self, task_completion: TaskCompletion) -> None:
        session_id = task_completion.session_id
        agent_name = task_completion.agent_name

        if session_id in self.sessions:
            messages = self.sessions[session_id]
            await self._process_completed_task(session_id, messages, agent_name)

    async def _process_completed_task(self, session_id: str, messages: list[Message], agent_name: str | None) -> None:
        await self.process_completed_task(session_id, messages, agent_name)

    async def process_completed_task(
        self, session_id: str, messages: list[Message], agent_name: str | None = None
    ) -> None:
        if not agent_name:
            logger.debug(f"No agent name provided for session {session_id}, skipping learning")
            return

        if not messages:
            logger.debug(f"No messages for session {session_id}, skipping learning")
            return

        learning_content = await self._generate_learning(messages, agent_name)
        if learning_content:
            await self._save_learning(agent_name, learning_content)

    async def _generate_learning(self, messages: list[Message], agent_name: str) -> str | None:
        analysis_prompt = self._build_learning_prompt(messages, agent_name)

        logger.debug(f"Generating learning for agent {agent_name}")

        result = await run_for_result(analysis_prompt)
        if result and result.success:
            return result.result
        else:
            logger.error(f"Failed to generate learning for agent {agent_name}")
            return None

    def _build_learning_prompt(self, messages: list[Message], agent_name: str) -> str:
        agent_prompt = self._load_agent_prompt(agent_name)
        current_learnings = self.load_learnings(agent_name)

        prompt = f"""You are analyzing a completed task session for the agent "{agent_name}".
Your goal is to assess the current agent instructions and learnings, then regenerate the learnings
to contain only a minimal set of helpful, additional information that is not already covered in the
agent's prompt file.

=== CURRENT AGENT INSTRUCTIONS ===
{agent_prompt if agent_prompt else "(No agent instructions found)"}

=== CURRENT LEARNINGS ===
{current_learnings if current_learnings else "(No previous learnings)"}

=== SESSION MESSAGES ===
"""

        for i, msg in enumerate(messages, 1):
            prompt += f"Message {i}: {msg.render()}\n"

        prompt += """

Please analyze the session and:

1. **Review** the current agent instructions and existing learnings
2. **Identify** what information is already covered in the agent's prompt
3. **Extract** only NEW insights from this session that are NOT redundant with the agent
   instructions or existing learnings
4. **Regenerate** the complete learnings document that includes:
   - Any valuable insights from previous learnings that are still relevant and not in the
     agent prompt
   - New insights from this session that add value beyond what's already documented

Focus on creating a minimal, non-redundant set of learnings. Avoid repeating information
that's already in the agent's instructions.

Structure your response as a clean markdown document. Be concise and actionable.
Only include information that genuinely adds value beyond the agent's existing instructions."""

        return prompt

    async def _save_learning(self, agent_name: str, learning_content: str) -> None:
        learning_file = self.learning_dir / f"{agent_name}.md"

        try:
            learning_file.write_text(learning_content, encoding="utf-8")
            logger.info(f"Saved learning for agent {agent_name} to {learning_file}")
        except Exception as e:
            logger.error(f"Failed to save learning for agent {agent_name}: {e}")

    def load_learnings(self, agent_name: str) -> str:
        learning_file = self.learning_dir / f"{agent_name}.md"

        if not learning_file.exists():
            return ""

        try:
            return learning_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load learnings for agent {agent_name}: {e}")
            return ""

    def _load_agent_prompt(self, agent_name: str) -> str:
        catalog_dir = Path(__file__).parent.parent / "catalog"
        agent_file = catalog_dir / f"{agent_name}.md"

        if not agent_file.exists():
            return ""

        try:
            return agent_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load agent prompt for {agent_name}: {e}")
            return ""
