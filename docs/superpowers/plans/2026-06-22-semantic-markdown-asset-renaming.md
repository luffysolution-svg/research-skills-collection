# Semantic Markdown Asset Renaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, cross-platform post-processing tool that gives referenced MinerU/MarkItDown images stable semantic filenames, updates Markdown references transactionally, and supports validation and rollback.

**Architecture:** Implement one importable Python CLI with focused dataclasses and pure functions for scanning, evidence collection, naming, planning, vision fallback, transaction execution, and rollback. Use byte-preserving destination-span rewrites instead of re-rendering Markdown, store plans and transaction journals as versioned JSON, and keep preview as the default behavior.

**Tech Stack:** Python 3.9+ standard library, `unittest`, optional OpenAI Python client from the existing MarkItDown OCR environment, JSON/CSV artifacts, Git.

---

## File structure

| Path | Responsibility |
|---|---|
| `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py` | Importable implementation and CLI for `plan`, `apply`, `validate`, and `rollback` |
| `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py` | Standard-library unit and synthetic integration tests |
| `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_real_mineru_fixture.py` | Optional regression test against a temporary copy of the existing 4-document MinerU output |
| `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/SKILL.md` | Agent routing and safe workflow instructions |
| `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/references/engines.md` | User-facing command and configuration reference |
| `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/agents/openai.yaml` | UI metadata reflecting asset organization support |

Keep the production implementation in one script because Skills must remain copyable and directly executable. Separate tests by deterministic fixtures versus the machine-specific real MinerU fixture.

### Stable implementation interfaces

Define these dataclasses and functions before later tasks use them:

```python
@dataclass(frozen=True)
class Reference:
    markdown_path: Path
    syntax: str
    start: int
    end: int
    raw_destination: str
    decoded_destination: str
    asset_path: Path
    encoding_style: str


@dataclass
class AssetRecord:
    path: Path
    sha256: str
    references: list[Reference]
    evidence: list[dict[str, object]]
    proposed_name: str = ""
    reason: str = ""


def scan_markdown(path: Path, root: Path) -> list[Reference]: ...
def load_mineru_metadata(root: Path) -> dict[Path, list[dict[str, object]]]: ...
def build_asset_graph(root: Path) -> tuple[list[Path], dict[Path, AssetRecord], list[dict[str, str]]]: ...
def propose_names(root: Path, assets: dict[Path, AssetRecord], metadata: dict[Path, list[dict[str, object]]]) -> None: ...
def create_plan(
    root: Path,
    output_dir: Path,
    use_vision: bool = False,
    vision_analyzer: Callable[..., dict[str, object]] | None = None,
) -> dict[str, object]: ...
def apply_plan(plan_path: Path, fail_after: str | None = None) -> Path: ...
def validate_plan(plan_path: Path) -> list[str]: ...
def rollback_transaction(transaction_path: Path) -> list[str]: ...
def main(argv: list[str] | None = None) -> int: ...
```

Plan schema version: `1`. Transaction schema version: `1`.

---

### Task 1: Establish the test harness and portable naming primitives

**Files:**
- Create: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py`
- Create: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py`

- [ ] **Step 1: Write failing tests for module loading, hashing, slugging, and filename safety**

Create a loader that imports the hyphenated script by path and tests deterministic primitives:

```python
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "rename-markdown-assets.py"
SPEC = importlib.util.spec_from_file_location("rename_markdown_assets", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class NamingTests(unittest.TestCase):
    def test_sha256_file_returns_full_lowercase_digest(self):
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "图像.jpg"
            path.write_bytes(b"asset")
            self.assertEqual(
                MODULE.sha256_file(path),
                hashlib.sha256(b"asset").hexdigest(),
            )

    def test_slugify_uses_portable_ascii_kebab_case(self):
        self.assertEqual(
            MODULE.slugify("Figure 1: First Reactor Temperature Profile"),
            "figure-1-first-reactor-temperature-profile",
        )

    def test_safe_filename_rejects_windows_reserved_names(self):
        self.assertEqual(
            MODULE.safe_filename("CON", ".jpg", "12345678"),
            "asset-12345678.jpg",
        )

    def test_safe_filename_enforces_length_and_hash_suffix(self):
        result = MODULE.safe_filename("a" * 300, ".png", "89abcdef", limit=80)
        self.assertLessEqual(len(result), 80)
        self.assertTrue(result.endswith("-89abcdef.png"))
```

- [ ] **Step 2: Run the tests and verify the missing module fails**

Run:

