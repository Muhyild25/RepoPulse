"""Pydantic v2 data models for RepoPulse."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, computed_field


class CommitInfo(BaseModel):
    """GitHub commit metadata used for activity and message quality analysis."""

    sha: str = ""
    message: str
    author: str | None = None
    date: datetime | None = None


class RepoData(BaseModel):
    """Raw repository snapshot fetched from GitHub REST API v3."""

    owner: str
    name: str
    full_name: str
    html_url: str = ""
    description: str | None = None
    topics: list[str] = Field(default_factory=list)
    default_branch: str = "main"
    stargazers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    has_issues: bool = True
    archived: bool = False
    is_fork: bool = False
    license_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pushed_at: datetime | None = None
    root_files: list[str] = Field(default_factory=list)
    readme_content: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    commits: list[CommitInfo] = Field(default_factory=list)


class CategoryScore(BaseModel):
    """Score breakdown for a single health audit category."""

    name: str
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    details: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def percentage(self) -> float:
        """Return category score as a 0-100 percentage."""
        return round((self.score / self.max_score) * 100, 1)


class HealthReport(BaseModel):
    """Complete health audit report for a single repository."""

    repo_full_name: str
    html_url: str = ""
    description: str | None = None
    total_score: int = Field(ge=0, le=100)
    max_score: int = 100
    grade: str
    categories: list[CategoryScore] = Field(default_factory=list)
    language_percentages: dict[str, float] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    stargazers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProfileSummary(BaseModel):
    """Aggregated health summary across multiple repositories of a GitHub user."""

    username: str
    profile_url: str = ""
    total_repos_analyzed: int = Field(ge=0)
    average_score: float = Field(ge=0.0, le=100.0)
    grade: str
    best_repo: str | None = None
    weakest_repo: str | None = None
    top_languages: dict[str, float] = Field(default_factory=dict)
    repo_reports: list[HealthReport] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
