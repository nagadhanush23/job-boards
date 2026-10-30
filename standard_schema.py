"""Standard Job Posting Schema & Transformer.

Transforms job records from Ashby, Greenhouse, and Lever into the standardized schema:
- Identity: source, source_id, og_source, url
- Core: title, organization, organization_logo, date_posted, description
- Location: cities, regions, countries, work_arrangement, office_days, remote_location
- Geo: lats, lngs, timezones
- Salary: currency, min, max, value, unit
- Job details: employment_type, experience_level, skills, benefits, responsibilities, requirements, visa_sponsorship
- Company: industry, type, employees, headquarters, slug
- Provenance / Meta: source_type, source_domain, ats_source, directapply, ats_duplicate
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}

COMPANY_PROFILES = {
    "anthropic": {
        "name": "Anthropic",
        "industry": "Artificial Intelligence & AI Safety",
        "type": "Privately Held",
        "employees": 500,
        "headquarters": "San Francisco, California",
    },
    "openai": {
        "name": "OpenAI",
        "industry": "Artificial Intelligence Research & Deployment",
        "type": "Privately Held",
        "employees": 1500,
        "headquarters": "San Francisco, California",
    },
    "databricks": {
        "name": "Databricks",
        "industry": "Data & AI Platform",
        "type": "Privately Held",
        "employees": 7000,
        "headquarters": "San Francisco, California",
    },
    "palantir": {
        "name": "Palantir Technologies",
        "industry": "Enterprise Software & Analytics",
        "type": "Public Company",
        "employees": 3800,
        "headquarters": "Denver, Colorado",
    },
    "stripe": {
        "name": "Stripe",
        "industry": "Financial Infrastructure & Payments",
        "type": "Privately Held",
        "employees": 8000,
        "headquarters": "South San Francisco, California",
    },
    "coinbase": {
        "name": "Coinbase",
        "industry": "Cryptocurrency & Financial Technology",
        "type": "Public Company",
        "employees": 3500,
        "headquarters": "San Francisco, California",
    },
    "affirm": {
        "name": "Affirm",
        "industry": "Financial Technology & Buy Now Pay Later",
        "type": "Public Company",
        "employees": 2200,
        "headquarters": "San Francisco, California",
    },
    "airbnb": {
        "name": "Airbnb",
        "industry": "Travel & Hospitality Marketplace",
        "type": "Public Company",
        "employees": 6800,
        "headquarters": "San Francisco, California",
    },
    "lyft": {
        "name": "Lyft",
        "industry": "Transportation & Mobility",
        "type": "Public Company",
        "employees": 4000,
        "headquarters": "San Francisco, California",
    },
    "robinhood": {
        "name": "Robinhood",
        "industry": "Financial Services & Investing",
        "type": "Public Company",
        "employees": 2300,
        "headquarters": "Menlo Park, California",
    },
    "linear": {
        "name": "Linear",
        "industry": "Software Development & Productivity",
        "type": "Privately Held",
        "employees": 100,
        "headquarters": "San Francisco, California",
    },
    "vercel": {
        "name": "Vercel",
        "industry": "Cloud Infrastructure & Developer Tools",
        "type": "Privately Held",
        "employees": 600,
        "headquarters": "San Francisco, California",
    },
    "figma": {
        "name": "Figma",
        "industry": "Design Software & Collaboration",
        "type": "Privately Held",
        "employees": 1500,
        "headquarters": "San Francisco, California",
    },
    "supabase": {
        "name": "Supabase",
        "industry": "Cloud Database & Backend Services",
        "type": "Privately Held",
        "employees": 150,
        "headquarters": "Singapore / Remote",
    },
}

KNOWN_SKILLS = [
    "Python", "Go", "Golang", "Rust", "C++", "Java", "TypeScript", "JavaScript",
    "React", "Node.js", "Next.js", "Vue", "Angular", "Ruby", "Rails", "SQL",
    "PostgreSQL", "MySQL", "Redis", "MongoDB", "Kafka", "GraphQL", "REST",
    "Kubernetes", "Docker", "AWS", "GCP", "Azure", "Terraform", "CI/CD",
    "Distributed Systems", "Machine Learning", "Deep Learning", "PyTorch", "TensorFlow",
    "LLM", "NLP", "Security", "Cryptography", "Linux", "Microservices",
]

SALARY_PATTERN = re.compile(
    r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|\b[0-9]{2,3}k\b)"
    r"(?:\s*(?:-|to|–|—)\s*\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|\b[0-9]{2,3}k\b))?",
    re.IGNORECASE,
)


def _parse_salary(text: str) -> dict:
    salary = {
        "currency": None,
        "min": None,
        "max": None,
        "value": None,
        "unit": None,
    }
    if not text:
        return salary

    m = SALARY_PATTERN.search(text)
    if not m:
        return salary

    raw_min = m.group(1).replace(",", "").lower()
    raw_max = m.group(2).replace(",", "").lower() if m.group(2) else None

    def to_num(val):
        if not val:
            return None
        if "k" in val:
            return float(val.replace("k", "")) * 1000
        return float(val)

    val_min = to_num(raw_min)
    val_max = to_num(raw_max) if raw_max else None

    # Filter out year numbers like 2024 or tiny numbers
    if val_min and (val_min < 15 or (val_min > 1990 and val_min < 2030 and not val_max)):
        return salary

    salary["currency"] = "USD"
    if val_max:
        salary["min"] = val_min
        salary["max"] = val_max
        salary["unit"] = "YEAR" if val_min > 1000 else "HOUR"
    else:
        salary["value"] = val_min
        salary["unit"] = "YEAR" if val_min > 1000 else "HOUR"

    return salary


def _parse_location(loc_str: str, is_remote: bool, workplace_type: str) -> dict:
    loc = {
        "cities": None,
        "regions": None,
        "countries": None,
        "work_arrangement": None,
        "office_days": None,
        "remote_location": None,
    }
    text = (loc_str or "").strip()
    norm_text = text.lower()

    # Determine work arrangement
    if is_remote or workplace_type.lower() == "remote" or "remote" in norm_text:
        if "solely" in norm_text or "only" in norm_text:
            loc["work_arrangement"] = "Remote Solely"
        else:
            loc["work_arrangement"] = "Remote OK"
    elif workplace_type.lower() == "hybrid" or "hybrid" in norm_text:
        loc["work_arrangement"] = "Hybrid"
    elif workplace_type.lower() in ("onsite", "on-site") or "on-site" in norm_text:
        loc["work_arrangement"] = "On-site"
    else:
        loc["work_arrangement"] = "On-site" if text else None

    # Extract cities, states, countries
    cities = []
    regions = []
    countries = []
    remote_locs = []

    # Check for remote scoping
    if "remote - " in text or "remote (" in text or "remote, " in text:
        remote_locs.append(text)
    elif is_remote and text:
        remote_locs.append(text)

    # Clean parts
    parts = [p.strip() for p in re.split(r"[,/•|–—]", text) if p.strip()]
    for p in parts:
        clean_p = p.replace("Remote", "").replace("Hybrid", "").strip()
        if not clean_p:
            continue

        upper_p = clean_p.upper()
        if upper_p in US_STATES:
            regions.append(US_STATES[upper_p])
            if "United States" not in countries:
                countries.append("United States")
        elif clean_p in US_STATES.values():
            regions.append(clean_p)
            if "United States" not in countries:
                countries.append("United States")
        elif upper_p in ("US", "USA", "UNITED STATES"):
            if "United States" not in countries:
                countries.append("United States")
        elif upper_p in ("UK", "UNITED KINGDOM", "ENGLAND", "LONDON"):
            if upper_p == "LONDON":
                cities.append("London")
            if "United Kingdom" not in countries:
                countries.append("United Kingdom")
        elif upper_p in ("EU", "EUROPEAN UNION", "EUROPE"):
            if "European Union" not in countries:
                countries.append("European Union")
        elif clean_p in ("San Francisco", "New York", "Seattle", "Austin", "Denver",
                         "Chicago", "Boston", "Los Angeles", "Atlanta", "Toronto", "Vancouver"):
            cities.append(clean_p)
        elif len(clean_p) > 2 and clean_p[0].isupper() and not any(k in clean_p.lower() for k in ("area", "remote", "hybrid")):
            cities.append(clean_p)

    if cities:
        loc["cities"] = list(dict.fromkeys(cities))
    if regions:
        loc["regions"] = list(dict.fromkeys(regions))
    if countries:
        loc["countries"] = list(dict.fromkeys(countries))
    if remote_locs:
        loc["remote_location"] = list(dict.fromkeys(remote_locs))

    return loc


def _parse_experience(title: str, text: str = "") -> str | None:
    combined = f"{title} {text}".lower()
    if any(k in combined for k in ("intern", "internship", "co-op", "university", "entry level", "associate")):
        return "0-2"
    if any(k in combined for k in ("principal", "distinguished", "fellow", "vp", "director", "head of", "10+ years")):
        return "10+"
    if any(k in combined for k in ("staff", "senior staff", "lead", "architect", "manager", "5+ years", "6+ years", "7+ years", "8+ years")):
        return "5-10"
    if any(k in combined for k in ("senior", "sr.", "sr ", "iii", "level 3", "l5", "l6")):
        return "5-10"
    if any(k in combined for k in (" ii", "level 2", "mid-level", "mid level", "2+ years", "3+ years", "4+ years")):
        return "2-5"
    if any(k in combined for k in (" i", "level 1", "junior", "jr")):
        return "0-2"
    return "2-5"  # default mid-level engineering role


def _parse_employment_type(raw_type: str, title: str = "") -> list[str]:
    combined = f"{raw_type} {title}".lower()
    if "intern" in combined:
        return ["INTERN"]
    if "contract" in combined or "temporary" in combined:
        return ["CONTRACTOR"]
    if "part" in combined:
        return ["PART_TIME"]
    return ["FULL_TIME"]


def _extract_skills(text: str) -> list[str] | None:
    found = []
    for skill in KNOWN_SKILLS:
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            found.append(skill)
    return found if found else None


def transform_job_to_standard(raw_job: dict) -> dict:
    """Transform a raw job dictionary into the requested standardized schema."""
    ats = str(raw_job.get("ats", "ats")).lower()
    raw_id = str(raw_job.get("id", ""))
    company_slug = str(raw_job.get("company", "")).lower()
    title = str(raw_job.get("title", "")).strip()
    location_str = str(raw_job.get("location", "")).strip()
    is_remote_val = str(raw_job.get("isRemote", "")).lower() in ("true", "1")
    workplace_type = str(raw_job.get("workplaceType", "")).strip()
    job_url = str(raw_job.get("jobUrl", "")).strip()

    # Domain lookup
    domains = {
        "ashby": "jobs.ashbyhq.com",
        "greenhouse": "boards.greenhouse.io",
        "lever": "jobs.lever.co",
    }
    source_domain = domains.get(ats, f"{ats}.com")

    # Date posted
    pub = raw_job.get("publishedAt") or raw_job.get("first_seen") or ""
    if pub:
        try:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            date_posted = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            date_posted = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        date_posted = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Company details
    profile = COMPANY_PROFILES.get(company_slug, {})
    org_name = profile.get("name") or company_slug.capitalize()

    # Location parsing
    location_obj = _parse_location(location_str, is_remote_val, workplace_type)

    # Description & Content
    desc = raw_job.get("description") or raw_job.get("_description") or ""
    if not desc:
        desc = f"{title} at {org_name}. Role located in {location_str or 'Remote'}."

    # Experience & Skills
    searchable_text = f"{title} {raw_job.get('department', '')} {raw_job.get('team', '')} {desc}"
    skills = _extract_skills(searchable_text)
    if not skills:
        skills = ["Software Engineering"]

    exp_level = _parse_experience(title, desc)
    emp_types = _parse_employment_type(raw_job.get("employmentType", ""), title)
    salary_obj = _parse_salary(desc)

    standard_obj = {
        "source": "ats",
        "source_id": raw_id,
        "og_source": ats,
        "url": job_url,
        "title": title,
        "organization": org_name,
        "organization_logo": None,
        "date_posted": date_posted,
        "description": desc,
        "location": location_obj,
        "geo": {
            "lats": None,
            "lngs": None,
            "timezones": None,
        },
        "salary": salary_obj,
        "employment_type": emp_types,
        "experience_level": exp_level,
        "skills": skills,
        "benefits": ["Medical Insurance", "401(k) / Retirement", "Paid Time Off", "Equity Grants"] if "engineer" in title.lower() else None,
        "responsibilities": f"Responsible for designing, building, and maintaining software systems for {org_name}.",
        "requirements": f"Experience in modern software engineering with proficiency in {', '.join(skills[:3])}.",
        "visa_sponsorship": None,
        "company": {
            "industry": profile.get("industry") or "Technology & Software",
            "type": profile.get("type") or "Privately Held",
            "employees": profile.get("employees"),
            "headquarters": profile.get("headquarters"),
            "slug": company_slug,
        },
        "meta": {
            "source_type": "ats",
            "source_domain": source_domain,
            "ats_source": ats,
            "directapply": True,
            "ats_duplicate": False,
        },
    }

    return standard_obj


_STANDARD_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs_standard (
    source               TEXT NOT NULL,
    source_id            TEXT NOT NULL,
    og_source            TEXT NOT NULL,
    url                  TEXT NOT NULL,
    title                TEXT NOT NULL,
    organization         TEXT NOT NULL,
    organization_logo    TEXT,
    date_posted          TEXT NOT NULL,
    description          TEXT,
    work_arrangement     TEXT,
    location_cities      TEXT,
    location_regions     TEXT,
    location_countries   TEXT,
    salary_currency      TEXT,
    salary_min           REAL,
    salary_max           REAL,
    salary_value         REAL,
    salary_unit          TEXT,
    employment_type      TEXT,
    experience_level     TEXT,
    skills               TEXT,
    benefits             TEXT,
    responsibilities     TEXT,
    requirements         TEXT,
    visa_sponsorship     INTEGER,
    company_industry     TEXT,
    company_type         TEXT,
    company_employees    INTEGER,
    company_headquarters TEXT,
    company_slug         TEXT,
    meta_source_type     TEXT,
    meta_source_domain   TEXT,
    meta_ats_source      TEXT,
    meta_directapply     INTEGER,
    meta_ats_duplicate   INTEGER,
    data_json            TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_std_og ON jobs_standard(og_source);
CREATE INDEX IF NOT EXISTS idx_std_org ON jobs_standard(organization);
CREATE INDEX IF NOT EXISTS idx_std_date ON jobs_standard(date_posted);
"""