```powershell
python -m unittest "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py" -v
```

Expected: import failure because `scripts/rename-markdown-assets.py` does not exist.

- [ ] **Step 3: Implement the dataclasses and minimal naming primitives**

Create the script with UTF-8 output setup, the stable dataclasses, and these functions:

```python
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip("-")


def safe_filename(stem: str, suffix: str, hash8: str, limit: int = 120) -> str:
    slug = slugify(stem) or "asset"
    if slug.casefold() in WINDOWS_RESERVED:
        slug = "asset"
    tail = f"-{hash8}{suffix.lower()}"
    available = max(1, limit - len(tail))
    slug = slug[:available].rstrip("-") or "asset"
    return f"{slug}{tail}"
```

Add `main()` with an argument parser that currently exposes `--help` and returns zero; later tasks add subcommands.

- [ ] **Step 4: Run the naming tests**

Run the same `unittest` command.

Expected: 4 tests pass.

- [ ] **Step 5: Commit the naming foundation**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py"
git commit -m "Add semantic asset naming primitives"
```

---

### Task 2: Parse Markdown and HTML image references without reformatting

**Files:**
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py`
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py`

- [ ] **Step 1: Add failing scanner tests**

Add a `MarkdownScannerTests` class with a temporary root and assertions for:

```python
def test_scans_inline_reference_style_and_html_images(self):
    text = (
        '![inline](images/a%20b.jpg "title")\n'
        '![reference][plot]\n'
        '[plot]: <images/c 图.png> "caption"\n'
        '<table><tr><td><img src="images/chart.jpg"/></td></tr></table>\n'
    )
    references = self.write_and_scan(text, ["a b.jpg", "c 图.png", "chart.jpg"])
    self.assertEqual(
        [(r.syntax, r.decoded_destination) for r in references],
        [
            ("markdown-inline", "images/a b.jpg"),
            ("markdown-reference", "images/c 图.png"),
            ("html-img", "images/chart.jpg"),
        ],
    )


def test_ignores_code_comments_remote_urls_and_data_urls(self):
    text = (
        '`![](images/inline.jpg)`\n'
        '```md\n![](images/fenced.jpg)\n```\n'
        '<!-- ![](images/comment.jpg) -->\n'
        '![](https://example.com/a.jpg)\n'
        '![](data:image/png;base64,AAAA)\n'
    )
    self.assertEqual(self.write_and_scan(text, []), [])


def test_records_exact_destination_offsets(self):
    text = '![](images/图 1.jpg)\r\n'
    references = self.write_and_scan(text, ["图 1.jpg"])
    ref = references[0]
    encoded = text.encode("utf-8")
    self.assertEqual(encoded[ref.start:ref.end].decode("utf-8"), "images/图 1.jpg")
```

The helper writes actual asset files below `images/` and calls `scan_markdown(markdown, root)`.

- [ ] **Step 2: Run scanner tests and verify failure**

Run:

```powershell
python -m unittest "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py" -v
```

Expected: failures because `scan_markdown` is absent.

- [ ] **Step 3: Implement byte-offset scanning**

Implement:

```python
def protected_ranges(text: str) -> list[tuple[int, int]]:
    """Return character ranges for fenced code, inline code, and HTML comments."""


def destination_to_asset(
    markdown_path: Path,
    root: Path,
    raw_destination: str,
) -> tuple[str, Path] | None:
    """Reject schemes, decode percent escapes, resolve locally, and enforce root containment."""


def scan_markdown(path: Path, root: Path) -> list[Reference]:
    """Scan UTF-8 text and convert matched character offsets to UTF-8 byte offsets."""
```

Use explicit patterns for:

- inline Markdown images;
- reference definitions used by image reference nodes;
- case-insensitive HTML `<img>` `src` attributes.

Build a character-to-byte-offset table once per file:

```python
byte_offsets = [0]
for char in text:
    byte_offsets.append(byte_offsets[-1] + len(char.encode("utf-8")))
```

Reject absolute paths outside `root`, path traversal, symlinks resolving outside `root`, and unsupported URI schemes. Do not require the target asset to exist during scanning; missing assets are reported by graph construction.

- [ ] **Step 4: Run all scanner and naming tests**

Expected: all tests pass with CRLF, CJK, percent encoding, reference-style syntax, and HTML handled.

- [ ] **Step 5: Commit the scanner**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py"
git commit -m "Parse Markdown asset references safely"
```

---

### Task 3: Build the asset graph and consume MinerU structured metadata

