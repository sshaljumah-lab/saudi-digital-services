"""PRISMA-ScR outputs: flow counts, flow diagram (SVG), checklist and manuscript draft."""

from __future__ import annotations

import html
import textwrap
from collections import Counter
from datetime import date

from .charting import summarise
from .store import Store

# ----------------------------------------------------------------- counts


def flow_counts(store: Store) -> dict:
    allr = store.records
    uniq = store.unique()
    db = Counter(r["source"] for r in allr if r.get("origin", "database") == "database")
    other = Counter(r["source"] for r in allr if r.get("origin") == "other")
    ta_ex = sum(r["ta_final"] == "exclude" for r in uniq)
    ta_pending = sum(r["ta_final"] is None for r in uniq)
    sought = [r for r in uniq if r["ta_final"] == "include"]
    not_retrieved = sum(r["ft_final"] == "not_retrieved" for r in sought)
    assessed = [r for r in sought if r["ft_final"] in ("include", "exclude")]
    ft_pending = sum(r["ft_final"] is None for r in sought)
    reasons = Counter(r["ft_reason"] or "Reason not recorded" for r in assessed if r["ft_final"] == "exclude")
    return {
        "identified_db": dict(db), "identified_db_total": sum(db.values()),
        "identified_other": dict(other), "identified_other_total": sum(other.values()),
        "identified_total": len(allr),
        "duplicates": sum(1 for r in allr if r.get("duplicate_of")),
        "screened": len(uniq), "ta_excluded": ta_ex, "ta_pending": ta_pending,
        "sought": len(sought), "not_retrieved": not_retrieved, "ft_pending": ft_pending,
        "assessed": len(assessed), "ft_excluded": sum(reasons.values()),
        "ft_reasons": dict(reasons.most_common()),
        "included": sum(r["ft_final"] == "include" for r in sought),
    }


def check_consistency(c: dict) -> list[str]:
    issues = []
    if c["identified_total"] - c["duplicates"] != c["screened"]:
        issues.append("identified - duplicates != screened")
    if c["screened"] - c["ta_excluded"] - c["ta_pending"] != c["sought"]:
        issues.append("screened - excluded - pending != sought")
    if c["sought"] - c["not_retrieved"] - c["ft_pending"] != c["assessed"]:
        issues.append("sought - not retrieved - pending != assessed")
    if c["assessed"] - c["ft_excluded"] != c["included"]:
        issues.append("assessed - excluded != included")
    if c["ta_pending"] or c["ft_pending"]:
        issues.append(f"screening incomplete: {c['ta_pending']} title/abstract and "
                      f"{c['ft_pending']} full-text records still pending")
    return issues


# ----------------------------------------------------------------- SVG


def _box(x, y, w, lines, fill="#ffffff", bold_first=False, lh=17):
    h = 16 + lh * len(lines)
    parts = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{fill}" stroke="#333" stroke-width="1.2"/>']
    for i, ln in enumerate(lines):
        weight = ' font-weight="bold"' if bold_first and i == 0 else ""
        parts.append(f'<text x="{x + 10}" y="{y + 20 + i * lh}" xml:space="preserve"{weight}>{html.escape(ln)}</text>')
    return "\n".join(parts), h


def _wrap(s, width):
    return textwrap.wrap(s, width) or [""]


