# Literature Verification Rules

## Accept

- Peer-reviewed journal articles.
- Scholarly books or edited volumes from academic publishers.
- Classic foundation papers or books.
- High-citation reviews.
- Original method papers.
- Recent high-quality empirical studies.
- Formally published full conference papers; official policy documents for policy-context claims.
- Official publisher pages, DOI pages, Crossref records, PubMed records, Web of Science records, Scopus records, or journal pages as verification sources.

## Prefer

- SCI Q1 or SSCI Q1 journals where relevant.
- PNAS, Science, Nature family journals, Science Advances, Annual Review journals, Ecology and Society, Global Environmental Change, American Economic Review, and comparable field-leading outlets.
- Recent publications relative to the current date when they directly support the claim; verify publication status as of that date.
- Older sources when they are the original theory, method, or canonical foundation.

## Reject Unless Explicitly Allowed

- arXiv, SSRN, bioRxiv, medRxiv, or other preprints.
- ResearchGate uploads or personal profile copies.
- Blogs, encyclopedia pages, lecture notes, public previews, and unverifiable web pages.
- Conference abstracts, posters, slides, and incomplete proceedings records.
- Items whose title, authors, year, source, pages/article number, DOI, or official URL cannot be confirmed.

## Minimum Metadata

Every final reference must include:

- Stable `id`.
- Reference `type`.
- Full `title`.
- All available `authors`.
- `year`.
- `journal` for articles or `publisher` for books/reports.
- `volume`, `issue`, and `pages` or article number when applicable.
- `doi` or official `url`.
- `verified` set to `true`.

Use `pages` for an article number if the journal uses article IDs.

## Metadata Consistency

- DOI metadata must match the cited record. If a DOI resolves to a reprint, either cite the reprint metadata or use an official URL for the original publication.
- For Ecology and Society and similar article-number journals, record the article number in `pages` when no conventional page range exists.
- If the publisher/Crossref record has no issue number, write `not assigned` in the issue field and keep the verification source. Do not invent an issue.
- Keep ENW, candidate table, insertion mapping, embedded Word field metadata, and visible bibliography text synchronized after any metadata correction.

## Candidate-to-confirmed gate

- Crossref retrieval and fuzzy ENW enrichment produce candidates, not verified references. The DOI fetcher deliberately writes `verified=false`; set true only after reviewing source identity, metadata, and exact claim support. Record a useful verification URL and what it confirmed.
- Inspect titles and every author for replacement characters, mojibake, implausible mixed encodings, HTML residue, and malformed given/family fields. A valid JSON response can still contain corrupted text. Compare suspicious records against the publisher HTML/PDF or official proceedings; do not guess Chinese surnames or mechanically reverse whole names.
- Confirm absent issue numbers against the publisher. `not assigned` is an internal table marker only; ENW writers omit `%N`. Missing volume/pages for genuine online-first publication require an explicitly documented type-appropriate exception, not invented values or a false verified flag. The strict ENW validator may require a scoped adaptation for that exception.
- Confirm journal/conference/report type and publication year. Do not mix a reprint DOI with original-edition metadata or use database creation dates as evidence of publication.
- `crossref_http.py` retries at most twice. An HTTP `IncompleteRead` can be recovered only when the received bytes form complete UTF-8 JSON with a valid message object. Recovery is logged to stderr; preserve that log. Invalid partial JSON is rejected, never patched or padded. DOI retrieval additionally checks that the returned DOI matches the request.
- A network failure may be resolved through another authoritative source. Keep the error record and the alternative verification URL; do not exclude a verified source merely because one API failed.
