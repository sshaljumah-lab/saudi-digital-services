# Search strategies — Alienation in Eliot, Faulkner, Hurston criticism (scoping review)

Run every search on the same day where possible. Log each one when importing:
`prisma-scr import FILE --source "<Database>" --date YYYY-MM-DD --query '<string>'`.
That log becomes PRISMA-ScR items 7–8 (information sources and search) automatically.

Limits for all databases: publication years 1990–2026, English. Record the coverage dates
each platform reports.

## Concept blocks

| Block | Terms |
|---|---|
| A. Alienation | alienat\*, estrang\*, isolat\*, displac\*, exclu\*, marginal\*, outsider\*, deracinat\*, exile\*, "not at home" |
| B. Focal texts / authors | "Waste Land", "T. S. Eliot" / "T.S. Eliot", "Sound and the Fury", Faulkner, Compson, Benjy, Quentin, "Their Eyes Were Watching God", Hurston, Janie |

Final string = A AND B. In MLA IB, also run block B with the subject-heading approach below.
That catches criticism indexed by subject that never uses "alienation" in its title.

## 1. MLA International Bibliography (EBSCOhost): primary database

```
S1  DE "Eliot, T. S. (1888-1965)" OR TI "Waste Land" OR SU "Waste Land"
S2  DE "Faulkner, William (1897-1962)" OR TI "Sound and the Fury" OR SU "Sound and the Fury"
S3  DE "Hurston, Zora Neale (1891-1960)" OR TI "Their Eyes Were Watching God" OR SU "Their Eyes Were Watching God"
S4  S1 OR S2 OR S3
S5  TI (alienat* OR estrang* OR isolat* OR displac* OR exclu* OR marginal* OR outsider* OR exile*)
    OR AB (alienat* OR estrang* OR isolat* OR displac* OR exclu* OR marginal* OR outsider* OR exile*)
    OR SU (alienation OR estrangement OR isolation OR exile OR marginality OR displacement)
S6  S4 AND S5
Limiters: Publication Date 1990-2026; Language: English;
          Publication Type: Journal Article, Book, Book Article, Dissertation Abstract
```
Check the exact subject-heading forms in the EBSCO thesaurus: the life dates in author
headings are what make the DE field match. Export everything as RIS.

## 2. JSTOR (Advanced search; export citations as RIS)

```
(ti:("Waste Land" OR "Sound and the Fury" OR "Their Eyes Were Watching God") OR ab:(...same...))
AND (alienation OR alienated OR estrangement OR estranged)
Discipline: Language & Literature; Content type: Journals, Books; 1990-2026
```
JSTOR searches full text by default. Confine the concept terms to title and abstract where
the interface allows, otherwise expect very high recall and low precision.

## 3. Project MUSE (Advanced search; export RIS)

```
("Waste Land" OR "Sound and the Fury" OR "Their Eyes Were Watching God" OR Hurston OR Faulkner OR "T. S. Eliot")
AND (alienation OR estrangement)        [field: Title/Abstract where available]
Filters: Research Area = Literature; Content = Articles, Chapters; 1990-2026
```

## 4. Web of Science Core Collection (A&HCI). Export as tab-delimited "Full Record"

```
TS=(alienat* OR estrang* OR isolat* OR displac* OR exclu* OR marginal* OR outsider* OR exile*)
AND TS=("Waste Land" OR "T. S. Eliot" OR "T.S. Eliot" OR "Sound and the Fury" OR Faulkner
        OR "Their Eyes Were Watching God" OR Hurston)
Indexes: A&HCI; Timespan: 1990-2026; Language: English
```

## 5. Scopus. Export as CSV (all fields)

```
TITLE-ABS-KEY((alienat* OR estrang* OR isolat* OR displac* OR exclu* OR marginal* OR outsider* OR exile*)
 AND ("Waste Land" OR "T. S. Eliot" OR "Sound and the Fury" OR Faulkner
      OR "Their Eyes Were Watching God" OR Hurston))
AND PUBYEAR > 1989 AND LANGUAGE(english) AND SUBJAREA(ARTS)
```

## 6. ProQuest Dissertations & Theses Global. Export RIS

```
ti,ab(alienat* OR estrang* OR isolat* OR displac* OR exile*) AND
ti,ab,su("Waste Land" OR "Sound and the Fury" OR "Their Eyes Were Watching God" OR Faulkner OR Hurston OR "T. S. Eliot")
Date: 1990-2026; Manuscript type: Doctoral dissertations
```

## 7. OpenAlex and Crossref (run by the program: `prisma-scr search`)

Strings are in `protocol.yaml`. Pilot run (2026-11-23), title/abstract, 1990–2026:

| String | Records |
|---|---|
| (alienation OR estrangement OR isolation OR displacement OR exclusion) AND (Eliot OR Faulkner OR Hurston) | 1,337 (noisy: "Eliot" matches George Eliot) |
| (alienation OR alienated OR estrangement OR estranged) AND ("T. S. Eliot" OR "Waste Land" OR Faulkner OR "Sound and the Fury" OR Hurston OR "Their Eyes Were Watching God") | 490 (363 articles) |

The top results of the second string mix relevant items with noise, such as Paquet's
*Callaloo* article (relevant) next to marketing and Brodsky papers (noise). OpenAlex
abstract coverage for literary studies is thin, so it supplements MLA IB and cannot
replace it. Expect roughly 1,500–3,000 records across all sources before deduplication.

## Peer review of the search

Have a subject librarian review the MLA IB strategy (PRESS checklist; McGowan et al., 2016)
before running the final searches. Record the review in the protocol.
