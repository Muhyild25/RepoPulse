"""Typer CLI entry point for RepoPulse."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from repopulse.analyzer import analyze_profile, analyze_repository
from repopulse.github_client import GitHubAPIError, GitHubClient, RateLimitError, RepoNotFoundError
from repopulse.models import HealthReport, RepoData
from repopulse.reporter import (
    export_profile_summary_markdown,
    export_repo_report_markdown,
    print_profile_summary,
    print_repo_report,
)

# Ensure UTF-8 output on Windows consoles when supported
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

app = typer.Typer(
    name="repopulse",
    help="RepoPulse - GitHub Profil & Repo Sağlık Denetçisi",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _parse_repo_slug(slug: str) -> tuple[str, str]:
    """Parse 'owner/repo' (or a GitHub URL) into (owner, repo)."""
    cleaned = slug.strip().removesuffix(".git").rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    parts = [p for p in cleaned.split("/") if p]
    if len(parts) != 2:
        raise typer.BadParameter(
            "Repo adı 'owner/repo' formatında olmalıdır (örnek: Muhyild25/ProjeHub)."
        )
    return parts[0], parts[1]


def _render_error(title: str, message: str) -> None:
    console.print(Panel(message, title=f"[bold red]{title}[/bold red]", border_style="red"))


@app.command("repo")
def analyze_repo_cmd(
    repo_slug: Annotated[
        str,
        typer.Argument(help="Denetlenecek GitHub deposu (owner/repo formatında)"),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Raporu belirtilen Markdown (.md) dosyasına aktar"),
    ] = None,
    token: Annotated[
        Optional[str],
        typer.Option(
            "--token",
            "-t",
            envvar="GITHUB_TOKEN",
            help="GitHub Personal Access Token (.env üzerinden otomatik okunur)",
        ),
    ] = None,
) -> None:
    """Tek bir GitHub reposunun 100 üzerinden sağlık denetimini yapar."""
    owner, repo = _parse_repo_slug(repo_slug)

    try:
        with GitHubClient(token=token) as client:
            with console.status(f"[bold cyan]{owner}/{repo} verileri GitHub API'den alınıyor...[/bold cyan]"):
                repo_data = client.get_repo_data(owner, repo)
    except RepoNotFoundError as exc:
        _render_error("Repo Bulunamadı", str(exc))
        raise typer.Exit(code=1) from exc
    except RateLimitError as exc:
        _render_error("Rate Limit Aşıldı", str(exc))
        raise typer.Exit(code=1) from exc
    except GitHubAPIError as exc:
        _render_error("GitHub API Hatası", str(exc))
        raise typer.Exit(code=1) from exc

    report = analyze_repository(repo_data)
    print_repo_report(report, console=console)

    if output is not None:
        saved_path = export_repo_report_markdown(report, output)
        console.print(f"[bold green]Markdown raporu kaydedildi:[/bold green] {saved_path}")


@app.command("profile")
def analyze_profile_cmd(
    username: Annotated[
        str,
        typer.Argument(help="Denetlenecek GitHub kullanıcı adı"),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", min=1, max=30, help="İncelenecek maksimum repo sayısı"),
    ] = 5,
    sort: Annotated[
        str,
        typer.Option("--sort", "-s", help="Sıralama ölçütü: 'updated' (en güncel) veya 'stars' (en popüler)"),
    ] = "updated",
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Profil özetini Markdown (.md) dosyasına aktar"),
    ] = None,
    token: Annotated[
        Optional[str],
        typer.Option(
            "--token",
            "-t",
            envvar="GITHUB_TOKEN",
            help="GitHub Personal Access Token (.env üzerinden otomatik okunur)",
        ),
    ] = None,
) -> None:
    """Bir GitHub kullanıcısının herkese açık repolarını tarayıp genel profil sağlık özeti çıkarır."""
    sort_key = sort.strip().lower()
    if sort_key not in ("updated", "stars"):
        raise typer.BadParameter("--sort değeri 'updated' veya 'stars' olmalıdır.")

    clean_username = username.strip().lstrip("@")
    reports: list[HealthReport] = []
    repos_data: list[RepoData] = []

    try:
        with GitHubClient(token=token) as client:
            with console.status(f"[bold cyan]@{clean_username} repoları listeleniyor...[/bold cyan]"):
                raw_repos = client.get_user_repos(clean_username, limit=limit, sort=sort_key)

            if not raw_repos:
                console.print(
                    Panel(
                        f"@{clean_username} kullanıcısının herkese açık reposu bulunamadı.",
                        title="[bold yellow]Bilgi[/bold yellow]",
                        border_style="yellow",
                    )
                )
                return

            for idx, item in enumerate(raw_repos, start=1):
                repo_name = str(item.get("name") or "")
                owner_login = str((item.get("owner") or {}).get("login") or clean_username)
                if not repo_name:
                    continue
                with console.status(
                    f"[bold cyan]({idx}/{len(raw_repos)}) {owner_login}/{repo_name} analiz ediliyor...[/bold cyan]"
                ):
                    data = client.get_repo_data(owner_login, repo_name)
                    repos_data.append(data)
                    reports.append(analyze_repository(data))
    except RepoNotFoundError as exc:
        _render_error("Kullanıcı Bulunamadı", str(exc))
        raise typer.Exit(code=1) from exc
    except RateLimitError as exc:
        _render_error("Rate Limit Aşıldı", str(exc))
        raise typer.Exit(code=1) from exc
    except GitHubAPIError as exc:
        _render_error("GitHub API Hatası", str(exc))
        raise typer.Exit(code=1) from exc

    summary = analyze_profile(clean_username, reports, repos_data=repos_data)
    print_profile_summary(summary, console=console)

    if output is not None:
        saved_path = export_profile_summary_markdown(summary, output)
        console.print(f"[bold green]Profil Markdown raporu kaydedildi:[/bold green] {saved_path}")


if __name__ == "__main__":
    app()
