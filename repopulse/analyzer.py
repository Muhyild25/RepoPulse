"""Repository and profile health scoring engine for RepoPulse."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from repopulse.models import CategoryScore, HealthReport, ProfileSummary, RepoData

LICENSE_FILENAMES = {
    "license",
    "license.md",
    "license.txt",
    "license.rst",
    "copying",
    "copying.md",
    "copying.txt",
    "unlicense",
}

CONFIG_OR_COMMUNITY_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "poetry.lock",
    "environment.yml",
    "package.json",
    "tsconfig.json",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "gemfile",
    "cmakelists.txt",
    "makefile",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "contributing.md",
    "code_of_conduct.md",
    "security.md",
    "changelog.md",
    ".github",
    ".editorconfig",
    ".pre-commit-config.yaml",
}

WEAK_COMMIT_WORDS = {
    "update",
    "updated",
    "updates",
    "fix",
    "fixed",
    "fixes",
    "bugfix",
    "test",
    "tests",
    "testing",
    "wip",
    "changes",
    "change",
    "commit",
    "init",
    "initial",
    "misc",
    "stuff",
    "temp",
    "tmp",
    "cleanup",
    "minor",
    "edit",
    "edited",
    "save",
    "push",
    "check",
    "debug",
    "done",
    "ok",
    "final",
    "asdf",
    "asd",
    "deneme",
    "guncelleme",
    "güncelleme",
    "duzeltme",
    "düzeltme",
}

HEADING_PATTERN = re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S")
WORD_PATTERN = re.compile(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+")


def compute_grade(score: float) -> str:
    """Map a 0-100 numerical score to a letter grade."""
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 45:
        return "D"
    return "F"


def compute_language_percentages(languages: dict[str, int]) -> dict[str, float]:
    """Convert raw byte counts per language into sorted percentages."""
    total_bytes = sum(v for v in languages.values() if v > 0)
    if total_bytes <= 0:
        return {}
    sorted_langs = sorted(
        ((lang, count) for lang, count in languages.items() if count > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    return {lang: round((count / total_bytes) * 100, 1) for lang, count in sorted_langs}


def is_descriptive_commit_message(message: str) -> bool:
    """Return True if a commit's subject line is descriptive rather than trivial."""
    subject = message.strip().splitlines()[0].strip() if message and message.strip() else ""
    if len(subject) < 10:
        return False

    words = WORD_PATTERN.findall(subject.lower())
    if len(words) < 2:
        return False

    # Reject messages composed exclusively of weak filler words (e.g., "update fix test")
    if all(word in WEAK_COMMIT_WORDS for word in words):
        return False

    return True


def _score_documentation(repo: RepoData, recommendations: list[str]) -> CategoryScore:
    """Score Documentation category (35 pts max)."""
    score = 0
    details: list[str] = []

    readme = (repo.readme_content or "").strip()
    root_lower = {f.lower() for f in repo.root_files}
    has_readme_file = bool(readme) or any(f.startswith("readme") for f in root_lower)

    # 1. README existence (15 pts)
    if has_readme_file and readme:
        score += 15
        details.append("README.md mevcut (+15/15)")
    elif has_readme_file:
        score += 5
        details.append("README dosyası mevcut ancak içi boş (+5/15)")
        recommendations.append(
            "README.md dosyasını projenin amacı, kurulum adımları ve kullanım örnekleriyle doldurun."
        )
    else:
        details.append("README.md bulunamadı (+0/15)")
        recommendations.append(
            "Proje kök dizinine kurulum, kullanım ve proje özetini içeren bir README.md ekleyin."
        )

    # 2. README length and heading structure (10 pts)
    if readme:
        readme_len = len(readme)
        headings_count = len(HEADING_PATTERN.findall(readme))

        if readme_len >= 300:
            length_pts = 5
        elif readme_len >= 100:
            length_pts = 2
            recommendations.append(
                f"README.md içeriğini genişletin (mevcut: {readme_len} karakter; en az 300 karakter önerilir)."
            )
        else:
            length_pts = 0
            recommendations.append(
                f"README.md çok kısa ({readme_len} karakter). Kurulum, özellikler ve örnek kullanım bölümleri ekleyin."
            )

        if headings_count >= 2:
            heading_pts = 5
        elif headings_count == 1:
            heading_pts = 2
            recommendations.append(
                "README.md içinde '## Kurulum', '## Kullanım' gibi en az 2 Markdown alt başlığı kullanın."
            )
        else:
            heading_pts = 0
            recommendations.append(
                "README.md dosyasını okunabilir kılmak için Markdown başlıkları (#, ##) ile bölümlendirin."
            )

        structure_pts = length_pts + heading_pts
        score += structure_pts
        details.append(
            f"README yapısı: {readme_len} karakter, {headings_count} başlık (+{structure_pts}/10)"
        )
    else:
        details.append("README uzunluk ve başlık yapısı değerlendirilemedi (+0/10)")

    # 3. Repository description (5 pts)
    desc = (repo.description or "").strip()
    if len(desc) >= 5:
        score += 5
        details.append("Repo açıklaması (description) tanımlı (+5/5)")
    else:
        details.append("Repo açıklaması eksik veya çok kısa (+0/5)")
        recommendations.append(
            "GitHub repo ayarlarından projeyi tek cümleyle özetleyen bir açıklama (description) ekleyin."
        )

    # 4. Repository topics (5 pts)
    if len(repo.topics) >= 1:
        score += 5
        details.append(f"Repo etiketleri (topics) tanımlı: {len(repo.topics)} adet (+5/5)")
    else:
        details.append("Repo etiketi (topics) tanımlanmamış (+0/5)")
        recommendations.append(
            "Reponun keşfedilebilirliğini artırmak için en az 2-3 ilgili GitHub etiketi (topics) ekleyin."
        )

    return CategoryScore(name="Dokümantasyon", score=score, max_score=35, details=details)


