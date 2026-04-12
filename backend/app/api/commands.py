from fastapi import APIRouter

from app.core.assistant_commands import execute_assistant_command
from app.schemas.command import CommandExecuteRequest, CommandExecuteResponse

router = APIRouter(prefix="/commands", tags=["commands"])


@router.post("/execute", response_model=CommandExecuteResponse)
async def execute_command(payload: CommandExecuteRequest) -> CommandExecuteResponse:
    text = await execute_assistant_command(payload.text)
    return CommandExecuteResponse(text=text)
