from pydantic import BaseModel


class AgentSelection(BaseModel):
    agent_name: str | None = None
