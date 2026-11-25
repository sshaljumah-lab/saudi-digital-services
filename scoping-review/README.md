# prisma-scr — run a PRISMA-ScR scoping review from the command line

A small, transparent Python program that takes a scoping review from protocol to
manuscript, following the **PRISMA Extension for Scoping Reviews (PRISMA-ScR)**
(Tricco et al., 2018) and the JBI scoping review methodology.

```
protocol.yaml ─► search / import ─► dedupe ─► title/abstract screening ─► full-text screening
                                                   (2 reviewers, κ, conflicts)     (exclusion reasons)
                                                                                         │
             manuscript.md ◄─ PRISMA-ScR checklist ◄─ flow diagram (SVG) ◄─ data charting
```

The default protocol is a review of **digital government services in Saudi Arabia**.
Change `protocol.yaml` to use it for any topic.

## Install

```bash
cd scoping-review
pip install -e .            # installs the `prisma-scr` command (needs only PyYAML)
# or, without installing:  python -m prisma_scr ...
```

## Workflow

```bash
prisma-scr init my-review           # creates my-review/protocol.yaml and folders
cd my-review
# 1. Edit protocol.yaml: PCC, objectives, eligibility, search strings, charting form

# 2. Identification
export PRISMA_SCR_MAILTO=you@university.edu     # optional, polite API use
prisma-scr search                    # OpenAlex, Crossref, PubMed (whichever are enabled)
prisma-scr import scopus.csv --source Scopus --date 2026-11-20 --query '<string used>'
prisma-scr import savedrecs.txt --source "Web of Science"
prisma-scr import refs.ris --source "Citation searching" --kind other
prisma-scr dedupe --report          # writes data/duplicates.csv so you can check matches

# 3. Title/abstract screening, each reviewer independently
prisma-scr screen export --stage ta --reviewer R1   # -> screening/ta_R1.csv (fill 'decision')
prisma-scr screen import screening/ta_R1.csv --stage ta --reviewer R1
#   ...or screen in the terminal:
prisma-scr screen interactive --stage ta --reviewer R2
prisma-scr screen reconcile --stage ta              # Cohen's kappa + screening/ta_conflicts.csv
prisma-scr screen resolve screening/ta_conflicts.csv --stage ta

# 4. Full-text screening (decision: include / exclude / not_retrieved; reason required to exclude)
prisma-scr screen export --stage ft --reviewer R1
prisma-scr screen import screening/ft_R1.csv --stage ft --reviewer R1
prisma-scr screen reconcile --stage ft

# 5. Data charting
prisma-scr chart export             # charting/charting_form.csv + codebook
prisma-scr chart import charting/charting_form.csv

# 6. Reporting
prisma-scr report
prisma-scr status                   # progress and the suggested next step at any time
```

## Outputs (`output/`)

| File | PRISMA-ScR items |
|---|---|
| `prisma_flow.svg`: flow diagram with counts and full-text exclusion reasons | 14 |
| `manuscript.md`: full draft; methods and results are written from your data, `[AUTHOR]` marks the parts you write | 1–22 |
| `prisma_scr_checklist.md`: all 22 items with where each one is reported and whether it is auto-generated or needs the author | all |
| `flow_counts.json`: raw counts, checked for internal consistency | 14 |

## Design notes

- **Screening files you can audit.** Every decision is stored per reviewer in
  `data/records.json`, and every action is appended to `data/audit_log.jsonl`.
  Searches are logged with date, query and count in `data/search_log.json`.
- **Agreement.** Cohen's κ and percent agreement are computed for the first two
  reviewers at each stage. At title/abstract, *maybe* moves a record on to full text.
  At full text, reviewers must agree on a definite decision or the record goes to
  adjudication. A single reviewer in `screening.reviewers` gives single-reviewer mode.
- **Deduplication.** Records are matched on DOI first, then on normalised title
  similarity (≥ 0.93 by default) with publication years within ±1. The record with the
  richest metadata is kept, and abstracts and DOIs from the dropped copies are merged into it.
- **Ranking for screening.** `screening.priority_terms` changes the order records
  appear in. It never excludes anything.
- **Supported imports:** RIS (Scopus, WoS, EndNote, Zotero, PubMed via citation
  managers), BibTeX, Scopus CSV, Web of Science tab-delimited, and generic CSV with a
  `title` column.

## Tests

```bash
pip install pytest && python -m pytest -q
```

## Reference

Tricco AC, Lillie E, Zarin W, et al. PRISMA Extension for Scoping Reviews (PRISMA-ScR):
Checklist and Explanation. *Ann Intern Med.* 2018;169(7):467-473. doi:10.7326/M18-0850
