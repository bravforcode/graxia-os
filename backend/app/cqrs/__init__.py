"""
CQRS Module

Command Query Responsibility Segregation implementation.
"""
from app.cqrs.commands import *
from app.cqrs.queries import *
from app.cqrs.handlers import mediator, CommandHandler, QueryHandler

__all__ = [
    "mediator",
    "CommandHandler",
    "QueryHandler",
]
