# Word and EndNote CWYW workflow

This file applies to editable EndNote output. Ordinary Word references do not require CWYW.

## Check and isolate

- Run `check_endnote_environment.ps1` for executable/registry discovery. Registry presence proves installation, not successful formatting.
- Use `-ProbeCom` only when useful, under an external timeout. A COM call can block on an invisible modal dialog; `DisplayAlerts=0` does not suppress EndNote dialogs.
- Snapshot existing Word processes/documents. Create a uniquely named task copy and log input/output paths, process identity, and the current operation before a potentially blocking call.
- Do not attach to a user's existing Word session just to avoid creating a task-owned instance. Do not close, save, quit, or terminate unrelated documents/processes.
- A new COM application object alone is not proof of process ownership. Resolve its window handle to the actual PID, compare with the preexisting PID set, and confirm document ownership before cleanup.
- Launch any background PowerShell helper with `-WindowStyle Hidden`. Use a parent process to enforce a bounded operation timeout and poll in intervals no longer than 60 seconds. Log stages such as created/opened/formatting/saved/exported so a timeout identifies the blocked action. Do not block the conversation while waiting.
- Use try/finally for task-document Close and COM release. Quit only an instance verified to contain no unrelated documents. After a timeout, terminate a Word process only if its identity and exclusive task ownership are proven; otherwise report the remaining dialog/lock for targeted handling.

## Import and resolve

- Import the verified ENW into a task-specific library using EndNote Import and UTF-8.
- Check count and actual record numbers. Generated `record_map.csv` numbers are provisional; library import order is not proof of `#RecordNumber`.
- Keep the matching library open. A group can be `{Author, 2020 #1;Other, 2021 #2}`; normally 1–3 references and at most 5 unless the user explicitly specifies another limit.
- If a matching dialog appears, inspect the record identity and fix the mapping/library. Do not repeatedly retry the same unresolved temporary citation or blindly click the first search result.
- Existing native fields may carry travelling-library metadata and remain valid without a freshly imported library. Preserve and validate those fields instead of rebuilding merely because no record map is available.

## Style and native formatting

- Set the requested output style explicitly. For generic numbered output use `Numbered`; it is not automatically GB/T 7714. The application's current default style may differ from the document's style.
- Prefer Word's EndNote tab, Update Citations and Bibliography. On the tested X9 installation, `Word.Application.Run('ENFormatBibliography')` was the working macro. Macro names are version-dependent; verify on a small task copy before using another installation.
- Do not assume `EndNoteFormatBib`, `ENUpdateBibliography`, or `ENWFormatBibliography` exists. A missing-macro error calls for discovering the actual installed command, not cycling speculative names.
- Save to a new DOCX after native formatting. Retain a known-good fielded baseline until the new copy passes field, preservation, and visual checks.
- Nested `ADDIN EN.CITE.DATA` is a native payload container. Base64 `w:fldData` may contain a trailing null byte. It is not an additional citation group.
- Valid marker balance alone is insufficient: validate embedded records, visible bibliography, numbering order, and sentence-to-reference correspondence. Use the current installed `inspect_docx_fields.py`.

## Locks, dialogs, and stalled runs

1. Read the last logged stage and inspect the task-owned window/dialog before launching anything else.
2. If a task copy is locked, locate the owner; use a fresh task copy when appropriate. Do not remove lock files or kill all WINWORD/EndNote processes.
3. Known reference-matching dialogs require bibliographic resolution. Promotion, recovery, add-in, or other dialogs require identifying the exact condition; do not perform blind coordinate clicks or accept unknown actions.
4. Do not globally disable unrelated add-ins or change their registry LoadBehavior to make automation easier. For an evidenced add-in conflict, isolate the task and record/restore any temporary setting change in finally.
5. If automation remains blocked, state the exact remaining UI step. Do not claim fields are absent when a structural inspection shows they exist, or declare successful CWYW just because ENW import worked.

The environment probe does not itself provide a complete unattended formatting controller. These ownership and timeout steps must be implemented by the task's worker when automating; otherwise use the interactive workflow. Never claim all modal-dialog cases are handled.

## Delivery gate

For EndNote mode, retain citation and bibliography fields; do not Convert to Plain Text. Run strict field validation, body/formula comparison, and PDF visual review after the final save.

If visible results are adjusted manually while preserving fields, label the output `fielded-numbered-preview fallback`. This is not proof of native style regeneration. Revalidate and disclose the exact limitation. If the user only wants ordinary numbered Word references, assess against that mode rather than demanding editable fields.

