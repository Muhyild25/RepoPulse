"""GitHub REST API v3 client for RepoPulse."""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

from repopulse.models import CommitInfo, RepoData


class GitHubAPIError(Exception):
    """Base exception for GitHub API communication errors."""


class RepoNotFoundError(GitHubAPIError):
    """Raised when a requested repository or user cannot be found (HTTP 404)."""


class RateLimitError(GitHubAPIError):
    """Raised when the GitHub API rate limit is exceeded (HTTP 403/429)."""


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp returned by GitHub into a timezone-aware UTC datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


class GitHubClient:
    """Synchronous GitHub REST API v3 client backed by httpx."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None, timeout: float = 15.0) -> None:
        load_dotenv()
        resolved_token = token if token is not None else os.getenv("GITHUB_TOKEN")
        self.token = resolved_token.strip() if resolved_token else None

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RepoPulse-CLI/0.1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def _handle_error_response(self, response: httpx.Response, resource_label: str) -> None:
        """Translate GitHub HTTP error responses into actionable domain exceptions."""
        status = response.status_code
        api_message = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                api_message = str(payload.get("message", ""))
        except ValueError:
            api_message = response.text.strip()[:200]

        if status == 404:
            raise RepoNotFoundError(
                f"GitHub üzerinde bulunamadı (404): {resource_label}. "
                "Repo/kullanıcı adını kontrol edin veya reponun herkese açık (public) olduğundan emin olun."
            )

        if status == 401:
            raise GitHubAPIError(
                "GitHub kimlik doğrulaması başarısız (401). "
                ".env dosyasındaki GITHUB_TOKEN değerinin geçerli olduğunu kontrol edin."
            )

        if status in (403, 429):
            remaining = response.headers.get("X-RateLimit-Remaining")
            reset_raw = response.headers.get("X-RateLimit-Reset")
            is_rate_limited = (
                status == 429
                or remaining == "0"
                or "rate limit" in api_message.lower()
                or "secondary rate limit" in api_message.lower()
            )
            if is_rate_limited:
                reset_hint = ""
                if reset_raw and reset_raw.isdigit():
                    reset_dt = datetime.fromtimestamp(int(reset_raw), tz=timezone.utc).astimezone()
                    reset_hint = f" Limit sıfırlanma zamanı: {reset_dt.strftime('%Y-%m-%d %H:%M:%S')}."
                token_hint = (
                    " Daha yüksek istek limiti (5000/saat) için .env dosyasına GITHUB_TOKEN ekleyin."
                    if not self.token
                    else " Bir süre bekleyip tekrar deneyin."
                )
                raise RateLimitError(
                    f"GitHub API rate limit aşıldı ({status}).{reset_hint}{token_hint}"
                )
            raise GitHubAPIError(
                f"GitHub API erişim reddedildi (403): {resource_label}. Detay: {api_message or 'Yetkisiz erişim'}"
            )

        raise GitHubAPIError(
            f"GitHub API hatası ({status}) [{resource_label}]: {api_message or 'Bilinmeyen hata'}"
        )

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        resource_label: str = "",
        allow_404: bool = False,
        allow_409: bool = False,
    ) -> Any:
        """Perform a GET request against GitHub API with unified error handling."""
        label = resource_label or path
        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise GitHubAPIError(
                f"GitHub API isteği zaman aşımına uğradı: {label}. İnternet bağlantınızı kontrol edin."
            ) from exc
        except httpx.RequestError as exc:
            raise GitHubAPIError(
                f"GitHub API bağlantı hatası ({label}): {exc}"
            ) from exc

        if response.status_code == 404 and allow_404:
            return None
        if response.status_code == 409 and allow_409:
            return None

        if response.status_code >= 400:
            self._handle_error_response(response, label)

        return response.json()

    def get_repo_data(self, owner: str, repo: str) -> RepoData:
        """Fetch repository metadata, root files, README, languages, and latest 20 commits."""
        slug = f"{owner}/{repo}"
        repo_json = self._get(f"/repos/{owner}/{repo}", resource_label=slug)

        # 1. Root directory entries
        contents_json = self._get(
            f"/repos/{owner}/{repo}/contents",
            resource_label=f"{slug}/contents",
            allow_404=True,
        )
        root_files: list[str] = []
        if isinstance(contents_json, list):
            root_files = [
                str(entry["name"])
                for entry in contents_json
                if isinstance(entry, dict) and entry.get("name")
            ]

        # 2. README content
        readme_json = self._get(
            f"/repos/{owner}/{repo}/readme",
            resource_label=f"{slug}/readme",
            allow_404=True,
        )
        readme_content: str | None = None
        if isinstance(readme_json, dict) and readme_json.get("content"):
            encoding = readme_json.get("encoding", "base64")
            raw_content = str(readme_json["content"])
            if encoding == "base64":
                try:
                    readme_content = base64.b64decode(raw_content).decode("utf-8", errors="replace")
                except (ValueError, TypeError):
                    readme_content = None
            else:
                readme_content = raw_content

        # 3. Languages breakdown
        languages_json = self._get(
            f"/repos/{owner}/{repo}/languages",
            resource_label=f"{slug}/languages",
            allow_404=True,
        )
        languages: dict[str, int] = {}
        if isinstance(languages_json, dict):
            languages = {str(k): int(v) for k, v in languages_json.items() if isinstance(v, (int, float))}

        # 4. Latest 20 commits (409 is returned by GitHub when a repo has no commits yet)
        commits_json = self._get(
            f"/repos/{owner}/{repo}/commits",
            params={"per_page": 20},
            resource_label=f"{slug}/commits",
            allow_404=True,
            allow_409=True,
        )
        commits: list[CommitInfo] = []
        if isinstance(commits_json, list):
            for item in commits_json:
                if not isinstance(item, dict):
                    continue
                commit_obj = item.get("commit") or {}
                author_obj = commit_obj.get("author") or {}
                message = str(commit_obj.get("message") or "").strip()
                commits.append(
                    CommitInfo(
                        sha=str(item.get("sha") or "")[:7],
                        message=message,
                        author=author_obj.get("name"),
                        date=_parse_iso_datetime(author_obj.get("date")),
                    )
                )

        license_obj = repo_json.get("license")
        license_name: str | None = None
        if isinstance(license_obj, dict):
            spdx = license_obj.get("spdx_id")
            name = license_obj.get("name")
            if spdx and spdx != "NOASSERTION":
                license_name = str(spdx)
            elif name:
                license_name = str(name)

        owner_obj = repo_json.get("owner") or {}

        return RepoData(
            owner=str(owner_obj.get("login") or owner),
            name=str(repo_json.get("name") or repo),
            full_name=str(repo_json.get("full_name") or slug),
            html_url=str(repo_json.get("html_url") or f"https://github.com/{slug}"),
            description=repo_json.get("description"),
            topics=[str(t) for t in (repo_json.get("topics") or [])],
            default_branch=str(repo_json.get("default_branch") or "main"),
            stargazers_count=int(repo_json.get("stargazers_count") or 0),
            forks_count=int(repo_json.get("forks_count") or 0),
            open_issues_count=int(repo_json.get("open_issues_count") or 0),
            has_issues=bool(repo_json.get("has_issues", True)),
            archived=bool(repo_json.get("archived", False)),
            is_fork=bool(repo_json.get("fork", False)),
            license_name=license_name,
            created_at=_parse_iso_datetime(repo_json.get("created_at")),
            updated_at=_parse_iso_datetime(repo_json.get("updated_at")),
            pushed_at=_parse_iso_datetime(repo_json.get("pushed_at")),
            root_files=root_files,
            readme_content=readme_content,
            languages=languages,
            commits=commits,
        )

    def get_user_repos(
        self,
        username: str,
        *,
        limit: int = 5,
        sort: str = "updated",
    ) -> list[dict[str, Any]]:
        """List public repositories for a GitHub user sorted by recency or popularity."""
        if sort == "stars":
            # GitHub REST API does not natively sort /users/{user}/repos by stars,
            # so fetch up to 100 public repositories and sort client-side.
            repos = self._get(
                f"/users/{username}/repos",
                params={"type": "owner", "sort": "updated", "direction": "desc", "per_page": 100},
                resource_label=f"kullanıcı '{username}'",
            )
            if not isinstance(repos, list):
                return []
            repos.sort(
                key=lambda r: (int(r.get("stargazers_count") or 0), str(r.get("pushed_at") or "")),
                reverse=True,
            )
            return repos[:limit]

        repos = self._get(
            f"/users/{username}/repos",
            params={
                "type": "owner",
                "sort": "pushed" if sort == "pushed" else "updated",
                "direction": "desc",
                "per_page": min(max(limit, 1), 100),
            },
            resource_label=f"kullanıcı '{username}'",
        )
        if not isinstance(repos, list):
            return []
        return repos[:limit]
