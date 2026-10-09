# Content preservation and visual checks

## Before and after comparison

1. Keep a source copy and SHA-256 before any edit. Work on a separate DOCX.
2. Record only already-authorized corrections as JSON: `[{"paragraph_index": 1, "old": "exact original", "new": "exact replacement", "reason": "verified error and evidence"}]`. Indices are 1-based including empty/table paragraphs. Each old substring must match exactly once in its specified paragraph; repeated text needs a more specific anchor.
3. After CWYW, run `check_manuscript_preservation.py --source source.docx --final final.docx --changes authorized_changes.json --report preservation.json`. Omit changes when none were made. An error means inspect the report before claiming preservation.
4. The checker excludes only EndNote citation field content, compares all body paragraph text before a recognized reference heading, and tracks OLE binary hashes and OMML semantic content at paragraph/ordinal/preceding-text anchors. It does not strip ordinary `[n]` notation or normalize whitespace. Do not hide a failed check by adding unauthorized edits to the change list.
5. A prose correction spanning an embedded formula may change its text anchor. Review the formula's intended position explicitly; an authorized prose change does not automatically authorize moving formulas. Retain the discrepancy until resolved or documented with specific evidence.

The checker deliberately reports unsupported nested text-box paragraphs. Headers/footers, footnotes, existing bibliography changes, drawing content, and run formatting need separate inspection. The body boundary assumes an exact `Reference`, `References`, or `参考文献` heading and unchanged paragraph structure. Custom headings, appendices, or legitimate added reference-section spacer paragraphs require a scoped comparison, not broad whitespace deletion. For plain numbered or temporary citations, use the insertion map to remove only the exact inserted text at recorded positions in a comparison copy; the checker does not automatically infer those spans. Verify ordinary numbering separately.

## Formulas and objects

- A count of 16 before and 16 after does not prove preservation. A formula may have been replaced or moved. Compare object relationships, paragraph/order/text anchors, hashes, and visible equations.
- Word may reserialize OLE binaries without visibly changing the equation. Report a binary mismatch as requiring review, not as definitive mathematical corruption. Inspect the equation or MathType payload before deciding.
- Restore original OLE bytes only after verifying a one-to-one correspondence between source and destination objects and confirming no intended formula edits. Do not restore every object by file name alone; Word may renumber relationship IDs and part names.
- Preserve surrounding run properties, tabs, drawings, and objects when splitting text for insertion. Use lxml for OOXML edits to preserve namespace mappings; standard-library XML is suitable for read-only inspection.

## Windows rendering fallback

Use the document skill's renderer when available. If LibreOffice/soffice is absent but Word is installed, do not repeatedly retry the missing executable:

1. Open a task-owned copy read-only in a controlled Word instance using the ownership/timeout rules in `endnote_cwyw.md`.
2. Export with `Document.ExportAsFixedFormat(pdfPath, 17)`; close with no save. This avoids rewriting OLE content merely to obtain a preview.
3. Render that PDF with the configured runtime's pypdfium2 or Poppler. Use the current PDF's page count; stale PNGs from an earlier longer version are not part of the new document.
4. Check all pages at overview size and inspect dense citation pages, equations, the bibliography opening, and the last page at readable resolution. Verify no blank pages, heading-only pages, clipping, displaced equations, or broken reference entries.
5. If CWYW inherited `page_break_before` onto newly added empty/reference paragraphs, fix those specific paragraphs while preserving intended section breaks. Never globally remove page breaks from the manuscript. Re-export after the layout fix.

A PDF can remain an internal QA artifact when the user requests only Word. Text comparison, field validation, and visual inspection are separate checks; none substitutes for the others.