def _score_standard_files(repo: RepoData, recommendations: list[str]) -> CategoryScore:
    """Score Standard Files category (25 pts max)."""
    score = 0
    details: list[str] = []
    root_lower = {f.lower() for f in repo.root_files}

    # 1. LICENSE (10 pts)
    has_license = bool(repo.license_name) or bool(root_lower & LICENSE_FILENAMES)
    if has_license:
        score += 10
        label = f" ({repo.license_name})" if repo.license_name else ""
        details.append(f"LICENSE dosyası mevcut{label} (+10/10)")
    else:
        details.append("LICENSE dosyası bulunamadı (+0/10)")
        recommendations.append(
            "Açık kaynak kullanım koşullarını netleştirmek için kök dizine bir LICENSE dosyası (örn. MIT) ekleyin."
        )

    # 2. .gitignore (10 pts)
    if ".gitignore" in root_lower:
        score += 10
        details.append(".gitignore dosyası mevcut (+10/10)")
    else:
        details.append(".gitignore dosyası bulunamadı (+0/10)")
        recommendations.append(
            "Gereksiz derleme/ortam dosyalarının depoya girmemesi için uygun bir .gitignore dosyası ekleyin."
        )

    # 3. Project config or community file (5 pts)
    matched_configs = sorted(root_lower & CONFIG_OR_COMMUNITY_FILES)
    if matched_configs:
        score += 5
        shown = ", ".join(matched_configs[:3])
        details.append(f"Yapılandırma/topluluk dosyası mevcut ({shown}) (+5/5)")
    else:
        details.append("Yapılandırma veya topluluk dosyası bulunamadı (+0/5)")
        recommendations.append(
            "Bağımlılık veya katkı standartları için pyproject.toml, requirements.txt, package.json veya CONTRIBUTING.md ekleyin."
        )

    return CategoryScore(name="Standart Dosyalar", score=score, max_score=25, details=details)