**Files:**
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py`
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py`

- [ ] **Step 1: Add failing graph and metadata tests**

Add tests that construct two Markdown files sharing one image, one missing image, one unreferenced image, and a MinerU `content_list.json`:

```python
def test_graph_tracks_shared_missing_and_unreferenced_assets(self):
    documents, assets, warnings = MODULE.build_asset_graph(self.root)
    shared = (self.root / "images" / "shared.jpg").resolve()
    self.assertEqual(len(assets[shared].references), 2)
    self.assertTrue(any(item["code"] == "missing-asset" for item in warnings))
    self.assertTrue(any(item["code"] == "unreferenced-asset" for item in warnings))


def test_loads_caption_page_bbox_and_type_from_content_list(self):
    metadata = MODULE.load_mineru_metadata(self.root)
    path = (self.root / "images" / "shared.jpg").resolve()
    evidence = metadata[path][0]
    self.assertEqual(evidence["caption"], "Figure 1. Temperature profile")
    self.assertEqual(evidence["page_idx"], 2)
    self.assertEqual(evidence["visual_type"], "image")
```

Also add a `content_list_v2.json` case with a nested `content` object and verify it normalizes to the same evidence keys.

- [ ] **Step 2: Run tests and verify graph functions fail**

Expected: failures for missing `build_asset_graph` and `load_mineru_metadata`.

- [ ] **Step 3: Implement metadata normalization and graph construction**

Implement:

```python
def iter_markdown_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def load_mineru_metadata(root: Path) -> dict[Path, list[dict[str, object]]]:
    """Read both content-list schemas and normalize path, caption, type, page, bbox."""


def build_asset_graph(
    root: Path,
) -> tuple[list[Path], dict[Path, AssetRecord], list[dict[str, str]]]:
    """Collect references, hash existing assets once, and report missing/unreferenced files."""
```

Recognize supported image extensions case-insensitively. Record unreferenced assets only beneath directories containing referenced assets, preventing unrelated repository images from being reported.

- [ ] **Step 4: Run the graph tests**

Expected: graph tests and all earlier tests pass.

- [ ] **Step 5: Commit graph construction**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py"
git commit -m "Build MinerU asset metadata graph"
```

---

### Task 4: Generate deterministic semantic names and read-only plan artifacts

**Files:**
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py`
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py`

- [ ] **Step 1: Add failing evidence-ranking and plan tests**

Cover caption-first behavior, Markdown-context fallback, stable ordering, shared assets, and untouched source files:

```python
def test_caption_avoids_vision_and_generates_expected_name(self):
    metadata = {
        self.image.resolve(): [{
            "caption": "Figure 1. Temperature profile of the first reactor.",
            "visual_type": "image",
            "page_idx": 1,
            "bbox": [1, 2, 3, 4],
            "source": "content_list",
        }]
    }
    assets = self.single_asset_graph()
    MODULE.propose_names(self.root, assets, metadata)
    record = assets[self.image.resolve()]
    self.assertIn("fig01-first-reactor-temperature-profile", record.proposed_name)
    self.assertEqual(record.reason, "mineru-caption")


def test_create_plan_is_read_only_and_writes_json_and_csv(self):
    before = self.snapshot_tree()
    plan = MODULE.create_plan(self.root, self.output, use_vision=False)
    self.assertEqual(before, self.snapshot_tree(exclude=self.output))
    self.assertTrue((self.output / "rename-plan.json").is_file())
    self.assertTrue((self.output / "rename-plan.csv").is_file())
    self.assertEqual(plan["schema"], 1)
    self.assertEqual(plan["summary"]["eligible_assets"], 1)
```

Assert each asset entry includes:

```python
{
    "old_path": "images/hash.jpg",
    "new_path": "images/document-fig01-description-12345678.jpg",
    "sha256": "...",
    "reason": "mineru-caption",
    "references": [...],
    "vision_status": "not-needed",
}
```

- [ ] **Step 2: Run tests and verify plan functions fail**

Expected: failures for missing naming and planning functions.

- [ ] **Step 3: Implement evidence extraction and deterministic planning**

Implement:

```python
def markdown_context(reference: Reference) -> dict[str, str]:
    """Return alt text, nearby caption, nearest heading, and nearby paragraph."""


def choose_evidence(record: AssetRecord, metadata: list[dict[str, object]]) -> tuple[str, str, str]:
    """Return visual type, semantic text, and reason using the documented priority."""


