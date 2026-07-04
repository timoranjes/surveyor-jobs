"""Pydantic models for API request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ── Jobs ──

class JobCreate(BaseModel):
    title: str
    company: str
    discipline: str = "other"
    location: str = "Hong Kong"
    salary_range: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    posted_date: Optional[str] = None
    closing_date: Optional[str] = None
    fresh_grad_friendly: bool = True
    experience_level: str = "entry"

class JobResponse(BaseModel):
    id: int
    title: str
    company: str
    discipline: str
    location: str
    salary_range: Optional[str]
    description: Optional[str]
    requirements: Optional[str]
    url: Optional[str]
    source: Optional[str]
    posted_date: Optional[str]
    closing_date: Optional[str]
    fresh_grad_friendly: bool
    experience_level: str
    created_at: str
    application_status: Optional[str] = None  # joined from applications

class JobFilter(BaseModel):
    discipline: Optional[str] = None
    fresh_grad_only: bool = True
    status: Optional[str] = None  # filter by application status
    search: Optional[str] = None  # text search


# ── Applications ──

class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    cover_letter: Optional[str] = None
    applied_date: Optional[str] = None
    follow_up_date: Optional[str] = None

class ApplicationResponse(BaseModel):
    id: int
    job_id: int
    status: str
    applied_date: Optional[str]
    notes: Optional[str]
    cover_letter: Optional[str]
    follow_up_date: Optional[str]
    created_at: str
    job: Optional[JobResponse] = None


# ── CV ──

class CVUpload(BaseModel):
    full_text: str

class CVAnalysisRequest(BaseModel):
    cv_id: Optional[int] = None

class CVMatchResponse(BaseModel):
    job_id: int
    job_title: str
    company: str
    match_score: float
    strengths: List[str]
    gaps: List[str]
    suggestions: List[str]
    tailored_cv: Optional[str] = None
    cover_letter: Optional[str] = None
    interview_questions: Optional[List[str]] = None

class SkillGapResponse(BaseModel):
    missing_skills: List[str]
    frequency: dict  # skill → count across jobs
    recommended_courses: List[str]


# ── Companies ──

class CompanyProfile(BaseModel):
    company_name: str
    overview: Optional[str] = None
    hk_projects: Optional[str] = None
    reputation_notes: Optional[str] = None
    glassdoor_rating: Optional[float] = None


# ── Analytics ──

class AnalyticsResponse(BaseModel):
    total_jobs: int
    by_discipline: dict
    by_status: dict
    response_rate: float
    avg_match_score: float
    salary_benchmarks: dict
    recent_activity: List[dict]
