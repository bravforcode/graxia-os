"""
Result Type Pattern

Railway-oriented programming for clean error handling.
Inspired by Rust's Result<T, E> and functional programming.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar, Union

T = TypeVar('T')
E = TypeVar('E')
U = TypeVar('U')


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Success result containing a value."""
    value: T
    
    def is_ok(self) -> bool:
        return True
    
    def is_err(self) -> bool:
        return False
    
    def unwrap(self) -> T:
        """Get the value (safe for Ok)."""
        return self.value
    
    def unwrap_or(self, default: T) -> T:
        """Get the value or default."""
        return self.value
    
    def map(self, func: Callable[[T], U]) -> 'Result[U, E]':
        """Transform the value if Ok."""
        try:
            return Ok(func(self.value))
        except Exception as e:
            return Err(e)
    
    def and_then(self, func: Callable[[T], 'Result[U, E]']) -> 'Result[U, E]':
        """Chain operations (flatMap)."""
        try:
            return func(self.value)
        except Exception as e:
            return Err(e)


@dataclass(frozen=True)
class Err(Generic[E]):
    """Error result containing an error."""
    error: E
    
    def is_ok(self) -> bool:
        return False
    
    def is_err(self) -> bool:
        return True
    
    def unwrap(self) -> T:
        """Get the value (raises for Err)."""
        raise ValueError(f"Called unwrap on Err: {self.error}")
    
    def unwrap_or(self, default: T) -> T:
        """Get the value or default."""
        return default
    
    def map(self, func: Callable[[T], U]) -> 'Result[U, E]':
        """Transform the value if Ok (no-op for Err)."""
        return self
    
    def and_then(self, func: Callable[[T], 'Result[U, E]']) -> 'Result[U, E]':
        """Chain operations (no-op for Err)."""
        return self


# Type alias for Result
Result = Union[Ok[T], Err[E]]


def safe_execute(func: Callable[[], T]) -> Result[T, Exception]:
    """
    Execute a function and return Result.
    
    Example:
        result = safe_execute(lambda: risky_operation())
        if result.is_ok():
            value = result.unwrap()
        else:
            error = result.error
    """
    try:
        return Ok(func())
    except Exception as e:
        return Err(e)


async def safe_execute_async(func: Callable[[], T]) -> Result[T, Exception]:
    """
    Execute an async function and return Result.
    
    Example:
        result = await safe_execute_async(lambda: async_operation())
        if result.is_ok():
            value = result.unwrap()
    """
    try:
        return Ok(await func())
    except Exception as e:
        return Err(e)


# Convenience functions
def ok(value: T) -> Ok[T]:
    """Create an Ok result."""
    return Ok(value)


def err(error: E) -> Err[E]:
    """Create an Err result."""
    return Err(error)
