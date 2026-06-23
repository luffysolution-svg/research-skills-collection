# Semantic Markdown Asset Renaming Design

## Goal

Extend `convert-documents-to-markdown` with an optional post-processing workflow that replaces opaque MinerU/MarkItDown image names with stable semantic names while preserving every valid Markdown reference.

The feature must work on Windows, macOS, and Linux; support UTF-8 and CJK paths; avoid unnecessary vision API calls; and never modify files unless the user explicitly applies a reviewed rename plan.

## Scope

The first version supports:

- Standard Markdown image links such as `![](images/example.jpg)`.
- Images referenced through HTML `<img src="...">`.
- MinerU `content_list.json`, `content_list_v2.json`, and Markdown-only output.
- JPG, JPEG, PNG, WebP, GIF, BMP, TIFF, and SVG assets.
- One or more Markdown files sharing an asset directory.
- Preview, apply, validation, mapping export, and rollback.

The first version does not:

- Rename unreferenced files by default.
- Rewrite remote HTTP, HTTPS, or data URLs.
- Interpret arbitrary template languages embedded in Markdown.
- Modify source PDFs or Office documents.
- Require Obsidian or any editor-specific API.

## Design principles

1. Treat link integrity as more important than filename quality.
2. Prefer deterministic document metadata over model-generated descriptions.
3. Preserve the original Markdown formatting outside exact link destination spans.
4. Make preview the default and mutation explicit.
5. Keep a content-derived identity suffix so repeated runs remain stable.
6. Validate the complete operation before committing any visible changes.

## Information sources

For each referenced asset, generate naming evidence in this order:

1. MinerU structured output:
   - `image_caption`, `table_caption`, or chart caption;
   - visual `sub_type`;
   - `page_idx` and `bbox`;
   - structured image path.
2. Markdown context:
   - image alt text;
   - adjacent figure/table caption;
   - nearest preceding heading;
   - nearby paragraph text;
   - MinerU `<details>` content associated with the image.
3. Document context:
   - Markdown filename or detected document title;
   - image order within that document.
4. Vision model:
   - use only when the previous evidence cannot produce a meaningful name;
   - pass the image plus concise document context;
   - request a short factual description, not prose.
5. Deterministic fallback:
   - use document stem, asset type, sequence number, and short content hash.

MinerU captions identify text printed near the visual; they are not assumed to be generated visual descriptions.

## Naming policy

Default portable format:

```text
<document-slug>-<type><sequence>-<semantic-slug>-<hash8>.<extension>
```

Examples:

```text
oxidative-reheat-fig01-first-reactor-temperature-profile-4ac394e3.jpg
ethylbenzene-patent-fig01-process-flowchart-95bb8401.jpg
alkylation-study-table03-catalyst-performance-31761195.jpg
```

Rules:

- Use lowercase ASCII kebab-case by default for maximum portability.
- Preserve the original extension unless format conversion is separately requested.
- Restrict the semantic slug to concise, high-information terms.
- Remove Windows-reserved characters, trailing dots/spaces, control characters, path separators, and reserved device names.
- Apply a configurable filename length limit, defaulting to 120 Unicode code points including the extension.
- Include the first eight hexadecimal characters of SHA-256 content identity.
- Preserve stable sequence numbers per document and visual type.
- If one asset is referenced by multiple documents, choose the strongest caption evidence and use a neutral shared prefix when document-specific naming would be misleading.

The short hash is mandatory. It prevents accidental collisions, preserves identity across reruns, and makes rollback diagnostics reliable.

## Asset graph

Build an in-memory graph before producing a plan:

- Markdown document nodes.
- Referenced local asset nodes resolved to canonical filesystem paths.
- Reference edges containing source file, syntax kind, exact destination span, decoded path, and original textual representation.
- Optional MinerU structured-record nodes linked by normalized asset path.

Reject references that resolve outside the selected processing root unless the user explicitly expands the root. Do not follow a symlink outside that root.

Default eligibility:

- Rename only assets with at least one valid local reference.
- Report unreferenced files separately.
- Do not rename missing assets.
- Do not mutate unsupported or ambiguous references.

## Planning interface

Provide a portable Python script:

```text
scripts/rename-markdown-assets.py
```

Primary commands:

```bash
python scripts/rename-markdown-assets.py plan <markdown-root>
python scripts/rename-markdown-assets.py apply <plan.json>
python scripts/rename-markdown-assets.py validate <plan.json>
python scripts/rename-markdown-assets.py rollback <transaction.json>
```

`plan` is read-only and produces:

- `rename-plan.json`: machine-readable plan and evidence.
- `rename-plan.csv`: human-readable old/new mapping.
- console summary of documents, references, eligible assets, skipped assets, conflicts, and vision calls.

Vision analysis is opt-in during planning. The script first reports how many assets require vision. It reads the existing `MARKITDOWN_OCR_API_KEY`, `MARKITDOWN_OCR_BASE_URL`, and `MARKITDOWN_OCR_MODEL` configuration without printing secrets.

## Markdown parsing and rewriting

Use a syntax-aware scanner that records source offsets while preserving the original file bytes:

