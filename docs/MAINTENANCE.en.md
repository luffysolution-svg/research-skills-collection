# Repository Maintenance Guide

English | [简体中文](MAINTENANCE.zh-CN.md)

This repository contains both third-party and repository-original skills. The
maintenance priorities are preserving provenance and licenses, retaining an
installable directory structure, preventing credential leaks, and keeping the
Chinese and English documentation synchronized.

## Repository structure

```text
科研/<category>skills/<source>/<skill>/
开发/<category>skills/<source>/<skill>/
内容创作/<category>skills/<source>/<skill>/
```

`<skill>/SKILL.md` is required. Source directories isolate same-named skills
from different projects and must not be removed merely to shorten paths.
Complete third-party license copies live under `THIRD_PARTY_LICENSES/`.

## Adding an original skill

1. Use a repository-owned source directory such as `luffysolution-skills/`.
2. Preserve the complete directory, including scripts, references, assets,
   and tests.
3. Validate the frontmatter `name`, `description`, and Agent Skills compatibility.
4. Document its purpose and path in both READMEs.
5. Synchronize the Chinese and English documentation.
6. Run structure, encoding, credential, and real-use tests.

Original content must not be listed as a third-party project.
`THIRD_PARTY_NOTICES.md` does not automatically grant a repository-wide
license to original work. Add an explicit `LICENSE` when a public license is intended.

## Adding or updating a third-party skill

1. Record the upstream repository, pinned release or commit, license, and
   retrieval date.
2. Confirm that redistribution is permitted. Exclude content when permission
   cannot be established.
3. Copy the complete skill directory, not only `SKILL.md`.
4. Preserve upstream licenses, notices, attribution, and source links.
5. Put full license text under `THIRD_PARTY_LICENSES/<source>/` and update
   `THIRD_PARTY_NOTICES.md`.
6. Scan nested copies for restricted content, credentials, caches, build
   output, and large files.
7. Update statistics and both language versions of the documentation.

Do not include content whose upstream terms prohibit extraction, retention, or
third-party redistribution. Current exclusions are listed in the
[Third-Party Notices](../THIRD_PARTY_NOTICES.md).

## Documentation synchronization

| Chinese | English |
|---|---|
| `README.md` | `README_EN.md` |
| `docs/INSTALL.zh-CN.md` | `docs/INSTALL.en.md` |
| `docs/MAINTENANCE.zh-CN.md` | `docs/MAINTENANCE.en.md` |

Update both versions whenever installation paths, statistics, commands,
security rules, or license information changes.

## Updating statistics

Count directories containing `SKILL.md`; do not count arbitrary directories.

```bash
python -c "from pathlib import Path; print(sum(1 for _ in Path('.').rglob('SKILL.md')))"
```

PowerShell:

```powershell
(Get-ChildItem -Recurse -Filter SKILL.md -File).Count
```

Regenerate category counts from actual `SKILL.md` parent paths and update both
READMEs. Do not estimate them manually.

## Pre-release validation

### UTF-8 and invalid characters

```bash
python -c "from pathlib import Path; files=list(Path('.').rglob('*.md')); [p.read_text(encoding='utf-8') for p in files]; assert not any('\ufffd' in p.read_text(encoding='utf-8') for p in files); print(len(files), 'Markdown files OK')"
```

Terminal mojibake alone does not prove file corruption. Strict UTF-8 decoding
is authoritative.

### Credentials and private files

```bash
git grep -nEi "(api[_-]?key|secret|token|password)[[:space:]]*[:=][[:space:]]*['\"][^$<{][^'\"]+"
git status --short
```

Review matches manually. Placeholder variable names are acceptable; real
values, `.env` files, personal documents, and conversion output are not.

### Caches and large files

PowerShell:

```powershell
Get-ChildItem -Recurse -Force -Directory |
  Where-Object Name -in '__pycache__','.pytest_cache','.mypy_cache','node_modules'
Get-ChildItem -Recurse -File |
  Where-Object Length -gt 90MB |
  Select-Object FullName,Length
```

POSIX:

```bash
find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name node_modules \)
find . -type f -size +90M -print
```

### Links, formatting, and skill structure

- Verify that all relative Markdown links resolve.
- Run `git diff --check`.
- Run an available Agent Skills validator on every new skill.
- Run each skill's tests and doctor/check scripts.
- For scripted skills, check Windows, macOS/Linux, spaces, and CJK paths.

For `convert-documents-to-markdown`:

```bash
python 科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/document-tools-doctor.py --json
python 科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/task-workspace.py create
```

Run `validate "<path>"` and then `cleanup "<path>"` on the path returned by
`create` to exercise the marker, safety-boundary, and cleanup lifecycle.

## Git and pull-request workflow

1. Create a feature branch from the latest `main`.
2. Stage only the intended files; exclude personal notes and conversion output.
3. Run the complete pre-release validation.
4. Use a scoped commit message.
5. Push the branch and open a PR that records provenance, licenses, count
   changes, and verification results.
6. Recheck the PR file list and GitHub Actions before merging.
7. Verify remote `main` after merge, then clean up the local branch.

Put machine-specific exclusions in `.git/info/exclude`; do not modify the
repository `.gitignore` for personal files.

## Release checklist

- [ ] Every skill root contains `SKILL.md`
- [ ] Provenance and licenses are verified
- [ ] No restricted content, real credentials, caches, or oversized files
- [ ] Chinese and English documentation is synchronized
- [ ] README statistics come from an actual scan
- [ ] Relative links and UTF-8 validation pass
- [ ] New or modified skills have been exercised
- [ ] `git diff --check` passes
- [ ] The PR file scope is correct
