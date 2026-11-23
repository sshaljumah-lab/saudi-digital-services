"""Command-line interface: `python -m prisma_scr <command>` (or `prisma-scr` once installed)."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from . import __version__
from . import charting, dedupe, report, screening
from .importers import import_file
from .protocol import init_project, load_protocol, reviewers, save_protocol_field
from .sources import DISPLAY, ENGINES
from .store import Store

STATS_FILE = "data/screening_stats.json"


def _proj(a) -> Path:
    return Path(a.project).resolve()


# ------------------------------------------------------------------ commands
def cmd_init(a):
    proto = init_project(_proj(a))
    print(f"Created project at {_proj(a)}\nEdit {proto} (PCC, eligibility, search strings, charting form), then run:\n"
          f"  prisma-scr -p {a.project} search      # live API search\n"
          f"  prisma-scr -p {a.project} import FILE --source Scopus")


def cmd_search(a):
    proj = _proj(a)
    p = load_protocol(proj)
    store = Store(proj)
    years = p["eligibility"].get("years")
    today = date.today().isoformat()
    dbs = p["search"].get("databases") or {}
    chosen = a.only or [k for k, v in dbs.items() if v.get("enabled")]
    for key in chosen:
        if key not in ENGINES:
            raise SystemExit(f"Unknown database {key!r}; available: {', '.join(ENGINES)}")
        cfg = dbs.get(key) or {}
        q = cfg.get("query")
        if not q:
            raise SystemExit(f"No query configured for {key} in protocol.yaml")
        print(f"Searching {DISPLAY[key]} ...")
        try:
            recs = ENGINES[key](q, int(cfg.get("max_results", 1000)), years)
        except Exception as e:  # keep going with other databases
            print(f"  ! {DISPLAY[key]} search failed: {e}")
            continue
        for r in recs:
            r["origin"] = "database"
        added = store.add(recs)
        store.log_search({"source": DISPLAY[key], "origin": "database", "date": today, "query": q,
                          "limits": {"years": years}, "n": len(recs), "added": added})
        store.audit("search", source=DISPLAY[key], n=len(recs), added=added)
        print(f"  {len(recs)} records retrieved, {added} new")
    store.save()
    save_protocol_field(proj, "search.date_of_search", today)


def cmd_import(a):
    proj = _proj(a)
    load_protocol(proj)
    store = Store(proj)
    total = 0
    for f in a.files:
        recs = import_file(Path(f), a.source)
        for r in recs:
            r["origin"] = a.kind
        added = store.add(recs)
        total += added
        store.log_search({"source": a.source, "origin": a.kind, "date": a.date or date.today().isoformat(),
                          "query": a.query or "", "file": Path(f).name, "n": len(recs), "added": added})
        store.audit("import", file=str(f), source=a.source, n=len(recs), added=added)
        print(f"{f}: {len(recs)} records parsed, {added} new")
    store.save()
    print(f"Store now holds {len(store.records)} records ({total} added).")


def cmd_dedupe(a):
    store = Store(_proj(a))
    dupes = dedupe.find_duplicates(store.records, threshold=a.threshold)
    for d, keep in dupes.items():
        store.get(d)["duplicate_of"] = keep
    store.audit("dedupe", removed=len(dupes), threshold=a.threshold)
    store.save()
    print(f"Marked {len(dupes)} duplicates. {len(store.unique())} unique records remain.")
    if a.report:
        out = _proj(a) / "data" / "duplicates.csv"
        import csv
        with out.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["duplicate_id", "duplicate_source", "duplicate_title", "kept_id", "kept_source", "kept_title"])
            for d, k in dupes.items():
                rd, rk = store.get(d), store.get(k)
                w.writerow([d, rd["source"], rd["title"], k, rk["source"], rk["title"]])
        print(f"Duplicate pairs written to {out} for manual verification.")


def _stage_reviewer(a, p):
    revs = reviewers(p)
    rv = a.reviewer or revs[0]
    if rv not in revs:
        raise SystemExit(f"Reviewer {rv!r} not in protocol screening.reviewers {revs}")
    return rv


def cmd_screen(a):
    proj = _proj(a)
    p = load_protocol(proj)
    store = Store(proj)
    terms = (p.get("screening") or {}).get("priority_terms") or []
    reasons = p.get("exclusion_reasons") or []
    stage = a.stage
    if a.action == "export":
        rv = _stage_reviewer(a, p)
        out = Path(a.out) if a.out else proj / "screening" / f"{stage}_{rv}.csv"
        n = screening.export_sheet(store, stage, rv, out, terms)
        print(f"Wrote {n} records to {out}\nFill the 'decision' column with include / exclude / maybe"
              + (" / not_retrieved, and 'reason' for exclusions" if stage == "ft" else "") + ".")
        if stage == "ft" and reasons:
            print("Exclusion reasons (you may type the number):")
            for i, r in enumerate(reasons, 1):
                print(f"  {i}. {r}")
    elif a.action == "import":
        rv = _stage_reviewer(a, p)
        n, problems = screening.import_sheet(store, stage, rv, Path(a.file), reasons)
        for pr in problems:
            print("  !", pr)
        store.audit("screen_import", stage=stage, reviewer=rv, n=n, problems=len(problems))
        store.save()
        print(f"Recorded {n} {screening.STAGES[stage]} decisions for {rv}.")
    elif a.action == "interactive":
        rv = _stage_reviewer(a, p)
        try:
            n = screening.interactive(store, stage, rv, terms, reasons, p["eligibility"])
        finally:
            store.save()
        store.audit("screen_interactive", stage=stage, reviewer=rv, n=n)
        store.save()
        print(f"\nSaved {n} decisions.")
    elif a.action == "reconcile":
        stats = screening.reconcile(store, stage, reviewers(p))
        conflicts = stats.pop("conflicts")
        stats["n_conflicts"] = len(conflicts)
        sp = proj / STATS_FILE
        allstats = json.loads(sp.read_text()) if sp.exists() else {}
        allstats[stage] = stats
        sp.write_text(json.dumps(allstats, indent=1))
        store.audit("reconcile", **stats)
        store.save()
        print(f"{screening.STAGES[stage].title()}: {stats['complete']} complete, {stats['pending']} pending, "
              f"{stats['agreed']} agreed, {len(conflicts)} conflicts")
        if stats["kappa"] is not None:
            print(f"Agreement {100 * stats['percent_agreement']:.1f}%, Cohen's kappa = {stats['kappa']:.3f}")
        if conflicts:
            out = proj / "screening" / f"{stage}_conflicts.csv"
            stats["conflicts"] = conflicts
            screening.export_conflicts(stats, reviewers(p), out)
            print(f"Resolve conflicts in {out} (column final_decision), then:\n"
                  f"  prisma-scr -p {a.project} screen resolve --stage {stage} {out}")
    elif a.action == "resolve":
        n = screening.import_adjudication(store, stage, Path(a.file), reasons)
        store.audit("adjudicate", stage=stage, n=n)
        store.save()
        print(f"Recorded {n} adjudicated decisions.")


def cmd_chart(a):
    proj = _proj(a)
    p = load_protocol(proj)
    store = Store(proj)
    fields = p["charting"]["fields"]
    if a.action == "export":
        out = Path(a.out) if a.out else proj / "charting" / "charting_form.csv"
        n = charting.export_form(store, fields, out)
        print(f"Wrote charting form for {n} included sources to {out} (+ codebook).")
    else:
        n, problems = charting.import_form(store, fields, Path(a.file))
        for pr in problems:
            print("  !", pr)
        store.audit("chart_import", n=n, problems=len(problems))
        store.save()
        print(f"Imported charting data for {n} sources.")


def cmd_report(a):
    proj = _proj(a)
    p = load_protocol(proj)
    store = Store(proj)
    out = proj / "output"
    out.mkdir(exist_ok=True)
    c = report.flow_counts(store)
    sp = proj / STATS_FILE
    stats = json.loads(sp.read_text()) if sp.exists() else {}
    (out / "prisma_flow.svg").write_text(report.flow_svg(c, a.title_on_diagram and p["title"] or ""), encoding="utf-8")
    (out / "flow_counts.json").write_text(json.dumps(c, indent=1), encoding="utf-8")
    (out / "prisma_scr_checklist.md").write_text(report.checklist_md(p, c), encoding="utf-8")
    (out / "manuscript.md").write_text(report.manuscript_md(store, p, stats), encoding="utf-8")
    store.audit("report", **{k: v for k, v in c.items() if isinstance(v, int)})
    for issue in report.check_consistency(c):
        print("  ⚠", issue)
    print(f"Wrote {out}/prisma_flow.svg, manuscript.md, prisma_scr_checklist.md, flow_counts.json")
    print(f"Included sources: {c['included']}")


def cmd_status(a):
    proj = _proj(a)
    p = load_protocol(proj)
    store = Store(proj)
    c = report.flow_counts(store)
    revs = reviewers(p)
    print(f"Project: {p['title']}")
    print(f"Records: {c['identified_total']} identified, {c['duplicates']} duplicates, {c['screened']} unique")
    for stage in ("ta", "ft"):
        pool = screening.pool(store, stage)
        per = ", ".join(f"{rv}: {sum(rv in r['screening'][stage] for r in pool)}/{len(pool)}" for rv in revs)
        print(f"{screening.STAGES[stage].title():>15} screening — {per}")
    print(f"Included: {c['included']}  |  charted: {sum(bool(r['charting']) for r in store.included())}")
    nxt = ("import/search" if not store.records else
           "dedupe" if not any(r.get('duplicate_of') for r in store.records) and c['ta_pending'] == c['screened'] else
           "screen --stage ta" if c["ta_pending"] else
           "screen --stage ft" if c["ft_pending"] else
           "chart" if c["included"] and not all(r["charting"] for r in store.included()) else "report")
    print(f"Suggested next step: {nxt}")


def build_parser():
    ap = argparse.ArgumentParser(prog="prisma-scr", description="Run a PRISMA-ScR scoping review end to end.")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("-p", "--project", default=".", help="project directory (default: current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a project with a protocol template")
    s.add_argument("directory", nargs="?", help="project directory (default: -p value)")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("search", help="run the protocol's searches against OpenAlex / Crossref / PubMed")
    s.add_argument("--only", nargs="*", choices=list(ENGINES), help="limit to these databases")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("import", help="import RIS / BibTeX / CSV / WoS exports")
    s.add_argument("files", nargs="+")
    s.add_argument("--source", required=True, help="database or source name, e.g. Scopus")
    s.add_argument("--kind", choices=["database", "other"], default="database",
                   help="'other' for citation searching, websites, experts (shown separately in the flow diagram)")
    s.add_argument("--date", help="date the search was run (YYYY-MM-DD), default today")
    s.add_argument("--query", help="search string used, for the search log")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("dedupe", help="remove duplicate records")
    s.add_argument("--threshold", type=float, default=0.93, help="title similarity threshold (0-1)")
    s.add_argument("--report", action="store_true", help="write data/duplicates.csv for checking")
    s.set_defaults(func=cmd_dedupe)

    s = sub.add_parser("screen", help="screening: export | import | interactive | reconcile | resolve")
    s.add_argument("action", choices=["export", "import", "interactive", "reconcile", "resolve"])
    s.add_argument("file", nargs="?", help="CSV to import / resolve")
    s.add_argument("--stage", choices=["ta", "ft"], default="ta", help="ta = title/abstract, ft = full text")
    s.add_argument("--reviewer", help="reviewer name from protocol (default: first)")
    s.add_argument("--out", help="output CSV path for export")
    s.set_defaults(func=cmd_screen)

    s = sub.add_parser("chart", help="data charting: export form | import completed form")
    s.add_argument("action", choices=["export", "import"])
    s.add_argument("file", nargs="?")
    s.add_argument("--out")
    s.set_defaults(func=cmd_chart)

    s = sub.add_parser("report", help="generate PRISMA-ScR flow diagram, checklist and manuscript draft")
    s.add_argument("--title-on-diagram", action="store_true")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("status", help="show progress and the next step")
    s.set_defaults(func=cmd_status)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "init" and a.directory:
        a.project = a.directory
    if a.cmd in ("screen", "chart") and a.action in ("import", "resolve") and not a.file:
        raise SystemExit(f"`{a.cmd} {a.action}` needs a CSV file argument")
    a.func(a)
    return 0