def propose_names(
    root: Path,
    assets: dict[Path, AssetRecord],
    metadata: dict[Path, list[dict[str, object]]],
) -> None:
    """Assign stable sequence, semantic name, reason, and collision-safe hash."""


def create_plan(
    root: Path,
    output_dir: Path,
    use_vision: bool = False,
    vision_analyzer: Callable[..., dict[str, object]] | None = None,
) -> dict[str, object]:
    """Create schema-1 JSON and CSV without mutating Markdown or assets."""
```

Use `fig`, `table`, or `chart` prefixes. Strip leading labels such as `Figure 1`, `Fig. 2`, `图 1`, and `Table 3` from the semantic slug after extracting their number. If no explicit figure number exists, allocate a stable number by document path and reference byte offset.

Write JSON with `ensure_ascii=False`, UTF-8, and LF. Write CSV with `encoding="utf-8-sig"` so spreadsheet software on Windows opens Chinese paths correctly.

- [ ] **Step 4: Run all deterministic plan tests twice**

Run the suite twice and compare generated `rename-plan.json` bytes.

Expected: all tests pass and both plans are byte-identical except a deliberately omitted timestamp. Do not include volatile timestamps in the plan.

- [ ] **Step 5: Commit deterministic planning**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py"
git commit -m "Generate semantic asset rename plans"
```

---

### Task 5: Add optional vision fallback with secure caching

**Files:**
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py`
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py`

- [ ] **Step 1: Add failing tests using an injected fake vision function**

Do not make network calls in automated tests:

```python
def test_vision_runs_only_for_generic_fallback_names(self):
    calls = []

    def fake_vision(path, context, config):
        calls.append(path)
        return {
            "description": "radial flow reactor temperature contour",
            "keywords": ["reactor", "temperature"],
            "confidence": 0.92,
        }

    plan = MODULE.create_plan(
        self.root,
        self.output,
        use_vision=True,
        vision_analyzer=fake_vision,
    )
    self.assertEqual(len(calls), 1)
    self.assertEqual(plan["assets"][0]["vision_status"], "used")


def test_low_confidence_and_failure_use_deterministic_fallback(self):
    for response in (
        {"description": "image", "keywords": [], "confidence": 0.2},
        RuntimeError("provider unavailable"),
    ):
        plan = self.plan_with_fake_response(response)
        self.assertIn(plan["assets"][0]["vision_status"], {"rejected", "failed"})
        self.assertRegex(plan["assets"][0]["new_path"], r"-[0-9a-f]{8}\.")


def test_cache_key_includes_hash_model_and_prompt_version(self):
    key = MODULE.vision_cache_key("a" * 64, "gpt-5.4", "v1")
    self.assertEqual(key, MODULE.vision_cache_key("a" * 64, "gpt-5.4", "v1"))
    self.assertNotEqual(key, MODULE.vision_cache_key("a" * 64, "other", "v1"))
```

- [ ] **Step 2: Run tests and verify vision interfaces fail**

Expected: failures because injected vision support and cache functions are absent.

- [ ] **Step 3: Implement secure provider configuration and vision analysis**

Reuse the configuration behavior from `markitdown-ocr-convert.py`:

```python
VISION_ENV = (
    "MARKITDOWN_OCR_API_KEY",
    "MARKITDOWN_OCR_BASE_URL",
    "MARKITDOWN_OCR_MODEL",
)
PROMPT_VERSION = "semantic-asset-name-v1"


def load_vision_config() -> dict[str, str]:
    """Load process/user variables without logging the API key."""


def vision_cache_key(sha256: str, model: str, prompt_version: str) -> str:
    return hashlib.sha256(f"{sha256}\0{model}\0{prompt_version}".encode()).hexdigest()


def analyze_image_with_vision(
    path: Path,
    context: dict[str, str],
    config: dict[str, str],
) -> dict[str, object]:
    """Send an OpenAI-compatible structured request and validate its JSON response."""
```

Store cache entries in the plan output directory under `.asset-name-cache.json`; do not include API keys. Record `base_url`, model, and prompt version in plan metadata. If the URL is not an OpenAI URL, label it as an OpenAI-compatible endpoint.

Require `use_vision=True` before loading credentials or importing `openai`. If the current Python lacks `openai`, locate and re-execute under the existing MarkItDown pipx environment using the same strategy as `markitdown-ocr-convert.py`.

- [ ] **Step 4: Run tests and a configuration-only check**

Run unit tests, then:

```powershell
python "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" check-vision
```

Expected: reports whether all three variables are configured while hiding every value except base URL classification and model name. It must never print the API key.

