from pydantic import BaseModel


class AgentEvent(BaseModel):
    node_name: str
    event_type: str
    summary: str
    retry_count: int = 0

