"""
CQRS Command and Query Handlers

Mediator pattern for handling commands and queries.
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Dict, Type, Any
import logging

from app.cqrs.commands import Command
from app.cqrs.queries import Query
from app.core.result import Result, ok, err


logger = logging.getLogger(__name__)


TCommand = TypeVar('TCommand', bound=Command)
TQuery = TypeVar('TQuery', bound=Query)
TResult = TypeVar('TResult')


class CommandHandler(ABC, Generic[TCommand, TResult]):
    """Base command handler."""
    
    @abstractmethod
    async def handle(self, command: TCommand) -> Result[TResult, Exception]:
        """Handle command and return result."""
        pass


class QueryHandler(ABC, Generic[TQuery, TResult]):
    """Base query handler."""
    
    @abstractmethod
    async def handle(self, query: TQuery) -> Result[TResult, Exception]:
        """Handle query and return result."""
        pass


class Mediator:
    """
    Mediator for dispatching commands and queries to handlers.
    
    Implements the Mediator pattern for decoupling senders and receivers.
    """
    
    def __init__(self):
        self._command_handlers: Dict[Type[Command], CommandHandler] = {}
        self._query_handlers: Dict[Type[Query], QueryHandler] = {}
    
    def register_command_handler(
        self,
        command_type: Type[TCommand],
        handler: CommandHandler[TCommand, TResult]
    ):
        """Register command handler."""
        self._command_handlers[command_type] = handler
        logger.info(f"Registered command handler: {command_type.__name__}")
    
    def register_query_handler(
        self,
        query_type: Type[TQuery],
        handler: QueryHandler[TQuery, TResult]
    ):
        """Register query handler."""
        self._query_handlers[query_type] = handler
        logger.info(f"Registered query handler: {query_type.__name__}")
    
    async def send_command(self, command: Command) -> Result[Any, Exception]:
        """
        Send command to handler.
        
        Returns Result[T, Exception] for railway-oriented programming.
        """
        command_type = type(command)
        handler = self._command_handlers.get(command_type)
        
        if not handler:
            error_msg = f"No handler registered for command: {command_type.__name__}"
            logger.error(error_msg)
            return err(ValueError(error_msg))
        
        try:
            logger.info(f"Handling command: {command_type.__name__}")
            result = await handler.handle(command)
            
            if result.is_ok():
                logger.info(f"Command handled successfully: {command_type.__name__}")
            else:
                logger.error(f"Command failed: {command_type.__name__} - {result.error}")
            
            return result
        except Exception as e:
            logger.exception(f"Command handler error: {command_type.__name__}")
            return err(e)
    
    async def send_query(self, query: Query) -> Result[Any, Exception]:
        """
        Send query to handler.
        
        Returns Result[T, Exception] for railway-oriented programming.
        """
        query_type = type(query)
        handler = self._query_handlers.get(query_type)
        
        if not handler:
            error_msg = f"No handler registered for query: {query_type.__name__}"
            logger.error(error_msg)
            return err(ValueError(error_msg))
        
        try:
            logger.debug(f"Handling query: {query_type.__name__}")
            result = await handler.handle(query)
            
            if result.is_ok():
                logger.debug(f"Query handled successfully: {query_type.__name__}")
            else:
                logger.error(f"Query failed: {query_type.__name__} - {result.error}")
            
            return result
        except Exception as e:
            logger.exception(f"Query handler error: {query_type.__name__}")
            return err(e)


# Global mediator instance
mediator = Mediator()
