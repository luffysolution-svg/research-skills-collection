---
name: convert-documents-to-markdown
description: Use when the user asks to convert, parse, extract, OCR, batch-process, or organize PDF, image, DOCX, PPTX, XLSX, HTML, or other document outputs into Markdown, including renaming MinerU hash-named images and updating Markdown asset references.
---

# Convert Documents to Markdown

## Overview

Choose the least expensive engine that preserves the required structure, execute the conversion, then verify the actual Markdown output. Never claim OCR was used merely because plugins were enabled.

## Engine selection

| Input or requirement | Engine |
|---|---|
| Digital PDF, DOCX, PPTX, XLSX, HTML, CSV, JSON | MarkItDown |
| Scanned PDF or images embedded in Office/PDF files | MarkItDown OCR |
| Standalone JPG/PNG text image | Configured vision OCR |
| WAV, MP3, M4A, MP4 speech | MarkItDown audio conversion |
| Legacy `.doc` or `.ppt` | MinerU precision; or convert to DOCX/PPTX first |
| Academic paper, formulas, complex tables, multi-column layout | MinerU |
| User explicitly names an engine | Use that engine |
| Unclear quality | Run a small representative comparison, then choose |

Read [references/engines.md](references/engines.md) before executing commands.

Run `python scripts/document-tools-doctor.py` before the first conversion in a session or whenever an engine/configuration failure occurs. Use the `.ps1` wrapper only on Windows when convenient.

## Workflow

1. Resolve every input path literally; confirm it exists and record size. For PDFs, inspect page count, encryption, extractable-text density, and representative rendered pages.
2. Determine output path. If unspecified, write beside the source as `<stem>.md`; for batch work, create a sibling `markdown/` directory. Never overwrite without explicit permission.
3. Check the selected executable and required credentials before conversion. Follow the credential detection and onboarding rules in the engine reference.
4. Create a per-task workspace with `python scripts/task-workspace.py create` when intermediate files are needed. Put only disposable files there.
5. Convert. Quote paths containing spaces, CJK characters, or shell metacharacters on every platform.
6. Verify:
   - command exited successfully;
   - output exists and is non-empty;
   - UTF-8 decodes without replacement characters;
   - headings, paragraphs, tables, formulas, and page order are plausible;
   - visually compare representative pages for layout-sensitive PDFs.
7. In a `finally`-equivalent step after success or failure, clean the workspace with `python scripts/task-workspace.py cleanup "<workspace>"`, unless the user explicitly asked to retain intermediates.
8. Report engine, output path, page/file count, warnings, and any known recognition errors.

## Temporary file lifecycle

- Copy final Markdown and required assets out of the temporary workspace before cleanup.
- Treat images, formulas, tables, and other files referenced by final MinerU Markdown as final deliverables, not temporary files. Keep them together in the final output directory.
- Delete only the workspace created for the current task. Never delete input files, final outputs, shared output directories, caches owned by another tool, or an unmarked directory.
- If cleanup validation fails, leave the directory untouched and report its path for manual review.
- If the user requests intermediate files, preserve the workspace and report its path.

## Semantic asset renaming

Use `scripts/rename-markdown-assets.py` when the user asks to organize or rename referenced Markdown assets, especially MinerU hash-named image files.

1. Run `python scripts/rename-markdown-assets.py plan "<markdown-root>" --output-dir "<plan-dir>"`.
2. Report the mapping path, counts, missing assets, unreferenced assets, and warnings from the plan.
3. Obtain explicit confirmation before mutating files.
4. Run `python scripts/rename-markdown-assets.py apply "<plan-dir>/rename-plan.json"`.
5. Run `python scripts/rename-markdown-assets.py validate "<plan-dir>/rename-plan.json"`.
6. Retain and report the transaction path so `python scripts/rename-markdown-assets.py rollback "<transaction.json>"` can restore the original names and Markdown references if needed.

- Do not rename unreferenced assets by default.
- Do not use `--vision` unless the user requests it, or deterministic evidence is insufficient and the user approves API use.
- Treat `https://api.ikuncode.cc/` as a third-party OpenAI-compatible relay, not an official OpenAI endpoint.
- Operate on a temporary copy for tests and regressions; never mutate user fixture directories such as shared MinerU output when validating behavior.

## Routing constraints

- Treat `markidown` as `MarkItDown`.
- Plain MarkItDown conversion does not require an API key.
- Audio conversion requires SpeechRecognition dependencies; MP3/M4A/MP4 decoding also requires `ffmpeg` and `ffprobe` on PATH. The built-in transcription uses Google's online recognizer and may require internet access.
- For legacy `.doc` and `.ppt`, prefer MinerU precision because it accepts those formats directly. If MarkItDown is required, preserve the original and convert with LibreOffice headless or manually use Office Save As. Do not assume Pandoc can read binary DOC/PPT, and do not rely on unattended Office COM automation without testing it on that machine.
- MarkItDown OCR only invokes vision for scanned pages or embedded images; digital PDF text may bypass OCR by design.
- Use `scripts/markitdown-ocr-convert.py` as the portable OCR entry point. It supports standalone images plus PDF/DOCX/PPTX/XLSX through the plugin.
- Do not expose API keys in commands, logs, generated Markdown, or skill files.
- If OCR configuration is incomplete, identify only the missing variable names and direct the user to their configured OpenAI-compatible provider. Never describe a third-party relay as an official OpenAI service.
- If `mineru-open-api` is missing, state that MinerU is unavailable and request installation permission before installing it.
- MinerU flash mode requires no Token. Before precision extraction, detect a configured Token; if absent, direct the user to the MinerU official Token page and explain how to configure it.
- MinerU `flash-extract` is limited to 10 MB and 20 pages. It exposes OCR/table/formula flags, but use precision `extract` when those structures must be retained reliably, or for larger documents, batch processing, and non-Markdown output.

## Common mistakes

- Enabling `--use-plugins` without passing an LLM client and assuming OCR occurred.
- Treating terminal mojibake as file corruption; verify by decoding the file as UTF-8.
- Using OCR on clean digital PDFs when direct extraction is faster and more accurate.
- Treating MinerU flash mode as equivalent to precision extraction for complex tables or formulas.
- Delivering output without opening or sampling it.
- Deleting a MinerU asset directory that the delivered Markdown references.
