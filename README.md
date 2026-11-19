# RepoPulse

**RepoPulse**, Python 3.13 uyumlu bir **GitHub Profil & Repo Sağlık Denetçisi** CLI aracıdır. GitHub REST API v3 üzerinden depoları analiz ederek 100 üzerinden sağlık skoru hesaplar, terminalde renkli `Rich` raporları sunar ve tek komutla temiz Markdown (`.md`) raporlarına dışa aktarır.

## Özellikler

- **Tekil Repo Denetimi (`repopulse repo`):** README kalitesi, standart dosyalar, commit güncelliği/açıklayıcılığı, dil dağılımı ve genel bakım sağlığına göre 100 puanlık skor kartı.
- **Profil Sağlık Özeti (`repopulse profile`):** Bir GitHub kullanıcısının en güncel veya en popüler herkese açık repolarını tarayarak genel profil ortalaması, en güçlü/geliştirilebilir repo ve dil dağılımı özeti.
- **Akıllı İyileştirme Önerileri:** Eksik her kriter için somut, uygulanabilir aksiyon maddeleri.
- **Markdown Dışa Aktarma:** `--output report.md` parametresiyle paylaşılabilir rapor dosyası üretimi.
- **Token ve Hata Yönetimi:** `.env` içindeki `GITHUB_TOKEN` ile 5000 istek/saat limiti; 404 (bulunamadı) ve 403 (rate limit) durumları için anlaşılır yönlendirmeler.

## Puanlama Kriterleri (100 Puan)

| Kategori | Maks. Puan | İncelenen Kriterler |
| --- | :---: | --- |
| **Dokümantasyon** | 35 | `README.md` varlığı (15p), uzunluk ve Markdown başlık yapısı (10p), repo açıklaması (5p), `topics` etiketleri (5p) |
| **Standart Dosyalar** | 25 | `LICENSE` (10p), `.gitignore` (10p), yapılandırma/topluluk dosyaları (`pyproject.toml`, `requirements.txt`, `package.json`, `CONTRIBUTING.md` vb.) (5p) |
| **Aktivite & Commit Kalitesi** | 25 | Son commit'in güncelliği (10p), son 20 commit mesajının açıklayıcılığı (15p) |
| **Bakım & Görünürlük** | 15 | Dil dağılımının bulunması (5p), arşiv durumu, issue sağlığı, yıldız ve fork etkileşimi (10p) |

## Kurulum

```bash
# 1. Sanal ortam oluşturun (Python 3.13)
py -3.13 -m venv .venv

# 2. Sanal ortamı etkinleştirin (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# 3. Paketi ve bağımlılıkları geliştirme modunda kurun
pip install -e ".[dev]"
```

### GitHub Token Yapılandırması (Opsiyonel)

Anonim GitHub API istekleri saatte 60 istekle sınırlıdır. Daha yüksek limit için `.env.example` dosyasını `.env` olarak kopyalayıp kendi Personal Access Token değerinizi ekleyin:

```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

## Kullanım

### Tek Bir Repoyu Analiz Etme

```bash
repopulse repo Muhyild25/ProjeHub
repopulse repo Muhyild25/ProjeHub --output report.md
```

### Bir GitHub Profilini Analiz Etme

```bash
repopulse profile Muhyild25 --limit 5
repopulse profile Muhyild25 --limit 5 --sort stars --output profile_report.md
```

## Testleri Çalıştırma

```bash
pytest
```

## Proje Yapısı

```text
RepoPulse/
├── repopulse/
│   ├── __init__.py
│   ├── analyzer.py       # 100 puanlık sağlık skorlama motoru
│   ├── cli.py            # Typer tabanlı CLI komutları (repo, profile)
│   ├── github_client.py  # httpx tabanlı GitHub REST API v3 istemcisi
│   ├── models.py         # Pydantic v2 veri modelleri
│   └── reporter.py       # Rich terminal çıktısı ve Markdown dışa aktarıcı
├── tests/
│   └── test_analyzer.py  # pytest birim testleri
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```
