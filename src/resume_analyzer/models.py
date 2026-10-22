"""Typed contracts between pipeline stages (validated with pydantic)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]
Tier = Literal["Strong Advance", "Advance", "Hold", "Decline"]


class Requirement(BaseModel):
    id: str
    text: str
    type: Literal["must", "nice"]
    category: str = "other"


class JobSpec(BaseModel):
    title: str
    seniority: str = "unspecified"
    requirements: list[Requirement]
    inclusivity_notes: list[str] = Field(default_factory=list)


class Role(BaseModel):
    title: str
    company: str = ""
    start: str = ""
    end: str = ""
    highlights: list[str] = Field(default_factory=list)


class IntegrityFlag(BaseModel):
    type: Literal["prompt_injection", "hidden_text", "inconsistent_dates", "other"]
    detail: str


class ResumeProfile(BaseModel):
    summary: str
    skills: list[str] = Field(default_factory=list)
    experience: list[Role] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    total_years_experience: Optional[float] = None
    integrity_flags: list[IntegrityFlag] = Field(default_factory=list)


class RequirementMatch(BaseModel):
    requirement_id: str
    reasoning: str = ""
    evidence: list[str] = Field(default_factory=list)
    score: int = Field(ge=0, le=4)
    confidence: Confidence = "medium"
    verified: bool = True  # set by code, never by the model


class Evaluation(BaseModel):
    matches: list[RequirementMatch]
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verify_in_interview: list[str] = Field(default_factory=list)


class InterviewQuestion(BaseModel):
    question: str
    targets_requirement_id: str = ""
    what_good_looks_like: str = ""


class Recommendation(BaseModel):
    headline: str
    rationale: str
    interview_questions: list[InterviewQuestion] = Field(default_factory=list)
    candidate_feedback: str = ""
    alternative_roles: list[str] = Field(default_factory=list)
    onboarding_risks: list[str] = Field(default_factory=list)


class Report(BaseModel):
    candidate_ref: str
    job_title: str
    match_score: float
    tier: Tier
    knockouts: list[str]
    needs_human_review: bool
    review_reasons: list[str]
    profile: ResumeProfile
    matches: list[RequirementMatch]
    strengths: list[str]
    gaps: list[str]
    verify_in_interview: list[str]
    recommendation: Optional[Recommendation] = None
    meta: dict