- [ ] **Step 5: Commit vision fallback**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py"
git commit -m "Add optional vision asset naming"
```

---

### Task 6: Implement exact link rewriting and transaction-safe apply

**Files:**
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py`
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py`

- [ ] **Step 1: Add failing rewrite and apply tests**

Test byte preservation and successful transaction behavior:

```python
def test_rewrite_changes_only_destination_bytes(self):
    original = (
        b'# Title\r\n\r\n'
        b'![](images/old.jpg "title")\r\n'
        b'<details>\r\nunchanged\r\n</details>\r\n'
    )
    updated = MODULE.rewrite_markdown_bytes(
        original,
        [(len(b'# Title\r\n\r\n![]('), len(b'# Title\r\n\r\n![](images/old.jpg'), b'images/new.jpg')],
    )
    self.assertEqual(
        updated,
        original.replace(b"images/old.jpg", b"images/new.jpg"),
    )


def test_apply_renames_assets_updates_all_references_and_validates(self):
    plan_path = self.create_shared_asset_plan()
    transaction_path = MODULE.apply_plan(plan_path)
    self.assertFalse(self.old_asset.exists())
    self.assertTrue(self.new_asset.exists())
    self.assertEqual(MODULE.validate_plan(plan_path), [])
    journal = json.loads(transaction_path.read_text(encoding="utf-8"))
    self.assertEqual(journal["state"], "committed")


def test_changed_markdown_invalidates_plan_before_mutation(self):
    plan_path = self.create_shared_asset_plan()
    self.markdown.write_text("changed", encoding="utf-8")
    with self.assertRaisesRegex(RuntimeError, "source hash changed"):
        MODULE.apply_plan(plan_path)
    self.assertTrue(self.old_asset.exists())
```

- [ ] **Step 2: Run tests and verify apply functions fail**

Expected: failures for missing rewriting and transaction execution.

- [ ] **Step 3: Implement preflight, staging, commit, and validation**

Implement:

```python
def rewrite_markdown_bytes(
    source: bytes,
    replacements: list[tuple[int, int, bytes]],
) -> bytes:
    for start, end, value in sorted(replacements, reverse=True):
        source = source[:start] + value + source[end:]
    return source


def preflight_plan(plan: dict[str, object], plan_path: Path) -> dict[str, object]:
    """Verify schema, roots, source hashes, targets, collisions, and reference spans."""


def apply_plan(plan_path: Path, fail_after: str | None = None) -> Path:
    """Stage same-directory temporary names and sibling Markdown files, then commit."""


def validate_plan(plan_path: Path) -> list[str]:
    """Rescan affected Markdown, verify targets, hashes, and absence of stale references."""
```

Use temporary names:

```text
.<original-name>.asset-rename-<transaction-id>.tmp
.<markdown-name>.asset-rename-<transaction-id>.tmp
```

Use `os.replace` for atomic sibling replacement. Create byte-identical Markdown backup files while validation is pending. Update `transaction.json` after every filesystem operation using write-to-temp plus `os.replace`.

For URL rewriting:

- preserve percent-encoding if the original destination was percent-encoded;
- preserve raw UTF-8 style otherwise;
- always use `/` in Markdown destinations;
- retain angle brackets and quote delimiters because only the destination span changes.

- [ ] **Step 4: Run apply and validation tests**

Expected: all successful-apply and preflight-rejection tests pass.

- [ ] **Step 5: Commit transaction-safe apply**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py"
git commit -m "Apply asset rename plans transactionally"
```

---

### Task 7: Implement rollback and fault-injection coverage

**Files:**
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py`
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py`

- [ ] **Step 1: Add failing rollback tests for every mutation phase**

Expose an internal test hook:

```python
def apply_plan(plan_path: Path, fail_after: str | None = None) -> Path:
```

Test these checkpoints:

```python
for checkpoint in (
    "asset-staged",
    "markdown-staged",
    "asset-committed",
    "markdown-committed",
):
    with self.subTest(checkpoint=checkpoint):
        fixture = self.new_fixture()
        before = fixture.snapshot()
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            MODULE.apply_plan(fixture.plan_path, fail_after=checkpoint)
        self.assertEqual(fixture.snapshot(), before)
```

Add an explicit rollback-after-success test:

```python
transaction = MODULE.apply_plan(plan_path)
errors = MODULE.rollback_transaction(transaction)
self.assertEqual(errors, [])
self.assertEqual(self.snapshot_tree(), original_snapshot)
```

