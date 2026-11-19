"""Unit tests for RepoPulse repository and profile health analyzer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from repopulse.analyzer import (
    analyze_profile,
    analyze_repository,
    compute_language_percentages,
    is_descriptive_commit_message,
)
from repopulse.models import CommitInfo, RepoData

FIXED_NOW = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)


def _make_complete_repo() -> RepoData:
    """Return a mock repository that satisfies every health criterion."""
    readme_text = (
        "# Awesome Project\n\n"
        "Awesome Project, GitHub depolarının bakım kalitesini ve kod sağlığını ölçmek için "
        "geliştirilmiş açık kaynaklı bir Python komut satırı aracıdır.\n\n"
        "## Kurulum\n\n"
        "```bash\npip install awesome-project\n```\n\n"
        "## Kullanım\n\n"
        "```bash\nawesome-project check owner/repo\n```\n\n"
        "## Katkıda Bulunma\n\n"
        "Pull request ve issue bildirimleri memnuniyetle karşılanır.\n"
    )
    return RepoData(
        owner="octocat",
        name="awesome-project",
        full_name="octocat/awesome-project",
        html_url="https://github.com/octocat/awesome-project",
        description="Modüler ve hızlı GitHub repo sağlık denetçisi CLI aracı.",
        topics=["python", "cli", "github-api", "developer-tools"],
        stargazers_count=42,
        forks_count=8,
        open_issues_count=3,
        has_issues=True,
        archived=False,
        license_name="MIT",
        pushed_at=FIXED_NOW - timedelta(days=2),
        root_files=[
            "README.md",
            "LICENSE",
            ".gitignore",
            "pyproject.toml",
            "requirements.txt",
            "CONTRIBUTING.md",
        ],
        readme_content=readme_text,
        languages={"Python": 18000, "Shell": 2000},
        commits=[
            CommitInfo(
                sha="a1b2c3d",
                message="feat(cli): add markdown export option for repo reports",
                author="Octocat",
                date=FIXED_NOW - timedelta(days=2),
            ),
            CommitInfo(
                sha="e4f5g6h",
                message="fix(client): handle HTTP 403 rate limit reset header gracefully",
                author="Octocat",
                date=FIXED_NOW - timedelta(days=5),
            ),
            CommitInfo(
                sha="i7j8k9l",
                message="test(analyzer): add coverage for documentation and commit scoring",
                author="Octocat",
                date=FIXED_NOW - timedelta(days=9),
            ),
        ],
    )


def test_complete_repo_achieves_perfect_score() -> None:
    """An exemplary repository should score 100/100 with grade A+ and no recommendations."""
    repo = _make_complete_repo()
    report = analyze_repository(repo, now=FIXED_NOW)

    assert report.total_score == 100
    assert report.max_score == 100
    assert report.grade == "A+"
    assert report.recommendations == []

    scores_by_category = {cat.name: (cat.score, cat.max_score) for cat in report.categories}
    assert scores_by_category == {
        "Dokümantasyon": (35, 35),
        "Standart Dosyalar": (25, 25),
        "Aktivite & Commit Kalitesi": (25, 25),
        "Bakım & Görünürlük": (15, 15),
    }
    assert report.language_percentages == {"Python": 90.0, "Shell": 10.0}


def test_weak_documentation_repo_loses_doc_points_and_generates_tips() -> None:
    """A repo missing README, description, and topics should score 0/35 in Documentation."""
    repo = _make_complete_repo().model_copy(
        update={
            "name": "undocumented-repo",
            "full_name": "octocat/undocumented-repo",
            "description": None,
            "topics": [],
            "root_files": ["LICENSE", ".gitignore", "pyproject.toml"],
            "readme_content": None,
        }
    )

    report = analyze_repository(repo, now=FIXED_NOW)
    doc_category = next(cat for cat in report.categories if cat.name == "Dokümantasyon")

    assert doc_category.score == 0
    assert doc_category.max_score == 35
    assert report.total_score == 65
    assert report.grade == "C"

    joined_recs = " ".join(report.recommendations).lower()
    assert "readme.md" in joined_recs
    assert "description" in joined_recs or "açıklama" in joined_recs
    assert "topics" in joined_recs or "etiket" in joined_recs


def test_short_unstructured_readme_gets_partial_doc_score() -> None:
    """A repo with a very short README lacking headings should lose structure points."""
    repo = _make_complete_repo().model_copy(
        update={
            "readme_content": "Kısa bir proje notu.",
        }
    )

    report = analyze_repository(repo, now=FIXED_NOW)
    doc_category = next(cat for cat in report.categories if cat.name == "Dokümantasyon")

    # 15 (README exists) + 0 (length & headings) + 5 (description) + 5 (topics) = 25
    assert doc_category.score == 25
    assert any("çok kısa" in rec.lower() for rec in report.recommendations)
    assert any("başlık" in rec.lower() for rec in report.recommendations)


def test_poor_commit_messages_penalized_with_actionable_recommendation() -> None:
    """Single-word or short commit messages ('update', 'fix', 'test') must score 0/15."""
    bad_commits = [
        CommitInfo(sha="1111111", message="update", date=FIXED_NOW - timedelta(days=1)),
        CommitInfo(sha="2222222", message="fix", date=FIXED_NOW - timedelta(days=2)),
        CommitInfo(sha="3333333", message="test", date=FIXED_NOW - timedelta(days=3)),
        CommitInfo(sha="4444444", message="wip", date=FIXED_NOW - timedelta(days=4)),
        CommitInfo(sha="5555555", message="fix bug", date=FIXED_NOW - timedelta(days=5)),
        CommitInfo(sha="6666666", message="update fix test", date=FIXED_NOW - timedelta(days=6)),
    ]
    repo = _make_complete_repo().model_copy(update={"commits": bad_commits})

    report = analyze_repository(repo, now=FIXED_NOW)
    activity_category = next(
        cat for cat in report.categories if cat.name == "Aktivite & Commit Kalitesi"
    )

    # Recency is recent (10/10), commit quality is 0/15
    assert activity_category.score == 10
    assert activity_category.max_score == 25
    assert report.total_score == 85
    assert any("commit" in rec.lower() for rec in report.recommendations)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("feat: add repository health scoring engine", True),
        ("fix(api): handle empty repository 409 conflict", True),
        ("Add unit tests for documentation analyzer", True),
        ("update", False),
        ("fix", False),
        ("test", False),
        ("short msg", False),
        ("update fix", False),
        ("", False),
    ],
)
def test_is_descriptive_commit_message(message: str, expected: bool) -> None:
    """Validate commit descriptiveness heuristics across good and weak examples."""
    assert is_descriptive_commit_message(message) is expected


def test_stale_archived_repo_missing_standard_files() -> None:
    """Missing LICENSE/.gitignore/config and stale archived status should sharply reduce score."""
    repo = RepoData(
        owner="octocat",
        name="old-script",
        full_name="octocat/old-script",
        description=None,
        topics=[],
        stargazers_count=0,
        forks_count=0,
        open_issues_count=0,
        has_issues=False,
        archived=True,
        license_name=None,
        pushed_at=FIXED_NOW - timedelta(days=500),
        root_files=["script.py"],
        readme_content=None,
        languages={},
        commits=[],
    )

    report = analyze_repository(repo, now=FIXED_NOW)
    assert report.total_score <= 10
    assert report.grade == "F"
    assert len(report.recommendations) >= 6


def test_analyze_profile_aggregates_scores_and_languages() -> None:
    """Profile aggregation should compute average score, best/weakest repo, and top languages."""
    good_repo = _make_complete_repo()
    weak_repo = _make_complete_repo().model_copy(
        update={
            "name": "tiny-repo",
            "full_name": "octocat/tiny-repo",
            "description": None,
            "topics": [],
            "readme_content": None,
            "root_files": ["main.js"],
            "license_name": None,
            "languages": {"JavaScript": 20000},
        }
    )

    good_report = analyze_repository(good_repo, now=FIXED_NOW)
    weak_report = analyze_repository(weak_repo, now=FIXED_NOW)

    summary = analyze_profile(
        "octocat",
        [good_report, weak_report],
        repos_data=[good_repo, weak_repo],
        now=FIXED_NOW,
    )

    assert summary.username == "octocat"
    assert summary.total_repos_analyzed == 2
    assert summary.average_score == round((good_report.total_score + weak_report.total_score) / 2, 1)
    assert summary.best_repo == f"octocat/awesome-project ({good_report.total_score}/100)"
    assert summary.weakest_repo == f"octocat/tiny-repo ({weak_report.total_score}/100)"
    assert summary.top_languages == {"JavaScript": 50.0, "Python": 45.0, "Shell": 5.0}


def test_compute_language_percentages_empty() -> None:
    """Empty language maps should return an empty dictionary."""
    assert compute_language_percentages({}) == {}