def _score_activity_and_commits(
    repo: RepoData,
    recommendations: list[str],
    now: datetime,
) -> CategoryScore:
    """Score Activity & Commit Quality category (25 pts max)."""
    score = 0
    details: list[str] = []

    # 1. Recency of latest commit (10 pts)
    latest_date: datetime | None = None
    if repo.commits:
        commit_dates = [c.date for c in repo.commits if c.date is not None]
        if commit_dates:
            latest_date = max(commit_dates)
    if latest_date is None:
        latest_date = repo.pushed_at or repo.updated_at

    if latest_date is not None:
        if latest_date.tzinfo is None:
            latest_date = latest_date.replace(tzinfo=timezone.utc)
        days_since = max(0, (now - latest_date.astimezone(timezone.utc)).days)

        if days_since <= 30:
            recency_pts = 10
        elif days_since <= 90:
            recency_pts = 7
        elif days_since <= 180:
            recency_pts = 4
            recommendations.append(
                f"Son commit {days_since} gün önce atılmış; projeyi güncel tutun veya bağımlılıkları gözden geçirin."
            )
        elif days_since <= 365:
            recency_pts = 2
            recommendations.append(
                f"Repo {days_since} gündür güncellenmiyor; aktif geliştirme sürecekse bakım commit'i ekleyin."
            )
        else:
            recency_pts = 0
            recommendations.append(
                f"Repo 1 yıldan uzun süredir ({days_since} gün) pasif; artık geliştirilmiyorsa arşivlemeyi düşünün."
            )
        score += recency_pts
        details.append(f"Son aktivite: {days_since} gün önce (+{recency_pts}/10)")
    else:
        details.append("Commit tarih bilgisi bulunamadı (+0/10)")
        recommendations.append("Depoya düzenli ve izlenebilir commit geçmişi oluşturun.")

    # 2. Commit message descriptiveness (15 pts)
    if repo.commits:
        total_commits = len(repo.commits)
        good_commits = sum(1 for c in repo.commits if is_descriptive_commit_message(c.message))
        weak_commits = total_commits - good_commits
        ratio = good_commits / total_commits
        msg_pts = round(15 * ratio)
        score += msg_pts
        details.append(
            f"Açıklayıcı commit mesajları: {good_commits}/{total_commits} (+{msg_pts}/15)"
        )
        if weak_commits > 0 and ratio < 0.8:
            recommendations.append(
                f"Son {total_commits} commit'in {weak_commits} tanesi zayıf veya tek kelimelik. "
                "En az 10 karakterli, neyin neden değiştiğini açıklayan mesajlar (örn. Conventional Commits) kullanın."
            )
    else:
        details.append("İncelenecek commit bulunamadı (+0/15)")
        recommendations.append(
            "Anlamlı ve açıklayıcı commit mesajlarıyla ilk proje geçmişini oluşturun."
        )

    return CategoryScore(
        name="Aktivite & Commit Kalitesi",
        score=score,
        max_score=25,
        details=details,
    )


def _score_maintenance_and_visibility(
    repo: RepoData,
    recommendations: list[str],
) -> CategoryScore:
    """Score Maintenance & Visibility category (15 pts max)."""
    score = 0
    details: list[str] = []

    # 1. Language distribution detected (5 pts)
    total_lang_bytes = sum(v for v in repo.languages.values() if v > 0)
    if total_lang_bytes > 0:
        score += 5
        top_lang = max(repo.languages.items(), key=lambda item: item[1])[0]
        details.append(
            f"Dil dağılımı tespit edildi ({len(repo.languages)} dil, baskın: {top_lang}) (+5/5)"
        )
    else:
        details.append("Dil dağılımı bulunamadı (+0/5)")
        recommendations.append(
            "Depoda GitHub tarafından tanınan kaynak kod dosyası tespit edilemedi; proje yapısını doğrulayın."
        )

    # 2. General repository health, issues, stars & forks (10 pts)
    health_pts = 0

    # Active (non-archived) status: 3 pts
    if not repo.archived:
        health_pts += 3
    else:
        recommendations.append(
            "Bu repo arşivlenmiş (salt okunur) durumda; aktif bakım gerekiyorsa arşiv durumunu gözden geçirin."
        )

    # Issue tracker enabled: 2 pts
    if repo.has_issues:
        health_pts += 2
    else:
        recommendations.append(
            "Hata bildirimi ve geri bildirim alabilmek için repo ayarlarından GitHub Issues özelliğini etkinleştirin."
        )

    # Manageable open issue backlog: 1 pt
    if repo.open_issues_count <= 50:
        health_pts += 1
    else:
        recommendations.append(
            f"Açık issue sayısı yüksek ({repo.open_issues_count}); eski veya çözülmüş issue'ları gözden geçirip etiketleyin."
        )

    # Community visibility (stars/forks): 4 pts
    if repo.stargazers_count >= 5 or repo.forks_count >= 2:
        health_pts += 4
    elif repo.stargazers_count >= 1 or repo.forks_count >= 1:
        health_pts += 2
        recommendations.append(
            "Görünürlüğü artırmak için README'ye ekran görüntüleri, canlı demo bağlantısı veya rozetler (badges) ekleyin."
        )
    else:
        recommendations.append(
            "Repo henüz yıldız veya fork almamış; ekran görüntüleri, etiketler (topics) ve demo bağlantısıyla görünürlüğü artırın."
        )

    score += health_pts
    details.append(
        f"Genel sağlık & etkileşim: {repo.stargazers_count} yıldız, "
        f"{repo.forks_count} fork, {repo.open_issues_count} açık issue (+{health_pts}/10)"
    )

    return CategoryScore(
        name="Bakım & Görünürlük",
        score=score,
        max_score=15,
        details=details,
    )


