# Scoping review: alienation in Eliot, Faulkner, and Hurston criticism (1990–2026)

A PRISMA-ScR scoping review that complements the close-reading article *Alienation as
Modernist Form*. That article argues that alienation is a formal principle in the three
texts. This review maps how **the scholarship** has treated alienation in those texts. It
can evidence the article's literature-review claims, and it is publishable on its own.

## Review question

> How has literary scholarship published 1990–2026 conceptualised alienation in *The Waste
> Land*, *The Sound and the Fury*, and *Their Eyes Were Watching God*: which kinds of
> alienation, located in which formal features, through which theoretical frameworks? How
> often are these readings comparative or intersectional?

PCC, eligibility, and the charting form are in [`protocol.yaml`](protocol.yaml). Database
strategies and the pilot search are in [`search_strategies.md`](search_strategies.md).

## Status (2026-11-23)

- OpenAlex searched: 832 identified, 1 duplicate, **831 to screen**. Crossref was trialled and dropped (see `search_strategies.md`).
- Pilot screening sheets (50 records, seed 2026) are exported for R1 and R2.
- Main screening sheets are exported *after* the pilot is imported, so pilot records are not screened twice. Run the subscription-database searches first, then export.
- Screening sheets carry advisory `flags` (book reviews, ineligible language, no focal term). Flagged records are listed last. Reviewers still decide every record.

## Pilot search (2026-11-23)

The OpenAlex title/abstract search returned **490 records** (1990–2026, 363 journal
articles), mixed in precision. MLA International Bibliography must be the core database.
Full search estimate: 1,500–3,000 records before deduplication.

## Workflow (run from this folder)

| Step | Command | PRISMA-ScR items |
|---|---|---|
| 0. Register protocol on OSF (draft: `prisma-scr protocol` → `output/protocol_registration.md`); librarian peer-reviews MLA IB strategy | `prisma-scr protocol` | 5 |
| 1. Search OpenAlex + Crossref | `prisma-scr search` | 7, 8 |
| 2. Import MLA IB, JSTOR, MUSE, WoS, Scopus, ProQuest exports | `prisma-scr import FILE --source "MLA IB" --date … --query '…'` | 7, 8 |
| 3. Deduplicate and check matches | `prisma-scr dedupe --report` | 14 |
| 4. Pilot screening: both reviewers screen the same 50 records (`screening/ta_pilot_R1.csv`, `ta_pilot_R2.csv`, already exported), import, reconcile, discuss, refine criteria | `prisma-scr screen import screening/ta_pilot_R1.csv --stage ta --reviewer R1`, then `screen reconcile --stage ta` | 9 |
| 5. Title/abstract screening (independent, dual) | `screen import` / `screen interactive`, then `screen reconcile --stage ta` | 9, 14 |
| 6. Full-text screening with exclusion reasons | `--stage ft` | 9, 14 |
| 7. Citation searching of included sources; import with `--kind other` | `prisma-scr import refs.ris --source "Citation searching" --kind other` | 7, 14 |
| 8. Data charting (pilot the form on 5 sources, then chart; second reviewer verifies 20%) | `prisma-scr chart export` / `chart import` | 10, 11 |
| 9. Report | `prisma-scr report` → `output/` | 1–22 |

## Planned manuscript structure

1. **Introduction:** alienation as a critical keyword; the divided Eliot, Faulkner, and Hurston
   subfields; why a scoping review fits.
2. **Methods:** JBI and PRISMA-ScR; protocol registration; eligibility (PCC); sources and
   search; dual screening with κ; charting form (Appendix); descriptive and qualitative
   content synthesis. No critical appraisal, as is standard for scoping reviews.
3. **Results:**
   - selection (PRISMA-ScR flow diagram);
   - characteristics (by year, venue, source type, focal text);
   - conceptions of alienation × focal text (matrix);
   - formal locus × focal text;
   - frameworks over time (1990s vs 2000s vs 2010s+);
   - comparative and intersectional readings.
4. **Discussion:**
   - what "alienation" means across the subfields;
   - where race, gender, and class enter, and where they do not;
   - gaps: reception studies, cross-text comparison, disability-studies readings of Benjy,
     dialect beyond Hurston.
   - Limitations: English only; database indexing of humanities abstracts; interpretive
     judgement in charting.
5. **Conclusion:** implications for modernist studies and for the companion article.

## Sequencing with the article

Submit the corrected close-reading article first, or hold it until the review's results are
in so its section 2 can cite them. The review will also show whether the article's claim that
these texts have rarely been read together holds up.