- [ ] **Step 2: Run tests and confirm rollback failures**

Expected: failures because `fail_after` and rollback are not implemented.

- [ ] **Step 3: Implement journal-driven rollback**

Implement:

```python
def rollback_transaction(transaction_path: Path) -> list[str]:
    """Reverse committed Markdown and asset operations in reverse journal order."""
```

Journal each operation with:

```python
{
    "kind": "rename" | "replace",
    "source": "...",
    "target": "...",
    "backup": "...",
    "status": "completed",
}
```

Automatic rollback inside `apply_plan` must:

1. catch the original exception;
2. persist `state: "rolling-back"`;
3. reverse completed operations;
4. set `state` to `rolled-back` or `rollback-incomplete`;
5. re-raise an error containing the journal path.

Do not delete an incomplete journal, backup, or staged file.

- [ ] **Step 4: Run the fault-injection suite**

Expected: every checkpoint restores byte-identical Markdown, original asset paths, and original asset hashes.

- [ ] **Step 5: Commit rollback support**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py"
git commit -m "Add journaled asset rename rollback"
```

---

### Task 8: Complete the CLI and machine-readable summaries

**Files:**
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py`
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py`

- [ ] **Step 1: Add failing CLI tests**

Call `main([...])` directly and capture output:

```python
def test_plan_is_default_read_only_command(self):
    code = MODULE.main(["plan", str(self.root), "--output-dir", str(self.output), "--json"])
    self.assertEqual(code, 0)
    payload = json.loads(self.stdout.getvalue())
    self.assertEqual(payload["eligible_assets"], 1)


def test_apply_requires_explicit_plan_file(self):
    with self.assertRaises(SystemExit):
        MODULE.main(["apply"])


def test_validate_returns_nonzero_for_broken_reference(self):
    code = MODULE.main(["validate", str(self.plan_path), "--json"])
    self.assertEqual(code, 2)
```

- [ ] **Step 2: Run tests and verify incomplete CLI behavior**

Expected: CLI tests fail because subcommands and JSON summaries are missing.

- [ ] **Step 3: Implement final command surface**

Support:

```text
rename-markdown-assets.py plan ROOT [--output-dir DIR] [--vision] [--json]
rename-markdown-assets.py apply PLAN.json [--json]
rename-markdown-assets.py validate PLAN.json [--json]
rename-markdown-assets.py rollback TRANSACTION.json [--json]
rename-markdown-assets.py check-vision [--json]
```

Exit codes:

- `0`: success;
- `2`: validation, input, configuration, or operation failure;
- `3`: rollback incomplete.

Human output must include counts for documents, unique references, eligible assets, missing assets, unreferenced assets, vision-needed assets, vision calls, and warnings. JSON output must contain the same fields and never contain secret values.

- [ ] **Step 4: Run CLI tests and manual help checks**

Run:

```powershell
python "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" --help
python "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" plan --help
python -m unittest "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py" -v
```

Expected: help renders as UTF-8 and all tests pass.

- [ ] **Step 5: Commit the CLI**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py" "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_rename_markdown_assets.py"
git commit -m "Expose semantic asset rename CLI"
```

---

### Task 9: Add real MinerU fixture regression without modifying user files

**Files:**
- Create: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_real_mineru_fixture.py`

- [ ] **Step 1: Write the machine-specific regression test**

Use an environment override and skip cleanly when absent:

```python
SOURCE = Path(os.environ.get(
    "MARKDOWN_ASSET_REAL_FIXTURE",
    r"<local-real-fixture-markdown-dir>",
))


@unittest.skipUnless(SOURCE.is_dir(), f"real fixture not found: {SOURCE}")
class RealMinerUFixtureTests(unittest.TestCase):
    def test_plan_apply_validate_and_rollback_on_temporary_copy(self):
        with tempfile.TemporaryDirectory() as value:
            copied = Path(value) / "markdown"
            shutil.copytree(SOURCE, copied)
            before = snapshot(copied)
            plan = MODULE.create_plan(copied, Path(value) / "plan", use_vision=False)
            self.assertEqual(plan["summary"]["documents"], 4)
            self.assertEqual(plan["summary"]["eligible_assets"], 47)
            self.assertEqual(plan["summary"]["unreferenced_assets"], 94)
            transaction = MODULE.apply_plan(Path(value) / "plan" / "rename-plan.json")
            self.assertEqual(MODULE.validate_plan(Path(value) / "plan" / "rename-plan.json"), [])
            self.assertEqual(MODULE.rollback_transaction(transaction), [])
            self.assertEqual(snapshot(copied), before)