def analyze_repository(repo: RepoData, *, now: datetime | None = None) -> HealthReport:
    """Analyze a single repository and produce a 100-point HealthReport."""
    reference_now = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    recommendations: list[str] = []

    categories = [
        _score_documentation(repo, recommendations),
        _score_standard_files(repo, recommendations),
        _score_activity_and_commits(repo, recommendations, reference_now),
        _score_maintenance_and_visibility(repo, recommendations),
    ]

    total_score = sum(cat.score for cat in categories)
    max_score = sum(cat.max_score for cat in categories)
    language_percentages = compute_language_percentages(repo.languages)

    return HealthReport(
        repo_full_name=repo.full_name,
        html_url=repo.html_url,
        description=repo.description,
        total_score=total_score,
        max_score=max_score,
        grade=compute_grade(total_score),
        categories=categories,
        language_percentages=language_percentages,
        recommendations=recommendations,
        stargazers_count=repo.stargazers_count,
        forks_count=repo.forks_count,
        open_issues_count=repo.open_issues_count,
        analyzed_at=reference_now,
    )


def analyze_profile(
    username: str,
    repo_reports: list[HealthReport],
    *,
    repos_data: list[RepoData] | None = None,
    now: datetime | None = None,
) -> ProfileSummary:
    """Aggregate multiple repository HealthReports into a single ProfileSummary."""
    reference_now = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)

    if not repo_reports:
        return ProfileSummary(
            username=username,
            profile_url=f"https://github.com/{username}",
            total_repos_analyzed=0,
            average_score=0.0,
            grade="F",
            recommendations=["Bu kullanıcı için analiz edilebilecek herkese açık repo bulunamadı."],
            analyzed_at=reference_now,
        )

    average_score = round(
        sum(report.total_score for report in repo_reports) / len(repo_reports),
        1,
    )
    best = max(repo_reports, key=lambda r: r.total_score)
    weakest = min(repo_reports, key=lambda r: r.total_score)

    # Aggregate languages across profile
    if repos_data:
        combined_bytes: Counter[str] = Counter()
        for repo in repos_data:
            for lang, byte_count in repo.languages.items():
                if byte_count > 0:
                    combined_bytes[lang] += byte_count
        top_languages = compute_language_percentages(dict(combined_bytes))
    else:
        combined_pct: Counter[str] = Counter()
        for report in repo_reports:
            for lang, pct in report.language_percentages.items():
                combined_pct[lang] += pct
        total_pct = sum(combined_pct.values())
        top_languages = (
            {
                lang: round((val / total_pct) * 100, 1)
                for lang, val in combined_pct.most_common()
            }
            if total_pct > 0
            else {}
        )

    # Highlight the most frequent recommendations across analyzed repos
    rec_counter: Counter[str] = Counter()
    for report in repo_reports:
        for rec in report.recommendations:
            rec_counter[rec] += 1

    profile_recommendations: list[str] = []
    for rec, count in rec_counter.most_common(6):
        if count > 1:
            profile_recommendations.append(f"[{count}/{len(repo_reports)} repo] {rec}")
        else:
            profile_recommendations.append(rec)

    return ProfileSummary(
        username=username,
        profile_url=f"https://github.com/{username}",
        total_repos_analyzed=len(repo_reports),
        average_score=average_score,
        grade=compute_grade(average_score),
        best_repo=f"{best.repo_full_name} ({best.total_score}/100)",
        weakest_repo=f"{weakest.repo_full_name} ({weakest.total_score}/100)",
        top_languages=top_languages,
        repo_reports=repo_reports,
        recommendations=profile_recommendations,
        analyzed_at=reference_now,
    )
