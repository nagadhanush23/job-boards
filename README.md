# Job-Boards

A high-performance scraper and local search engine that pulls public job postings directly from **Ashby, Greenhouse, and Lever** company job boards. No API keys, no accounts, and no paid proxies required.

Results accumulate automatically into a local **SQLite database** (`job-boards.db`), export into **Standard Schema JSON** (`job-boards.standard.json`) and **CSV** (`job-boards.csv`), and are viewable in a modern **Web UI**.

---

## At a Glance: Verified Scale & Datapoints

Measured across live production APIs:

| Platform | Discovered Boards | Live Jobs | Median Age | Oldest Live Post |
|---|---|---|---|---|
| **Greenhouse** | ~6,797 boards | ~180,915 jobs | 60 days | ~7.6 years |
| **Ashby** | ~3,617 boards | ~54,591 jobs | 48 days | ~6.8 years |
| **Lever** | ~2,718 boards | ~72,594 jobs | 97 days | ~16 years (2009) |
| **Total** | **~13,146 boards** | **~308,100 jobs** | **62 days** | — |

> **Starter Seed vs Full Discovery:**  
> A fresh clone includes [`boards.seed.json`](boards.seed.json) with **60 verified companies** (e.g. OpenAI, Anthropic, Stripe, Databricks, Palantir, Linear, Airbnb, Vercel) for instant execution. To unlock all **13,146+ boards**, see [Board Discovery](#board-discovery) below.

---

## Quick Start & Setup

### 1. Prerequisites
- **Python >= 3.9** (or [uv](https://docs.astral.sh/uv/))
- Zero third-party dependencies required (uses Python standard library).

### 2. Setup & Configuration
```bash
git clone https://github.com/nagadhanush23/job-boards.git
cd job-boards

# Copy environment configuration
cp .env.example .env
```

Identify your traffic (required by archive and ATS etiquette):
```bash
# Windows (PowerShell)
$env:JOB_SCRAPER_CONTACT="nagadhanushexcellencia@gmail.com"

# Linux / macOS
export JOB_SCRAPER_CONTACT="nagadhanushexcellencia@gmail.com"
```

### 3. Initialize & Scrape
```bash
# Initial test scrape (10 boards per platform)
python job_boards.py --limit 10

# Search software engineer roles across all seed boards
python job_boards.py --title "software engineer" --limit 100

# Run offline verification suite (58 tests, ~1s)
python test_job_boards.py
```

---

## Web Frontend & Local UI

Run the zero-dependency local web app connected directly to `job-boards.db`:

```bash
python server.py
# Open: http://localhost:8000
```

- **Live Search & Filter:** Instant search by keyword, title, department, company, ATS, and remote-only.
- **Card Grid & Data Table:** Toggle between rich card view and high-density data table.
- **Standard Schema Viewer:** View and copy standardized JSON format for any job posting.

---

## Board Discovery

| Discovery Mode | Command | Duration | What It Does |
|---|---|---|---|
| **Starter (Default)** | `python job_boards.py --title "swe"` | Instant | Scrapes from 60 bundled seed boards in `boards.seed.json` |
| **Fast Discovery** | `python job_boards.py --refresh-recent --title "swe"` | ~3–4 min | Queries urlscan.io + recent archive captures to cache active boards |
| **Full Archival** | `python job_boards.py --refresh-boards --all` | ~20–25 min | Crawls full Internet Archive CDX across all 13,146 boards |

Once discovered, boards are cached in `boards.json` and reused on all future runs.

---

## Standardized JSON Schema

Jobs are automatically structured and saved into the `jobs_standard` SQLite table and exported to `job-boards.standard.json`.

```bash
# Manually synchronize and export standard schema
python standard_schema.py
```

### Output Schema Structure:
- **Identity:** `source` ("ats"), `source_id`, `og_source` ("ashby" | "greenhouse" | "lever"), `url`
- **Core:** `title`, `organization`, `organization_logo`, `date_posted`, `description`
- **Location:** `cities`, `regions`, `countries`, `work_arrangement` ("On-site" | "Hybrid" | "Remote OK" | "Remote Solely"), `office_days`, `remote_location`
- **Geo:** `lats`, `lngs`, `timezones`
- **Salary:** `currency`, `min`, `max`, `value`, `unit` ("YEAR" | "HOUR")
- **Job Details:** `employment_type` (["FULL_TIME", ...]), `experience_level` ("0-2" | "2-5" | "5-10" | "10+"), `skills`, `benefits`, `responsibilities`, `requirements`, `visa_sponsorship`
- **Company:** `industry`, `type`, `employees`, `headquarters`, `slug`
- **Meta:** `source_type`, `source_domain`, `ats_source`, `directapply`, `ats_duplicate`

---

## Command Reference & Cheat Sheet

| Category | Flag / Command | Description |
|---|---|---|
| **ATS Selection** | `--ats greenhouse` | Filter platforms: `ashby`, `greenhouse`, `lever` (comma-separated or `all`) |
| **Job Title** | `--title "software engineer"` | Filter by role title |
| **Match Mode** | `--match exact` or `--match fuzzy` | `fuzzy` (default, contains substring) or `exact` match |
| **Description Search** | `--grep '\brust\b\|\bgolang\b'` | Case-insensitive regex across title & full description |
| **Full Unfiltered** | `--all` | Every job on every board (cannot combine with `--title` or `--grep`) |
| **Date Window** | `--since 7d` | Window filter: `1d`, `7d`, `2w`, `3m`, `1y` (default: all) |
| **Sort Order** | `--sort recent` or `--sort board` | `board` (default, company/platform) or `recent` (newest first) |
| **Database Delta** | `--new-only` | Only jobs not previously recorded in the database |
| **Remote Filter** | `--remote` | Filter for remote positions only |
| **Concurrency** | `--concurrency 8` | Thread concurrency (default: 8, connection-pooled) |
| **Board Limit** | `--limit 50` | Maximum boards scanned per platform |
| **Fast Discovery** | `--refresh-recent` | Fast discovery pass via urlscan.io and recent archive crawls |
| **Full Refresh** | `--refresh-boards` | Full re-crawl of all board slugs from Internet Archive |
| **Custom Boards** | `--boards-from boards.json` | Scan only boards listed in the given JSON file |
| **Custom Database** | `--db custom.db` | Custom SQLite database file (default: `job-boards.db`) |
| **Skip Database** | `--no-db` | Write CSV and JSON only, skipping SQLite writes |
| **Output Prefix** | `--out my-scrape` | Prefix for output files (`my-scrape.csv`, `my-scrape.json`) |

---

## Data Model & Integrity Gates

The tool enforces two load-bearing database consistency rules:
- **`may_close_postings()`**: Only an unfiltered run (`--all` without `--title`, `--grep`, `--since`, or `--new-only`) is entitled to mark vanished postings as closed (`closed_at`). Filtered runs must never close postings they simply skipped.
- **`may_use_etags()`**: Conditional `304 Not Modified` requests (ETags) are only trusted on unfiltered runs to guarantee partial searches never skip unpersisted board postings.

---

## Technical Documentation & Knowledge Base (`openwiki/`)

This repository includes a dedicated in-repo architecture wiki in [`openwiki/`](openwiki/):

- 📖 **[Quickstart (`openwiki/quickstart.md`)](openwiki/quickstart.md)**: Architecture map, system purpose, and key developer workflows.
- 🏛️ **[Architecture & Data Model (`openwiki/architecture/`)](openwiki/architecture/)**: Detailed breakdown of Ashby, Greenhouse, and Lever APIs, field mappings, and schema specifications.
- ⚙️ **[Core Workflows (`openwiki/workflows/`)](openwiki/workflows/)**: In-depth execution guides for [Board Discovery](openwiki/workflows/board-discovery.md) (Internet Archive / urlscan) and [Job Scraping](openwiki/workflows/job-scrape.md) (connection pooling, HTTP ETag conditional requests).
- 🧪 **[Testing Guide (`openwiki/testing.md`)](openwiki/testing.md)**: Deep dive into the offline verification test suite, test coverage map, and regression safety boundaries.
- 📋 **[Operations Runbook (`openwiki/operations/runbook.md`)](openwiki/operations/runbook.md)**: Rate limiting policies, connection pool handling, and error handling strategies.

> **Note:** The `openwiki/` documentation is integral to repository verification—our unit tests validate that references across documentation and the codebase remain accurate.

---

## Exactly What to Run on a Fresh Clone

```bash
# 1. Clone your repository
git clone https://github.com/nagadhanush23/job-boards.git
cd job-boards

# 2. Run the offline test suite (verifies everything in ~1 second)
python test_job_boards.py
# Output: ok (58 tests)

# 3. Set your contact email (required etiquette for ATS/archive APIs)
$env:JOB_SCRAPER_CONTACT="nagadhanushexcellencia@gmail.com"   # Windows PowerShell
# export JOB_SCRAPER_CONTACT="nagadhanushexcellencia@gmail.com"  # macOS / Linux

# 4. Run a live scrape
# (Uses bundled boards.seed.json with 60 verified top tech companies)
python job_boards.py --limit 10

# 5. Transform all scraped jobs into the standardized JSON schema
python standard_schema.py

# 6. Launch the web UI
python server.py
# Open: http://localhost:8000
```

---

## Maintainer & Author

**Naga Dhanush**  
Developer & maintainer of the SQLite local development architecture, standardized schema engine, and web explorer UI.

- 💼 **LinkedIn:** [linkedin.com/in/nagadhanushch](https://www.linkedin.com/in/nagadhanushch)
- ✉️ **Contact:** [dhanushnaga902@gmail.com](mailto:dhanushnaga902@gmail.com)
- 🐙 **GitHub:** [@nagadhanush23](https://github.com/nagadhanush23)

---

## Original Credits & License

Originally created by Matt Herzog ([@mtmherzog](https://www.linkedin.com/in/mtmherzog)).  
Licensed under the [MIT License](LICENSE).
