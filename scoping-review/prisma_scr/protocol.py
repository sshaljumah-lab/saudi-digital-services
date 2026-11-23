"""Review protocol: loading, validation and the default template."""

from __future__ import annotations

from pathlib import Path

import yaml

PROTOCOL_FILE = "protocol.yaml"

TEMPLATE = """\
# PRISMA-ScR scoping review protocol
# Edit this file before running a search. Every field here feeds the
# generated methods section and the PRISMA-ScR checklist.

title: "Digital government services in Saudi Arabia: a scoping review"
authors: ["Author One", "Author Two"]
registration: "OSF: (add registration DOI or 'not registered')"
funding: "(describe funding, or 'none')"

# Population - Concept - Context (JBI framework for scoping reviews)
pcc:
  population: "Citizens, residents, businesses and public-sector employees using or delivering government services"
  concept: "Adoption, use, quality, and outcomes of digital / electronic government services (e-government, m-government, digital transformation)"
  context: "Kingdom of Saudi Arabia, in particular initiatives under Vision 2030 (e.g. Absher, Tawakkalna, Nafath, Yesser)"

objectives:
  - "Map the volume and characteristics of research on Saudi digital government services"
  - "Identify the services, platforms and stakeholder groups studied"
  - "Summarise reported adoption factors, barriers and outcomes"
  - "Identify gaps in the evidence base"

rationale: >
  Saudi Arabia has rapidly expanded digital public services under Vision 2030,
  but the research evidence is dispersed across disciplines. A scoping review
  can map what has been studied and where gaps remain.

eligibility:
  years: [2005, 2026]           # inclusive publication year range
  languages: ["en", "ar"]
  publication_types: ["journal-article", "proceedings-article", "report", "dissertation"]
  inclusion:
    - "Empirical or conceptual study of a digital/electronic government service"
    - "Conducted in, or reporting data specific to, Saudi Arabia"
  exclusion:
    - "Not about government / public services (e.g. purely commercial e-commerce)"
    - "No Saudi-specific data or analysis"
    - "Editorials, letters, or abstracts without full text"

# Reasons offered during full-text screening (shown in the PRISMA flow diagram)
exclusion_reasons:
  - "Wrong concept (not digital government)"
  - "Wrong context (not Saudi Arabia)"
  - "Wrong publication type"
  - "Full text not in eligible language"
  - "Duplicate report of included study"

# Search strategy. Queries are sent verbatim to each database's API.
search:
  date_of_search: null          # filled automatically when you run `search`
  databases:
    openalex:
      enabled: true
      query: '("e-government" OR "electronic government" OR "digital government" OR "m-government" OR "e-services") AND ("Saudi Arabia" OR Saudi OR KSA)'
      max_results: 2000
    crossref:
      enabled: true
      query: 'e-government digital government services Saudi Arabia'
      max_results: 1000
    pubmed:
      enabled: false
      query: '("e-government"[tiab] OR "digital government"[tiab] OR "e-health services"[tiab]) AND "Saudi Arabia"[tiab]'
      max_results: 500
  # Exports you obtain manually (Scopus, Web of Science, IEEE, Google Scholar,
  # grey literature) are added with `prisma-scr import FILE --source NAME`.
  other_sources:
    - "Hand-searching reference lists of included studies"
    - "Saudi Digital Government Authority (DGA) publications"

# Optional: terms used to rank records for screening (not to exclude them).
screening:
  reviewers: ["R1", "R2"]       # one name = single-reviewer screening
  priority_terms: ["saudi", "e-government", "digital government", "absher", "vision 2030", "adoption"]

# Data charting form (one column per field in the charting CSV)
charting:
  fields:
    - {name: study_design, type: category, options: [survey, interview, mixed-methods, case-study, experiment, review, conceptual, other]}
    - {name: service_or_platform, type: text}
    - {name: sector, type: category, options: [health, interior, education, finance, municipal, justice, labour, multi-sector, other]}
    - {name: stakeholder_group, type: category, options: [citizens, residents, businesses, employees, mixed]}
    - {name: sample_size, type: number}
    - {name: theoretical_framework, type: text}
    - {name: key_findings, type: text}
    - {name: barriers, type: text}
    - {name: facilitators, type: text}

# PRISMA-ScR item 12 is optional for scoping reviews.
critical_appraisal: false
"""


def init_project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for sub in ("data", "imports", "screening", "charting", "output"):
        (path / sub).mkdir(exist_ok=True)
    proto = path / PROTOCOL_FILE
    if not proto.exists():
        proto.write_text(TEMPLATE, encoding="utf-8")
    return proto


def load_protocol(project: Path) -> dict:
    proto = project / PROTOCOL_FILE
    if not proto.exists():
        raise SystemExit(f"No {PROTOCOL_FILE} in {project}. Run `prisma-scr init {project}` first.")
    data = yaml.safe_load(proto.read_text(encoding="utf-8")) or {}
    validate(data)
    return data


REQUIRED = ["title", "pcc", "objectives", "eligibility", "search", "charting"]


def validate(p: dict) -> None:
    missing = [k for k in REQUIRED if k not in p]
    if missing:
        raise SystemExit(f"protocol.yaml is missing required keys: {', '.join(missing)}")
    for k in ("population", "concept", "context"):
        if not p["pcc"].get(k):
            raise SystemExit(f"protocol.yaml: pcc.{k} must be set")
    years = p["eligibility"].get("years")
    if years and (len(years) != 2 or years[0] > years[1]):
        raise SystemExit("protocol.yaml: eligibility.years must be [start, end]")


def reviewers(p: dict) -> list[str]:
    return list((p.get("screening") or {}).get("reviewers") or ["R1"])


def save_protocol_field(project: Path, dotted_key: str, value) -> None:
    """Update one field (e.g. search.date_of_search) while keeping comments elsewhere intact
    as far as possible: we rewrite the single matching line if it exists."""
    proto = project / PROTOCOL_FILE
    text = proto.read_text(encoding="utf-8").splitlines()
    leaf = dotted_key.split(".")[-1]
    for i, line in enumerate(text):
        stripped = line.lstrip()
        if stripped.startswith(f"{leaf}:"):
            indent = line[: len(line) - len(stripped)]
            comment = ""
            if "#" in stripped:
                comment = "  #" + stripped.split("#", 1)[1]
            text[i] = f"{indent}{leaf}: {yaml.safe_dump(value, default_flow_style=True).strip()}{comment}"
            proto.write_text("\n".join(text) + "\n", encoding="utf-8")
            return