def _arrow(x1, y1, x2, y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#333" stroke-width="1.4" marker-end="url(#ah)"/>'


def flow_svg(c: dict, title: str = "") -> str:
    LX, LW, RX, RW = 60, 400, 520, 360
    els, y = [], 50
    phases = []

    def left(lines, **kw):
        nonlocal y
        s, h = _box(LX, y, LW, lines, **kw)
        els.append(s)
        top = y
        y += h
        return top, h

    def right(top, lines):
        s, h = _box(RX, top, RW, lines, fill="#f6f6f6")
        els.append(s)
        return h

    # Identification
    id_lines = [f"Records identified from databases (n = {c['identified_db_total']})"]
    id_lines += [f"   {k} (n = {v})" for k, v in sorted(c["identified_db"].items())]
    if c["identified_other_total"]:
        id_lines += [f"Records from other sources (n = {c['identified_other_total']})"]
        id_lines += [f"   {k} (n = {v})" for k, v in sorted(c["identified_other"].items())]
    top, h = left(id_lines)
    rh = right(top, ["Records removed before screening:", f"   Duplicate records (n = {c['duplicates']})"])
    els.append(_arrow(LX + LW, top + 25, RX, top + 25))
    phases.append(("Identification", 50, max(h, rh)))
    y = max(top + h, top + rh) + 30
    s0 = y
    els.append(_arrow(LX + LW / 2, y - 30, LX + LW / 2, y))

    # Screening
    top, h = left([f"Records screened (title/abstract) (n = {c['screened']})"])
    ex = [f"Records excluded (n = {c['ta_excluded']})"]
    if c["ta_pending"]:
        ex.append(f"Awaiting screening (n = {c['ta_pending']})")
    right(top, ex)
    els.append(_arrow(LX + LW, top + 20, RX, top + 20))
    y += 30
    els.append(_arrow(LX + LW / 2, y - 30, LX + LW / 2, y))
    top, h = left([f"Reports sought for retrieval (n = {c['sought']})"])
    right(top, [f"Reports not retrieved (n = {c['not_retrieved']})"])
    els.append(_arrow(LX + LW, top + 20, RX, top + 20))
    y += 30
    els.append(_arrow(LX + LW / 2, y - 30, LX + LW / 2, y))
    top, h = left([f"Reports assessed for eligibility (n = {c['assessed']})"])
    ex = [f"Reports excluded (n = {c['ft_excluded']}):"]
    for reason, n in c["ft_reasons"].items():
        wrapped = _wrap(f"{reason} (n = {n})", 44)
        ex += ["   " + wrapped[0]] + ["      " + w for w in wrapped[1:]]
    if c["ft_pending"]:
        ex.append(f"Awaiting full-text decision (n = {c['ft_pending']})")
    rh = right(top, ex)
    els.append(_arrow(LX + LW, top + 20, RX, top + 20))
    y = max(y, top + rh) + 30
    phases.append(("Screening", s0, y - 30 - s0))
    els.append(_arrow(LX + LW / 2, top + h, LX + LW / 2, y))

    # Included
    top, h = left([f"Sources of evidence included in review (n = {c['included']})"], fill="#eaf3ea")
    phases.append(("Included", top, max(h, 90)))
    y = top + max(h, 90) + 20

    for name, py, ph in phases:
        els.append(f'<rect x="10" y="{py}" width="32" height="{ph}" rx="4" fill="#cfe0f3" stroke="#333"/>')
        cx, cy = 26, py + ph / 2
        els.append(f'<text x="{cx}" y="{cy}" transform="rotate(-90 {cx} {cy})" text-anchor="middle" '
                   f'dominant-baseline="middle" font-weight="bold">{name}</text>')

    head = (f'<text x="{LX}" y="28" font-size="15" font-weight="bold">{html.escape(title[:95])}</text>'
            if title else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{y}" viewBox="0 0 900 {y}" '
            f'font-family="Arial, Helvetica, sans-serif" font-size="13">\n'
            '<defs><marker id="ah" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">'
            '<path d="M0,0 L10,4 L0,8 z" fill="#333"/></marker></defs>\n'
            f'<rect width="100%" height="100%" fill="#fff"/>\n{head}\n' + "\n".join(els) + "\n</svg>\n")


# ----------------------------------------------------------------- checklist

# PRISMA-ScR checklist (Tricco et al., Ann Intern Med 2018;169:467-473).
CHECKLIST = [
    ("TITLE", 1, "Title", "Identify the report as a scoping review.", "Title"),
    ("ABSTRACT", 2, "Structured summary", "Provide a structured summary that includes (as applicable): background, "
     "objectives, eligibility criteria, sources of evidence, charting methods, results, and conclusions that relate "
     "to the review questions and objectives.", "Abstract"),
    ("INTRODUCTION", 3, "Rationale", "Describe the rationale for the review in the context of what is already known. "
     "Explain why the review questions/objectives lend themselves to a scoping review approach.", "Introduction"),
    ("INTRODUCTION", 4, "Objectives", "Provide an explicit statement of the questions and objectives being addressed "
     "with reference to their key elements (e.g., population or participants, concepts, and context) or other "
     "relevant key elements used to conceptualize the review questions and/or objectives.", "Introduction › Objectives"),
    ("METHODS", 5, "Protocol and registration", "Indicate whether a review protocol exists; state if and where it can "
     "be accessed (e.g., a Web address); and if available, provide registration information, including the "
     "registration number.", "Methods › Protocol and registration"),
    ("METHODS", 6, "Eligibility criteria", "Specify characteristics of the sources of evidence used as eligibility "
     "criteria (e.g., years considered, language, and publication status), and provide a rationale.",
     "Methods › Eligibility criteria"),
    ("METHODS", 7, "Information sources", "Describe all information sources in the search (e.g., databases with dates "
     "of coverage and contact with authors to identify additional sources), as well as the date the most recent "
     "search was executed.", "Methods › Information sources"),
    ("METHODS", 8, "Search", "Present the full electronic search strategy for at least 1 database, including any "
     "limits used, such that it could be repeated.", "Appendix A: Search strategies"),
    ("METHODS", 9, "Selection of sources of evidence", "State the process for selecting sources of evidence (i.e., "
     "screening and eligibility) included in the scoping review.", "Methods › Selection of sources of evidence"),
    ("METHODS", 10, "Data charting process", "Describe the methods of charting data from the included sources of "
     "evidence (e.g., calibrated forms or forms that have been tested by the team before their use, and whether "
     "data charting was done independently or in duplicate) and any processes for obtaining and confirming data "
     "from investigators.", "Methods › Data charting process"),
    ("METHODS", 11, "Data items", "List and define all variables for which data were sought and any assumptions and "
     "simplifications made.", "Methods › Data items"),
    ("METHODS", 12, "Critical appraisal of individual sources of evidence", "If done, provide a rationale for "
     "conducting a critical appraisal of included sources of evidence; describe the methods used and how this "
     "information was used in any data synthesis (if appropriate).", "Methods › Critical appraisal"),
    ("METHODS", 13, "Synthesis of results", "Describe the methods of handling and summarizing the data that were "
     "charted.", "Methods › Synthesis of results"),
    ("RESULTS", 14, "Selection of sources of evidence", "Give numbers of sources of evidence screened, assessed for "
     "eligibility, and included in the review, with reasons for exclusions at each stage, ideally using a flow "
     "diagram.", "Results › Selection of sources of evidence; Figure 1"),
    ("RESULTS", 15, "Characteristics of sources of evidence", "For each source of evidence, present characteristics "
     "for which data were charted and provide the citations.", "Results › Characteristics; Appendix B"),
    ("RESULTS", 16, "Critical appraisal within sources of evidence", "If done, present data on critical appraisal of "
     "included sources of evidence (see item 12).", "Results › Critical appraisal"),
    ("RESULTS", 17, "Results of individual sources of evidence", "For each included source of evidence, present the "
     "relevant data that were charted that relate to the review questions and objectives.", "Appendix B"),
    ("RESULTS", 18, "Synthesis of results", "Summarize and/or present the charting results as they relate to the "
     "review questions and objectives.", "Results › Synthesis"),
    ("DISCUSSION", 19, "Summary of evidence", "Summarize the main results (including an overview of concepts, themes, "
     "and types of evidence available), link to the review questions and objectives, and consider the relevance "
     "to key groups.", "Discussion › Summary of evidence"),
    ("DISCUSSION", 20, "Limitations", "Discuss the limitations of the scoping review process.", "Discussion › Limitations"),
    ("DISCUSSION", 21, "Conclusions", "Provide a general interpretation of the results with respect to the review "
     "questions and objectives, as well as potential implications and/or next steps.", "Conclusions"),
    ("FUNDING", 22, "Funding", "Describe sources of funding for the included sources of evidence, as well as sources "
     "of funding for the scoping review. Describe the role of the funders of the scoping review.", "Funding"),
]

# Items the program fills from data; the rest need author-written content.
AUTO = {5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 17}
PARTIAL = {1, 2, 4, 18, 22}


def checklist_md(p: dict, c: dict) -> str:
    out = ["# PRISMA-ScR Checklist", "",
           f"Review: *{p['title']}*  ", f"Generated: {date.today().isoformat()}", "",
           "Status key: **auto** = generated from project data; **draft** = scaffold generated, "
           "author must complete; **author** = must be written by the review team; **n/a** = not applicable.", "",
           "| Section | # | Item | Reported in | Status |", "|---|---|---|---|---|"]
    for sec, n, item, _, where in CHECKLIST:
        if n in (12, 16) and not p.get("critical_appraisal"):
            status, where = "n/a", where + " (stated as not performed)"
        elif n in AUTO:
            status = "auto"
        elif n in PARTIAL:
            status = "draft"
        else:
            status = "author"
        if n == 14 and check_consistency(c):
            status = "auto ⚠ incomplete"
        out.append(f"| {sec} | {n} | {item} | {where} | {status} |")
    out += ["", "## Item descriptions", ""]
    for _, n, item, desc, _ in CHECKLIST:
        out.append(f"**{n}. {item}.** {desc}  ")
    out += ["", "*From:* Tricco AC, Lillie E, Zarin W, et al. PRISMA Extension for Scoping Reviews (PRISMA-ScR): "
            "Checklist and Explanation. *Ann Intern Med.* 2018;169(7):467-473. doi:10.7326/M18-0850", ""]
    return "\n".join(out)


# ----------------------------------------------------------------- manuscript


def _pct(n, d):
    return f"{n} ({100 * n / d:.0f}%)" if d else str(n)


def _table(counter: Counter, total: int, label: str) -> list[str]:
    rows = [f"| {label} | n (%) |", "|---|---|"]
    for k, v in counter.most_common():
        rows.append(f"| {k} | {_pct(v, total)} |")
    return rows


def _citation(r: dict) -> str:
    a = r["authors"]
    au = (a[0].split(",")[0] if a else "Anonymous") + (" et al." if len(a) > 2 else (f" & {a[1].split(',')[0]}" if len(a) == 2 else ""))
    doi = f" https://doi.org/{r['doi']}" if r["doi"] else ""
    return f"{au} ({r['year'] or 'n.d.'}). {r['title']}. *{r['venue']}*.{doi}"


def manuscript_md(store: Store, p: dict, stats: dict) -> str:
    c = flow_counts(store)
    fields = p["charting"]["fields"]
    summ = summarise(store, fields)
    elig = p["eligibility"]
    log = store.search_log()
    revs = (p.get("screening") or {}).get("reviewers") or ["R1"]
    pcc = p["pcc"]
    years = elig.get("years") or ["inception", "present"]
    last_search = max((e["date"] for e in log), default=p["search"].get("date_of_search") or "[date]")
    dbs = sorted({e["source"] for e in log if e.get("origin", "database") == "database"})
    others = sorted({e["source"] for e in log if e.get("origin") == "other"})

    def kappa_txt(stage):
        s = stats.get(stage) or {}
        if s.get("kappa") is None:
            return ""
        return (f" Inter-rater agreement was {100 * s['percent_agreement']:.1f}% "
                f"(Cohen's κ = {s['kappa']:.2f}).")

    L = [f"# {p['title']}", "", ", ".join(p.get("authors", [])), "",
         "> Draft generated by `prisma-scr`. Sections marked **[AUTHOR]** need to be written by the review team; "
         "numbers and methods text are generated from project data and should be re-generated after any change.", ""]

    # Abstract
    L += ["## Abstract", "",
          f"**Background:** [AUTHOR] {(p.get('rationale') or '').strip()}", "",
          "**Objectives:** " + "; ".join(p["objectives"]) + ".", "",
          f"**Eligibility criteria:** Sources addressing {pcc['concept'].lower()} among "
          f"{pcc['population'].lower()} in the context of {pcc['context']}, published {years[0]}–{years[1]}.", "",
          f"**Sources of evidence:** {', '.join(dbs + others) or '[sources]'}; last searched {last_search}.", "",
          "**Charting methods:** Data were charted using a standardised form "
          f"({len(fields)} items) developed for this review.", "",
          f"**Results:** Of {c['screened']} unique records screened, {c['assessed']} full-text reports were assessed "
          f"and {c['included']} sources of evidence were included. [AUTHOR: key findings]", "",
          "**Conclusions:** [AUTHOR]", ""]

    # Introduction
    L += ["## Introduction", "", (p.get("rationale") or "").strip(), "",
          "[AUTHOR: expand rationale, summarise existing reviews, and explain why a scoping review "
          "(rather than a systematic review) suits the question.]", "",
          "### Objectives", "",
          "Using the Population–Concept–Context framework, this review addresses:", "",
          f"- **Population:** {pcc['population']}", f"- **Concept:** {pcc['concept']}",
          f"- **Context:** {pcc['context']}", "", "Objectives:", ""]
    L += [f"{i}. {o}" for i, o in enumerate(p["objectives"], 1)] + [""]

    # Methods
    L += ["## Methods", "",
          "This scoping review was conducted following the JBI methodology for scoping reviews and is reported "
          "according to the Preferred Reporting Items for Systematic Reviews and Meta-Analyses extension for "
          "Scoping Reviews (PRISMA-ScR) [Tricco et al., 2018].", "",
          "### Protocol and registration", "", f"{p.get('registration') or '[AUTHOR]'}", "",
          "### Eligibility criteria", "",
          f"Sources were eligible if published between {years[0]} and {years[1]} in "
          f"{', '.join(elig.get('languages', [])) or 'any language'}"
          + (f", as {', '.join(elig['publication_types'])}" if elig.get("publication_types") else "") + ".", "",
          "Inclusion criteria:", ""] + [f"- {x}" for x in elig.get("inclusion", [])] + \
         ["", "Exclusion criteria:", ""] + [f"- {x}" for x in elig.get("exclusion", [])] + \
         ["", "[AUTHOR: rationale for the criteria.]", "",
          "### Information sources", ""]
    if log:
        L += ["| Source | Type | Date searched | Records |", "|---|---|---|---|"]
        for e in log:
            L.append(f"| {e['source']} | {e.get('origin', 'database')} | {e['date']} | {e['n']} |")
        L += ["", f"The most recent search was executed on {last_search}."]
    if p["search"].get("other_sources"):
        L += ["", "Additional sources searched:", ""] + [f"- {o}" for o in p["search"]["other_sources"]]
    L += ["", "The full search strategies are given in Appendix A.", "",
          "### Selection of sources of evidence", "",
          f"Records were imported into the review program and duplicates were removed automatically using DOI "
          f"matching and fuzzy title matching (similarity ≥ 0.93, publication year ±1), removing "
          f"{c['duplicates']} duplicate record{'s' if c['duplicates'] != 1 else ''}. "
          + (f"Titles and abstracts were screened independently by {len(revs)} reviewers ({', '.join(revs)}) "
             "against the eligibility criteria; records marked include or uncertain by both reviewers proceeded "
             "to full-text review, and disagreements were resolved by discussion."
             if len(revs) > 1 else
             f"Titles and abstracts were screened by a single reviewer ({revs[0]}).")
          + kappa_txt("ta") + " Full texts were then assessed independently against the same criteria, with "
          "reasons for exclusion recorded." + kappa_txt("ft"), "",
          "### Data charting process", "",
          "A data-charting form was developed by the team (Appendix C codebook) and piloted on a sample of "
          "included sources. [AUTHOR: state whether charting was done independently, in duplicate, or by one "
          "reviewer with verification, and how authors were contacted.]", "",
          "### Data items", "", "| Item | Type | Allowed values |", "|---|---|---|"]
    for f in fields:
        L.append(f"| {f['name']} | {f.get('type', 'text')} | {', '.join(f.get('options', [])) or 'free text'} |")
    L += ["", "### Critical appraisal", "",
          ("[AUTHOR: describe appraisal tool and rationale.]" if p.get("critical_appraisal") else
           "Consistent with scoping review methodology, critical appraisal of individual sources was not performed."),
          "", "### Synthesis of results", "",
          "Charted data were summarised descriptively using frequency counts for categorical items and "
          "medians/ranges for numeric items. Text items were synthesised narratively. [AUTHOR: describe any "
          "thematic / content analysis.]", ""]

    # Results
    inc = summ["n"]
    L += ["## Results", "", "### Selection of sources of evidence", "",
          f"The searches identified {c['identified_total']} records "
          f"({c['identified_db_total']} from databases"
          + (f", {c['identified_other_total']} from other sources" if c["identified_other_total"] else "")
          + f"). After removing {c['duplicates']} duplicates, {c['screened']} records were screened by title and "
          f"abstract, of which {c['ta_excluded']} were excluded. Of {c['sought']} reports sought, "
          f"{c['not_retrieved']} could not be retrieved; {c['assessed']} full-text reports were assessed and "
          f"{c['ft_excluded']} were excluded. A total of {c['included']} sources of evidence were included "
          "(Figure 1).", "", "![Figure 1. PRISMA-ScR flow diagram](prisma_flow.svg)", "",
          "Reasons for full-text exclusion:", ""]
    L += [f"- {k}: {v}" for k, v in c["ft_reasons"].items()] or ["- none"]
    L += ["", "### Characteristics of sources of evidence", ""]
    if inc:
        yrs = sorted(summ["by_year"])
        if yrs:
            L.append(f"Included sources were published between {yrs[0]} and {yrs[-1]}.")
        L += [""] + _table(Counter({str(k): v for k, v in sorted(summ["by_year"].items())}), inc, "Year") + [""]
        L += _table(summ["by_type"], inc, "Publication type") + [""]
    L += ["### Synthesis of results", ""]
    for name, s in summ["fields"].items():
        if s["type"] == "category":
            L += [f"**{name}**", ""] + _table(s["counts"], inc, name) + [""]
        elif s["type"] == "number" and s.get("n"):
            L += [f"**{name}**: reported in {s['n']} sources; median {s['median']:g} "
                  f"(range {s['min']:g}–{s['max']:g}).", ""]
        elif s["type"] == "text":
            L += [f"**{name}**: reported in {s['reported']}/{inc} sources. [AUTHOR: narrative synthesis]", ""]

    L += ["## Discussion", "", "### Summary of evidence", "", "[AUTHOR]", "",
          "### Limitations", "",
          "[AUTHOR] Consider: database coverage, language restrictions, grey literature, single-reviewer stages, "
          "and the absence of critical appraisal inherent to scoping reviews.", "",
          "## Conclusions", "", "[AUTHOR]", "", "## Funding", "", p.get("funding") or "[AUTHOR]", "",
          "[AUTHOR: funding of included sources, if charted.]", "",
          "## References", "",
          "Tricco AC, Lillie E, Zarin W, et al. PRISMA Extension for Scoping Reviews (PRISMA-ScR): Checklist and "
          "Explanation. Ann Intern Med. 2018;169(7):467-473.", "",
          "Peters MDJ, Marnie C, Tricco AC, et al. Updated methodological guidance for the conduct of scoping "
          "reviews. JBI Evid Synth. 2020;18(10):2119-2126.", "",
          "## Appendix A: Search strategies", ""]
    for name, cfg in (p["search"].get("databases") or {}).items():
        if cfg.get("enabled"):
            L += [f"**{name}** (limits: publication years {years[0]}–{years[1]}; max {cfg.get('max_results')} records)",
                  "", "```", cfg.get("query", ""), "```", ""]
    L += ["## Appendix B: Included sources of evidence", ""]
    fnames = [f["name"] for f in fields if f.get("type") != "text"][:4]
    L += ["| # | Source | " + " | ".join(fnames) + " |", "|---|---|" + "---|" * len(fnames)]
    for i, r in enumerate(sorted(store.included(), key=lambda r: (r["year"] or 0, r["title"])), 1):
        L.append(f"| {i} | {_citation(r)} | " + " | ".join(str(r["charting"].get(n, "")) for n in fnames) + " |")
    L += ["", "## Appendix C: Data charting codebook", "", "See `charting/charting_form_codebook.csv`.", ""]
    return "\n".join(L)