- Parse standard inline and reference-style Markdown image destinations.
- Parse HTML `<img src>` attributes.
- Ignore fenced code blocks, inline code, comments, and remote URLs.
- Decode percent-encoded paths for resolution but preserve the original encoding style when rewriting.
- Preserve angle-bracket destinations, quote style, alt text, titles, line endings, and all unrelated whitespace.

Do not render an entire Markdown AST back to text because that can reformat tables, embedded HTML, formulas, and MinerU-specific `<details>` blocks. Apply replacements to verified destination spans in descending byte-offset order.

Before writing, confirm the source file hash still matches the hash recorded during planning. A changed Markdown file invalidates the plan.

## Transaction model

Applying a plan uses four phases:

1. Preflight:
   - verify all source files and source hashes;
   - verify every target path stays inside the processing root;
   - verify target-name uniqueness using case-insensitive comparison on Windows and macOS-compatible mode;
   - verify destination paths are not occupied by unrelated files;
   - prepare rewritten Markdown in memory.
2. Stage:
   - rename each asset to a unique temporary name in the same directory;
   - write updated Markdown to temporary sibling files;
   - write a transaction journal after every completed operation.
3. Commit:
   - rename staged assets to final names;
   - atomically replace Markdown files where the platform permits;
   - retain backups until post-commit validation succeeds.
4. Verify and finish:
   - rescan every affected Markdown file;
   - verify every rewritten reference resolves;
   - verify old paths no longer appear in affected reference spans;
   - verify asset hashes are unchanged;
   - finalize `transaction.json` and remove temporary staging files.

On any failure, automatically reverse completed operations using the journal. If automatic rollback is incomplete, stop and report every remaining path without deleting evidence.

## Conflict and duplicate handling

- Same proposed semantic name, different content: retain each mandatory hash suffix.
- Same content, multiple filenames: do not deduplicate automatically; report duplicates and preserve each file unless the user requests deduplication separately.
- Existing target with identical content: report a merge opportunity but do not merge in the first version.
- Existing target with different content: choose another collision-safe name and record the reason.
- Shared asset: update every discovered reference in the selected root in the same transaction.
- Case-only rename: always pass through a temporary filename so Windows and default macOS filesystems handle it correctly.

## Vision request policy

The vision fallback receives:

- a resized copy when the source is unnecessarily large;
- the detected document title;
- nearest heading and adjacent caption text;
- visual type and sequence number.

Expected structured response:

```json
{
  "description": "temperature profile of the first radial flow reactor",
  "keywords": ["temperature", "profile", "first reactor"],
  "confidence": 0.91
}
```

The script validates and normalizes the response. Low-confidence, empty, unsafe, or generic responses fall back to deterministic metadata naming. API failures must not block planning; they produce warnings and fallback names.

Cache vision results by image SHA-256 plus model and prompt-version identifiers so identical images are not billed repeatedly.

## Privacy and secrets

- Never write API keys into plans, transaction files, logs, Markdown, or filenames.
- Record only provider base URL, model name, prompt version, and whether credentials were available.
- State clearly when a configured endpoint is a third-party OpenAI-compatible relay.
- Make vision opt-in because document images may contain sensitive material.

## Testing strategy

Unit tests cover:

- standard Markdown, reference-style links, and HTML image tags;
- parentheses, spaces, percent encoding, CJK names, and mixed line endings;
- fenced code and inline code exclusions;
- shared assets and multiple references;
- case-only renames and reserved Windows names;
- name length, collisions, and stable hash suffixes;
- plan invalidation after source changes;
- transaction rollback at each mutation phase.

Integration tests use a synthetic fixture tree and a copied subset of:

```text
<local-real-fixture-markdown-dir>
```

The current real-world fixture contains 4 Markdown files, 47 unique referenced images, 141 image files, and 94 unreferenced image candidates. Tests must operate on a temporary copy and confirm:

- only the 47 referenced images are eligible by default;
- all 47 rewritten references resolve;
- the 94 unreferenced candidates remain unchanged;
- HTML table-contained image references are detected;
- captions such as `Figure 1. Temperature profile of the first reactor.` produce useful deterministic names without a vision call;
- rollback restores byte-identical Markdown and original asset paths.

## Skill integration

Update `SKILL.md` to route requests such as “rename MinerU images,” “replace hash image names,” or “organize Markdown assets” to the new script.

The conversion workflow remains unchanged unless semantic renaming is explicitly requested. After conversion:

1. preserve final Markdown and referenced assets;
2. run `plan`;
3. show the user the summary and mapping;
4. run `apply` only after explicit confirmation;
5. run `validate`;
6. report the plan, transaction journal, changed files, warnings, and rollback command.

Update `references/engines.md` with the command reference and configuration behavior. Install the same Skill revision into Codex and Claude only after repository tests and validation pass.

## Success criteria

The feature is complete when:

- planning is read-only and deterministic without vision;
- meaningful captions avoid vision calls;
- every mutation has a durable journal and tested rollback;
- Markdown formatting outside link destinations remains byte-identical;
- all supported references resolve after apply;
- no unreferenced asset is changed by default;
- UTF-8, CJK paths, Windows, macOS, and Linux path rules are covered;
- secrets never appear in output artifacts;
- the repository Skill, Codex copy, and Claude copy pass their validation checks.
