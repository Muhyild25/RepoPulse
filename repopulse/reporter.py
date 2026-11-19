"""Rich terminal rendering and Markdown report export for RepoPulse."""

from __future__ import annotations

from pathlib import Path

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from repopulse.models import HealthReport, ProfileSummary


def _score_color(score: float) -> str:
    """Return a Rich color name matching the health score tier."""
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"


def _progress_bar(percentage: float, width: int = 14) -> str:
    """Render an ASCII/block progress bar safe across terminals."""
    filled = round((max(0.0, min(100.0, percentage)) / 100.0) * width)
    return "#" * filled + "-" * (width - filled)


def print_repo_report(report: HealthReport, console: Console | None = None) -> None:
    """Render a colorful health score card, category table, languages, and tips."""
    out = console or Console()
    color = _score_color(report.total_score)

    # 1. Header Score Card
    header_text = Text()
    header_text.append(f"{report.repo_full_name}\n", style="bold white")
    if report.description:
        header_text.append(f"{report.description}\n", style="dim")
    if report.html_url:
        header_text.append(f"{report.html_url}\n", style="cyan underline")
    header_text.append("\nSağlık Skoru: ", style="bold")
    header_text.append(
        f"{report.total_score}/{report.max_score}  (Not: {report.grade})",
        style=f"bold {color}",
    )
    header_text.append(
        f"\nYıldız: {report.stargazers_count}  |  Fork: {report.forks_count}  |  Açık Issue: {report.open_issues_count}",
        style="dim white",
    )

    out.print()
    out.print(
        Panel(
            header_text,
            title="[bold cyan]RepoPulse Sağlık Kartı[/bold cyan]",
            border_style=color,
            padding=(1, 2),
        )
    )

    # 2. Category Breakdown Table
    cat_table = Table(
        title="Kategori Bazlı Puan Dağılımı",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=True,
        expand=True,
    )
    cat_table.add_column("Kategori", style="bold white", ratio=2)
    cat_table.add_column("Puan", justify="center", ratio=1)
    cat_table.add_column("Oran", justify="center", ratio=2)
    cat_table.add_column("Değerlendirme Detayları", ratio=4)

    for cat in report.categories:
        cat_color = _score_color(cat.percentage)
        bar = _progress_bar(cat.percentage, width=10)
        cat_table.add_row(
            cat.name,
            f"[{cat_color}]{cat.score} / {cat.max_score}[/{cat_color}]",
            f"[{cat_color}]{bar} %{cat.percentage:.1f}[/{cat_color}]",
            "\n".join(f"- {escape(d)}" for d in cat.details),
        )

    out.print(cat_table)

    # 3. Language Distribution
    lang_table = Table(
        title="Dil Dağılımı",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        expand=True,
    )
    lang_table.add_column("Dil", style="bold white", ratio=2)
    lang_table.add_column("Yüzde", justify="right", ratio=1)
    lang_table.add_column("Dağılım", ratio=4)

    if report.language_percentages:
        for lang, pct in list(report.language_percentages.items())[:8]:
            lang_table.add_row(
                escape(lang),
                f"%{pct:.1f}",
                f"[cyan]{_progress_bar(pct, width=24)}[/cyan]",
            )
    else:
        lang_table.add_row("Tespit edilemedi", "-", "[dim]Kaynak kod verisi yok[/dim]")

    out.print(lang_table)

    # 4. Recommendations
    if report.recommendations:
        rec_lines = "\n".join(
            f"[bold yellow]{idx}.[/bold yellow] {escape(rec)}"
            for idx, rec in enumerate(report.recommendations, start=1)
        )
        out.print(
            Panel(
                rec_lines,
                title="[bold yellow]İyileştirme Önerileri[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            )
        )
    else:
        out.print(
            Panel(
                "[bold green]Tebrikler! Bu repo tüm sağlık kriterlerini karşılıyor.[/bold green]",
                title="[bold green]İyileştirme Önerileri[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )
    out.print()


def print_profile_summary(summary: ProfileSummary, console: Console | None = None) -> None:
    """Render a Rich terminal summary for a GitHub user's repositories."""
    out = console or Console()
    color = _score_color(summary.average_score)

    header = Text()
    header.append(f"@{summary.username}\n", style="bold white")
    if summary.profile_url:
        header.append(f"{summary.profile_url}\n", style="cyan underline")
    header.append("\nOrtalama Sağlık Skoru: ", style="bold")
    header.append(
        f"{summary.average_score:.1f}/100  (Not: {summary.grade})",
        style=f"bold {color}",
    )
    header.append(f"\nİncelenen Repo Sayısı: {summary.total_repos_analyzed}", style="white")
    if summary.best_repo:
        header.append(f"\nEn Sağlıklı Repo: {summary.best_repo}", style="green")
    if summary.weakest_repo:
        header.append(f"\nEn Çok Geliştirilebilir Repo: {summary.weakest_repo}", style="yellow")

    out.print()
    out.print(
        Panel(
            header,
            title="[bold cyan]RepoPulse Profil Sağlık Özeti[/bold cyan]",
            border_style=color,
            padding=(1, 2),
        )
    )

    if summary.repo_reports:
        repo_table = Table(
            title="İncelenen Repolar",
            box=box.ROUNDED,
            header_style="bold cyan",
            expand=True,
        )
        repo_table.add_column("Repo", style="bold white", ratio=3)
        repo_table.add_column("Skor", justify="center", ratio=1)
        repo_table.add_column("Not", justify="center", ratio=1)
        repo_table.add_column("Yıldız", justify="right", ratio=1)
        repo_table.add_column("Ana Dil", ratio=2)
        repo_table.add_column("Öneri Sayısı", justify="center", ratio=1)

        for r in summary.repo_reports:
            r_color = _score_color(r.total_score)
            top_lang = next(iter(r.language_percentages.keys()), "-")
            repo_table.add_row(
                escape(r.repo_full_name),
                f"[{r_color}]{r.total_score}/100[/{r_color}]",
                f"[bold {r_color}]{r.grade}[/bold {r_color}]",
                str(r.stargazers_count),
                escape(top_lang),
                str(len(r.recommendations)),
            )
        out.print(repo_table)

    if summary.top_languages:
        lang_table = Table(
            title="Profil Genelinde Dil Dağılımı",
            box=box.SIMPLE_HEAVY,
            header_style="bold cyan",
            expand=True,
        )
        lang_table.add_column("Dil", style="bold white", ratio=2)
        lang_table.add_column("Oran", justify="right", ratio=1)
        lang_table.add_column("Dağılım", ratio=4)

        for lang, pct in list(summary.top_languages.items())[:8]:
            lang_table.add_row(
                escape(lang),
                f"%{pct:.1f}",
                f"[cyan]{_progress_bar(pct, width=24)}[/cyan]",
            )
        out.print(lang_table)

    if summary.recommendations:
        rec_lines = "\n".join(
            f"[bold yellow]{idx}.[/bold yellow] {escape(rec)}"
            for idx, rec in enumerate(summary.recommendations, start=1)
        )
        out.print(
            Panel(
                rec_lines,
                title="[bold yellow]Öne Çıkan Profil Önerileri[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            )
        )
    out.print()


def render_repo_markdown(report: HealthReport) -> str:
    """Serialize a repository HealthReport to clean Markdown."""
    lines: list[str] = [
        f"# RepoPulse Sağlık Raporu: `{report.repo_full_name}`",
        "",
    ]
    if report.html_url:
        lines.append(f"- **Repo URL:** {report.html_url}")
    if report.description:
        lines.append(f"- **Açıklama:** {report.description}")
    lines.extend(
        [
            f"- **Toplam Skor:** **{report.total_score} / {report.max_score}** (Not: **{report.grade}**)",
            f"- **İstatistikler:** {report.stargazers_count} yıldız | {report.forks_count} fork | {report.open_issues_count} açık issue",
            f"- **Analiz Tarihi (UTC):** {report.analyzed_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Kategori Bazlı Puanlama",
            "",
            "| Kategori | Puan | Yüzde | Detaylar |",
            "| --- | :---: | :---: | --- |",
        ]
    )

    for cat in report.categories:
        details_str = "<br>".join(cat.details)
        lines.append(
            f"| {cat.name} | {cat.score} / {cat.max_score} | %{cat.percentage:.1f} | {details_str} |"
        )

    lines.extend(["", "## Dil Dağılımı", ""])
    if report.language_percentages:
        lines.append("| Dil | Yüzde |")
        lines.append("| --- | :---: |")
        for lang, pct in report.language_percentages.items():
            lines.append(f"| {lang} | %{pct:.1f} |")
    else:
        lines.append("_Dil dağılımı tespit edilemedi._")

    lines.extend(["", "## İyileştirme Önerileri", ""])
    if report.recommendations:
        for rec in report.recommendations:
            lines.append(f"- [ ] {rec}")
    else:
        lines.append("Tüm sağlık kontrolleri başarıyla geçildi. Tebrikler!")

    lines.append("")
    return "\n".join(lines)


def render_profile_markdown(summary: ProfileSummary) -> str:
    """Serialize a ProfileSummary to clean Markdown."""
    lines: list[str] = [
        f"# RepoPulse Profil Sağlık Özeti: `@{summary.username}`",
        "",
        f"- **Profil URL:** {summary.profile_url}",
        f"- **İncelenen Repo Sayısı:** {summary.total_repos_analyzed}",
        f"- **Ortalama Skor:** **{summary.average_score:.1f} / 100** (Not: **{summary.grade}**)",
    ]
    if summary.best_repo:
        lines.append(f"- **En Sağlıklı Repo:** {summary.best_repo}")
    if summary.weakest_repo:
        lines.append(f"- **En Çok Geliştirilebilir Repo:** {summary.weakest_repo}")
    lines.append(f"- **Analiz Tarihi (UTC):** {summary.analyzed_at.strftime('%Y-%m-%d %H:%M:%S')}")

    lines.extend(
        [
            "",
            "## İncelenen Repolar",
            "",
            "| Repo | Skor | Not | Yıldız | Ana Dil | Öneri Sayısı |",
            "| --- | :---: | :---: | :---: | --- | :---: |",
        ]
    )

    for r in summary.repo_reports:
        top_lang = next(iter(r.language_percentages.keys()), "-")
        repo_link = f"[{r.repo_full_name}]({r.html_url})" if r.html_url else r.repo_full_name
        lines.append(
            f"| {repo_link} | {r.total_score}/100 | {r.grade} | {r.stargazers_count} | {top_lang} | {len(r.recommendations)} |"
        )

    lines.extend(["", "## Profil Genelinde Dil Dağılımı", ""])
    if summary.top_languages:
        lines.append("| Dil | Oran |")
        lines.append("| --- | :---: |")
        for lang, pct in summary.top_languages.items():
            lines.append(f"| {lang} | %{pct:.1f} |")
    else:
        lines.append("_Dil dağılımı tespit edilemedi._")

    lines.extend(["", "## Öne Çıkan İyileştirme Önerileri", ""])
    if summary.recommendations:
        for rec in summary.recommendations:
            lines.append(f"- [ ] {rec}")
    else:
        lines.append("İncelenen tüm repolar yüksek sağlık skoruna sahip!")

    lines.append("")
    return "\n".join(lines)


def export_repo_report_markdown(report: HealthReport, output_path: str | Path) -> Path:
    """Write a repository HealthReport as a UTF-8 Markdown file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_repo_markdown(report), encoding="utf-8")
    return path


def export_profile_summary_markdown(summary: ProfileSummary, output_path: str | Path) -> Path:
    """Write a ProfileSummary as a UTF-8 Markdown file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_profile_markdown(summary), encoding="utf-8")
    return path