```

Add a targeted assertion that the image following `Figure 1. Temperature profile of the first reactor.` receives a name containing `fig01-first-reactor-temperature-profile` and has `vision_status == "not-needed"`.

- [ ] **Step 2: Run the real fixture test before production changes**

At this point the test should expose any mismatch in counts, syntax handling, or caption association. If it fails, add a minimal unit test reproducing the mismatch before changing production code.

Run:

```powershell
$env:MARKDOWN_ASSET_REAL_FIXTURE='<local-real-fixture-markdown-dir>'
python -m unittest "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests/test_real_mineru_fixture.py" -v
```

Expected: the source directory remains byte-for-byte unchanged because every operation occurs under `TemporaryDirectory`.

- [ ] **Step 3: Fix only real-fixture discrepancies with new unit coverage**

For each discrepancy:

1. add the smallest synthetic fixture to `test_rename_markdown_assets.py`;
2. run it and observe failure;
3. adjust scanner, context association, or transaction code;
4. rerun both test files.

- [ ] **Step 4: Run all tests and inspect generated mappings**

Run:

```powershell
python -m unittest discover -s "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests" -v
```

Expected: all deterministic and real-fixture tests pass; no file beneath the original local fixture path changes.

- [ ] **Step 5: Commit real-world regression coverage**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests"
git commit -m "Test semantic renaming on MinerU output"
```

---

### Task 10: Integrate the workflow into the Skill

**Files:**
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/SKILL.md`
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/references/engines.md`
- Modify: `科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/agents/openai.yaml`

- [ ] **Step 1: Add a failing documentation contract test**

Add to `test_rename_markdown_assets.py`:

```python
def test_skill_documents_preview_apply_validate_and_rollback(self):
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_ROOT / "references" / "engines.md").read_text(encoding="utf-8")
    for term in (
        "rename-markdown-assets.py plan",
        "rename-markdown-assets.py apply",
        "rename-markdown-assets.py validate",
        "rename-markdown-assets.py rollback",
    ):
        self.assertIn(term, skill + reference)
    self.assertIn("Do not rename unreferenced assets by default", skill)
    self.assertIn("explicit confirmation", skill)
```

- [ ] **Step 2: Run the contract test and verify failure**

Expected: failure because the new workflow is not documented.

- [ ] **Step 3: Update SKILL.md routing and workflow**

Extend the frontmatter description with triggers including:

```yaml
description: Use when the user asks to convert, parse, extract, OCR, batch-process, or organize PDF, image, DOCX, PPTX, XLSX, HTML, or other document outputs into Markdown, including renaming MinerU hash-named images and updating Markdown asset references.
```

Add a concise “Semantic asset renaming” section that requires:

1. run `plan`;
2. report mapping and counts;
3. obtain explicit confirmation;
4. run `apply`;
5. run `validate`;
6. retain the transaction path for rollback.

State:

- Do not rename unreferenced assets by default.
- Do not use vision unless requested or deterministic evidence is insufficient and the user approves API use.
- Treat non-OpenAI provider URLs as OpenAI-compatible endpoints.
- Operate on a temporary copy for tests.

- [ ] **Step 4: Update command reference and UI metadata**

Add complete command examples to `references/engines.md`, including `--vision`, `--json`, plan artifacts, transaction journal, and rollback.

Update `agents/openai.yaml` to valid UTF-8:

```yaml
interface:
  display_name: "文档转 Markdown"
  short_description: "使用 MarkItDown、OCR 或 MinerU 转换并整理文档资源"
  default_prompt: "Use $convert-documents-to-markdown to convert this document into verified Markdown and safely organize referenced assets when requested."
```

- [ ] **Step 5: Run contract tests and Skill validation**

Run:

```powershell
python -m unittest discover -s "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests" -v
python "<skill-creator>/scripts/quick_validate.py" "科研\办公专用skills\luffysolution-skills\convert-documents-to-markdown"
```

Expected: all tests pass and validator reports `Skill is valid!`.

- [ ] **Step 6: Commit Skill integration**

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown"
git commit -m "Document semantic Markdown asset workflow"
```

---

### Task 11: Run security, encoding, and cross-platform checks

**Files:**
- Validate all changed Skill files.

- [ ] **Step 1: Compile Python and run the complete suite**

```powershell
python -m py_compile "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/rename-markdown-assets.py"
python -m unittest discover -s "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests" -v
```

Expected: compilation and all tests pass.

- [ ] **Step 2: Strictly decode changed text as UTF-8**

Run a Python check over the script, tests, `SKILL.md`, `engines.md`, and `openai.yaml`:

```python
for path in changed_paths:
    text = path.read_bytes().decode("utf-8")
    assert "\ufffd" not in text
