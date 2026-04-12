"""
Repository Module

Data access layer with clean interfaces.
"""
from app.repositories.base import Repository
from app.repositories.opportunity_repository import OpportunityRepository
from app.repositories.submission_repository import SubmissionRepository

__all__ = [
    "Repository",
    "OpportunityRepository",
    "SubmissionRepository",
]
