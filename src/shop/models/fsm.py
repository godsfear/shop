from pydantic import BaseModel


class FSMState(BaseModel):
    state: str
    available: list[str] = []
