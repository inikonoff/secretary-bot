"""JSON contracts for the interview model and the final TZ model (AI Specification v1.1, §13 and §27)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProjectContext(BaseModel):
    summary: str = Field(default="", max_length=800)
    goal: list[str] = Field(default_factory=list, max_length=12)
    users: list[str] = Field(default_factory=list, max_length=8)
    features: list[str] = Field(default_factory=list, max_length=16)
    scenarios: list[str] = Field(default_factory=list, max_length=8)
    business_rules: list[str] = Field(default_factory=list, max_length=10)
    integrations: list[str] = Field(default_factory=list, max_length=8)
    data: list[str] = Field(default_factory=list, max_length=8)
    roles: list[str] = Field(default_factory=list, max_length=8)
    constraints: list[str] = Field(default_factory=list, max_length=8)
    recommendations: list[str] = Field(default_factory=list, max_length=8)
    to_clarify: list[str] = Field(default_factory=list, max_length=8)


class QuestionInfo(BaseModel):
    topic: str = ""
    importance: Literal["critical", "useful", "optional"] = "useful"


class InterviewMeta(BaseModel):
    clarifying_questions_count: int = 0
    add_information_count: int = 0


class InterviewResult(BaseModel):
    action: Literal["ask", "understanding", "wait_input", "error", "out_of_scope"]
    language: str = Field(default="ru", max_length=8)
    client_message: str = Field(max_length=1500)
    project_context: ProjectContext = Field(default_factory=ProjectContext)
    question: Optional[QuestionInfo] = None
    interview: InterviewMeta = Field(default_factory=InterviewMeta)


class FinalTZResult(BaseModel):
    project_title: str
    client_understanding: str
    technical_specification_markdown: str
    to_clarify: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    technical_stack: list[str] = Field(default_factory=list)
    paid_dependencies: list[str] = Field(default_factory=list)


class DeadlineParseResult(BaseModel):
    deadline_text: str


class RevisionResult(BaseModel):
    language: str = "ru"
    client_message: str
    ai_summary: str
