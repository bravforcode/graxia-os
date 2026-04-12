from pydantic import BaseModel


class CommandExecuteRequest(BaseModel):
    text: str


class CommandExecuteResponse(BaseModel):
    text: str
