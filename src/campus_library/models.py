"""Pydantic contracts shared by the service and MCP output schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Book(Contract):
    book_id: str
    title: str
    author: str
    topics: list[str]
    copies: int = Field(ge=0)


class BookAvailability(Book):
    available_copies: int = Field(ge=0)


class SearchResult(Contract):
    query: str
    total_matches: int
    books: list[BookAvailability]


class Reservation(Contract):
    reservation_id: str
    book_id: str
    title: str
    student_id: str
    created_at: str
    status: Literal["reserved"] = "reserved"


class ReservationResult(Contract):
    reservation: Reservation
    already_reserved: bool


class WorkflowResult(Contract):
    query: str
    selection_policy: str
    steps: list[str]
    result: ReservationResult
