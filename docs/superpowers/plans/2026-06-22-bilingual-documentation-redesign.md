# Bilingual Documentation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repository documentation with a matched Chinese/English information architecture for both users and maintainers, then validate and merge the existing Skill PR.

**Architecture:** Keep README files concise and route operational detail into language-specific installation and maintenance guides. Preserve old document paths as compatibility redirects, retain one authoritative third-party notice, and validate counts, links, commands, encoding, and secrets before merge.

**Tech Stack:** Markdown, PowerShell/Python validation commands, Git, GitHub CLI.

---

### Task 1: Rebuild repository entry points

**Files:**
- Modify: `README.md`
- Create: `README_EN.md`

- [x] Write matching Chinese and English README section outlines.
- [x] Add language switches, project positioning, quick start, statistics, category navigation, installation choices, original skills, legal notice, and documentation index.
- [x] Keep long command references out of README files.
- [x] Verify both READMEs contain the same high-level section set.

### Task 2: Rebuild installation documentation

**Files:**
- Create: `docs/INSTALL.zh-CN.md`
- Create: `docs/INSTALL.en.md`
- Modify: `INSTALL-Claude-Code-and-Codex.md`

- [x] Verify current local CLI syntax with `claude plugin --help`, `codex plugin --help`, `npx.cmd skills --help`, and relevant official documentation.
- [x] Write matched platform-neutral installation guides with Windows command notes.
- [x] Cover manual copying, Skills CLI, native plugins, verification, updating, removal, conflicts, and troubleshooting.
- [x] Replace the legacy installation document with links to both new guides.

### Task 3: Rebuild maintenance documentation

**Files:**
- Create: `docs/MAINTENANCE.zh-CN.md`
- Create: `docs/MAINTENANCE.en.md`
- Modify: `UPDATING.md`

- [x] Document categories, source grouping, original versus third-party additions, licenses, restricted content, validation checks, statistics, branches, and PR workflow.
- [x] Include executable validation commands for Windows and POSIX systems.
- [x] Replace the legacy updating document with links to both new guides.

### Task 4: Clarify third-party notices and local exclusions

**Files:**
- Modify: `THIRD_PARTY_NOTICES.md`
- Local-only: `.git/info/exclude`

- [x] Add Chinese navigation text while keeping the authoritative license table in English.
- [x] Clarify that repository-original skills are not third-party content.
- [x] Add `科研Skills分类详细说明.txt` to `.git/info/exclude` without changing repository `.gitignore`.

### Task 5: Validate documentation

**Files:**
- Validate all modified Markdown and the new Skill tree.

- [x] Check UTF-8 decoding and replacement characters.
- [x] Check every local Markdown link resolves.
- [x] Verify total and category counts against the repository tree.
- [x] Verify the Chinese and English document pairs have matched section structures.
- [x] Run secret, cache, large-file, and restricted-license scans.
- [x] Run `git diff --check` and Skill validation.

### Task 6: Publish and merge

**Files:**
- Update Git history and PR #1.

- [ ] Commit documentation changes with scoped paths only.
- [ ] Push the branch.
- [ ] Update the PR title/body to describe both the Skill and documentation redesign.
- [ ] Mark the PR ready for review.
- [ ] Merge PR #1 into `main`.
- [ ] Confirm remote main contains the merged files and local-only notes remain untracked/excluded.