```

Expected: no decode errors or replacement characters.

- [ ] **Step 3: Scan generated artifacts and logs for secrets**

Generate a plan with a fake API key in the process environment, then search the plan directory and captured output for that exact sentinel:

```powershell
$env:MARKITDOWN_OCR_API_KEY='SECRET-SENTINEL-DO-NOT-WRITE'
python ".../rename-markdown-assets.py" check-vision --json
rg -n --fixed-strings 'SECRET-SENTINEL-DO-NOT-WRITE' "<test-output-directory>"
```

Expected: `rg` finds no matches.

- [ ] **Step 4: Exercise path behavior in platform-neutral tests**

Run tests that monkeypatch platform policy rather than requiring each operating system:

- Windows/macOS-compatible case-insensitive collision detection;
- POSIX case-sensitive mode;
- Windows reserved names;
- `/` Markdown separators independent of `os.sep`;
- CJK roots and filenames;
- symlink escape rejection when symlinks are supported.

Expected: all policy tests pass.

- [ ] **Step 5: Run repository checks**

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files are changed.

- [ ] **Step 6: Commit any verification-driven corrections**

If corrections were required:

```powershell
git add -- "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown"
git commit -m "Harden semantic asset renaming"
```

Do not create an empty commit when no correction was needed.

---

### Task 12: Install the verified revision into Codex and Claude

**Files:**
- Source: `<repo>/科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown`
- Replace local installation: `<codex-home>/skills/convert-documents-to-markdown`
- Replace local installation: `<claude-home>/skills/convert-documents-to-markdown`

- [ ] **Step 1: Verify source and destination paths**

Resolve all three absolute paths and confirm both destinations are exactly beneath their expected `skills` directories. Refuse any computed path outside those roots.

- [ ] **Step 2: Create temporary backups of both installed copies**

Use marked workspaces created by:

```powershell
python "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/task-workspace.py" create
```

Copy each existing installed Skill into the workspace before replacement. Do not delete either installed copy until its backup exists.

- [ ] **Step 3: Replace both installed copies from the repository source**

Use native PowerShell `Copy-Item` and `Remove-Item` with verified literal absolute paths. Keep the operation in PowerShell end-to-end. Exclude `tests/__pycache__` and `.pyc` files, but include the test source files for future maintenance.

- [ ] **Step 4: Validate repository, Codex, and Claude copies**

For each copy:

```powershell
python "<skill-creator>/scripts/quick_validate.py" "<skill-path>"
python "<skill-path>\scripts\rename-markdown-assets.py" --help
python "<skill-path>\scripts\rename-markdown-assets.py" check-vision --json
```

Expected: all three copies validate and expose identical script SHA-256 hashes.

- [ ] **Step 5: Clean temporary backups after successful validation**

Use `task-workspace.py cleanup` only after all three copies pass. If any validation fails, restore from backup and retain the workspace path in the report.

- [ ] **Step 6: Record final verification**

Report:

- repository commit;
- script SHA-256;
- unit and real-fixture test counts;
- Codex and Claude installation paths;
- OCR provider classification without credentials;
- confirmation that the original local fixture was not modified.

---

### Task 13: Final repository verification and publication

**Files:**
- Verify Git history and working tree.

- [ ] **Step 1: Run verification-before-completion checks**

Use `superpowers:verification-before-completion`, then rerun:

```powershell
python -m unittest discover -s "科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/tests" -v
python "<skill-creator>/scripts/quick_validate.py" "科研\办公专用skills/luffysolution-skills/convert-documents-to-markdown"
git diff --check
git status --short
```

Expected: all tests and validation pass; worktree is clean after commits.

- [ ] **Step 2: Review commit scope**

```powershell
git log --oneline 38e74bd..HEAD
git diff --stat 38e74bd..HEAD
```

Expected: only the design, plan, Skill implementation, tests, and Skill documentation are included.

- [ ] **Step 3: Push the feature commits**

```powershell
git push origin main
```

Expected: remote `main` advances to the verified local HEAD. If branch protection rejects direct push, create a feature branch and PR instead of bypassing protection.

- [ ] **Step 4: Confirm remote state**

```powershell
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
```

Expected: hashes match after push or after the approved PR merge.