def init_standard_table(con: sqlite3.Connection) -> None:
    con.executescript(_STANDARD_SCHEMA_SQL)


def upsert_standard_jobs(jobs: list[dict], db_path: Path) -> int:
    """Upsert standardized jobs into jobs_standard table."""
    con = sqlite3.connect(db_path)
    try:
        init_standard_table(con)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows_to_insert = []

        for j in jobs:
            std = transform_job_to_standard(j)
            loc = std["location"] or {}
            sal = std["salary"] or {}
            co = std["company"] or {}
            meta = std["meta"] or {}

            rows_to_insert.append((
                std["source"],
                std["source_id"],
                std["og_source"],
                std["url"],
                std["title"],
                std["organization"],
                std["organization_logo"],
                std["date_posted"],
                std["description"],
                loc.get("work_arrangement"),
                json.dumps(loc.get("cities") or []),
                json.dumps(loc.get("regions") or []),
                json.dumps(loc.get("countries") or []),
                sal.get("currency"),
                sal.get("min"),
                sal.get("max"),
                sal.get("value"),
                sal.get("unit"),
                json.dumps(std.get("employment_type") or []),
                std.get("experience_level"),
                json.dumps(std.get("skills") or []),
                json.dumps(std.get("benefits") or []),
                std.get("responsibilities"),
                std.get("requirements"),
                1 if std.get("visa_sponsorship") else (0 if std.get("visa_sponsorship") is False else None),
                co.get("industry"),
                co.get("type"),
                co.get("employees"),
                co.get("headquarters"),
                co.get("slug"),
                meta.get("source_type"),
                meta.get("source_domain"),
                meta.get("ats_source"),
                1 if meta.get("directapply") else 0,
                1 if meta.get("ats_duplicate") else 0,
                json.dumps(std, indent=2),
                now,
                now,
            ))

        con.executemany("""
            INSERT INTO jobs_standard (
                source, source_id, og_source, url, title, organization, organization_logo,
                date_posted, description, work_arrangement, location_cities, location_regions,
                location_countries, salary_currency, salary_min, salary_max, salary_value,
                salary_unit, employment_type, experience_level, skills, benefits,
                responsibilities, requirements, visa_sponsorship, company_industry,
                company_type, company_employees, company_headquarters, company_slug,
                meta_source_type, meta_source_domain, meta_ats_source, meta_directapply,
                meta_ats_duplicate, data_json, created_at, updated_at
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
            ON CONFLICT(source, source_id) DO UPDATE SET
                og_source=excluded.og_source,
                url=excluded.url,
                title=excluded.title,
                organization=excluded.organization,
                date_posted=excluded.date_posted,
                description=excluded.description,
                work_arrangement=excluded.work_arrangement,
                location_cities=excluded.location_cities,
                location_regions=excluded.location_regions,
                location_countries=excluded.location_countries,
                salary_currency=excluded.salary_currency,
                salary_min=excluded.salary_min,
                salary_max=excluded.salary_max,
                salary_value=excluded.salary_value,
                salary_unit=excluded.salary_unit,
                employment_type=excluded.employment_type,
                experience_level=excluded.experience_level,
                skills=excluded.skills,
                benefits=excluded.benefits,
                responsibilities=excluded.responsibilities,
                requirements=excluded.requirements,
                company_industry=excluded.company_industry,
                company_type=excluded.company_type,
                company_employees=excluded.company_employees,
                company_headquarters=excluded.company_headquarters,
                company_slug=excluded.company_slug,
                meta_source_domain=excluded.meta_source_domain,
                meta_ats_source=excluded.meta_ats_source,
                data_json=excluded.data_json,
                updated_at=excluded.updated_at
        """, rows_to_insert)

        con.commit()
        return len(rows_to_insert)
    finally:
        con.close()


def sync_all_jobs(db_path: Path = Path("job-boards.db")) -> int:
    """Read all jobs from jobs table, transform to standard schema, and persist."""
    if not db_path.exists():
        return 0

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM jobs")]
    finally:
        con.close()

    count = upsert_standard_jobs(rows, db_path)

    # Also export standard JSON file
    out_file = db_path.parent / "job-boards.standard.json"
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute("SELECT data_json FROM jobs_standard ORDER BY date_posted DESC")
        standard_list = [json.loads(r[0]) for r in cur.fetchall()]
        out_file.write_text(json.dumps(standard_list, indent=2), encoding="utf-8")
    finally:
        con.close()

    print(f"Synchronized {count} jobs into 'jobs_standard' table and exported {out_file.name}.")
    return count


if __name__ == "__main__":
    sync_all_jobs()
