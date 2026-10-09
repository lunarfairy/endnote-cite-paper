#!/usr/bin/env python3
"""Fetch Crossref DOI metadata into the reference CSV accepted by build_enw.py."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
import time
import unicodedata
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any
from crossref_http import fetch_json, validate_response


FIELDS = [
    "id",
    "type",
    "authors",
    "year",
    "title",
    "journal",
    "publisher",
    "volume",
    "issue",
    "pages",
    "doi",
    "url",
    "keywords",
    "verified",
    "record_number",
    "verification_source",
]


def read_dois(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        values = []
        for row in rows:
            doi = row.get("doi") or row.get("DOI") or row.get("Doi")
            if doi:
                values.append(doi)
        return clean_dois(values)
    return clean_dois(path.read_text(encoding="utf-8-sig").splitlines())


def clean_dois(values: list[str]) -> list[str]:
    dois: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        if not text or text.startswith("#"):
            continue
        text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text, flags=re.I)
        text = text.strip().rstrip(".,;")
        key = text.lower()
        if key not in seen:
            seen.add(key)
            dois.append(text)
    return dois


def fetch_crossref(doi: str, timeout: int) -> dict[str, Any]:
    url = 'https://api.crossref.org/works/' + urllib.parse.quote(doi, safe='')
    try:
        item = fetch_json(url, timeout=timeout)["message"]
    except (urllib.error.URLError, TimeoutError):
        # Windows environments sometimes have flaky urllib TLS/proxy behavior while curl works.
        proc = subprocess.run(
            ["curl.exe", "--fail", "-sS", "-L", "--max-time", str(timeout), url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout + 5,
        )
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip() or f"curl exit {proc.returncode}")
        item = validate_response(json.loads(proc.stdout))["message"]
    if str(item.get("DOI", "")).lower() != doi.lower():
        raise ValueError(f"Crossref DOI mismatch for {doi}")
    return item


def first_text(values: Any) -> str:
    if isinstance(values, list) and values:
        return html.unescape(str(values[0]).strip())
    return html.unescape(str(values or "").strip())


def year_from(item: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = item.get(key, {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            return str(parts[0][0])
    return ""


def authors_from(item: dict[str, Any]) -> str:
    authors: list[str] = []
    for author in item.get("author", []) or []:
        family = html.unescape(str(author.get("family", "")).strip())
        given = html.unescape(str(author.get("given", "")).strip())
        if family and given:
            authors.append(f"{family}, {given}")
        elif family:
            authors.append(family)
        elif given:
            authors.append(given)
    return ";".join(authors)


def reference_type(crossref_type: str) -> str:
    if crossref_type == "proceedings-article":
        return "Conference Paper"
    if crossref_type in {"book", "monograph"}:
        return "Book"
    if crossref_type == "book-chapter":
        return "Book Section"
    return "Journal Article"


def slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    words = re.findall(r"[a-z0-9]+", normalized)
    return "_".join(words[:5]) or "ref"


def row_from_item(item: dict[str, Any], record_number: int, used_ids: set[str]) -> dict[str, str]:
    title = first_text(item.get("title"))
    base_id = slug(title)[:60]
    rid = base_id
    suffix = 2
    while rid in used_ids:
        rid = f"{base_id}_{suffix}"
        suffix += 1
    used_ids.add(rid)
    kind = reference_type(str(item.get("type", "")))
    journal = first_text(item.get("container-title"))
    publisher = html.unescape(str(item.get("publisher", "")).strip())
    issue = html.unescape(str(item.get("issue", "")).strip())
    if kind == "Journal Article" and not issue:
        issue = "not assigned"
    return {
        "id": rid,
        "type": kind,
        "authors": authors_from(item),
        "year": year_from(item),
        "title": title,
        "journal": journal,
        "publisher": "" if kind == "Journal Article" else publisher,
        "volume": html.unescape(str(item.get("volume", "")).strip()),
        "issue": issue,
        "pages": html.unescape(str(item.get("page") or item.get("article-number") or "").strip()),
        "doi": html.unescape(str(item.get("DOI", "")).strip()),
        "url": html.unescape(str(item.get("URL") or f"https://doi.org/{item.get('DOI', '')}").strip()),
        "keywords": "",
        "verified": "false",
        "record_number": str(record_number),
        "verification_source": "Crossref REST API; pending metadata and sentence-support review",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", type=Path, required=True, help="Text file with one DOI per line, or CSV with doi column")
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--errors", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.1)
    args = parser.parse_args(argv)

    dois = read_dois(args.input)
    rows: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    used_ids: set[str] = set()
    for doi in dois:
        try:
            item = fetch_crossref(doi, args.timeout)
            rows.append(row_from_item(item, len(rows) + 1, used_ids))
            print(f"OK {len(rows):03d} {doi}")
        except Exception as exc:
            errors.append({"doi": doi, "error": str(exc)})
            print(f"ERR {doi}: {exc}")
        time.sleep(args.sleep)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    args.errors.parent.mkdir(parents=True, exist_ok=True)
    args.errors.write_text(json.dumps(errors, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} candidate references (verified=false) to {args.output}")
    print(f"Wrote {len(errors)} fetch errors to {args.errors}")
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
