# Research Skills Collection

English | [简体中文](README.md)

A categorized collection of Agent Skills for research, software development,
and content creation. It contains complete skill directories for Claude Code,
Codex, and other tools that support the Agent Skills standard.

The current version contains **241 skills**: 240 from 16 upstream projects and
1 original skill maintained in this repository.

## What this repository is for

- Organize skills from multiple repositories by real-world task.
- Preserve each skill's `SKILL.md`, scripts, references, and assets.
- Isolate same-named skills from different upstream sources.
- Document installation for Claude Code, Codex, and the Skills CLI.
- Provide a maintained home for original skills.

This repository is not a single runtime skills directory. Install the innermost
folder that contains `SKILL.md`; do not copy `科研/`, `开发/`, or `内容创作/`
directly into an agent's skills folder.

## Quick start

### Install the repository-original document conversion skill

```bash
npx skills add luffysolution-svg/research-skills-collection \
  --skill convert-documents-to-markdown \
  --agent claude-code codex \
  --global --copy --full-depth --yes
```

On Windows PowerShell, use `npx.cmd` if execution policy blocks `npx.ps1`.

For manual installation, copy:

```text
科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/
```

to `~/.claude/skills/` for Claude Code or `~/.agents/skills/` for Codex.

See the [English installation guide](docs/INSTALL.en.md) for full details.

## Category navigation

| Category | Count | Main focus |
|---|---:|---|
| Research / literature search and citation | 13 | Search, databases, citations, evidence |
| Research / literature writing | 13 | Papers, editing, patents, templates |
| Research / figures | 20 | Charts, schematics, posters, presentations |
| Research / data analysis | 27 | Statistics, machine learning, data frameworks |
| Research / biology | 49 | Bioinformatics, omics, imaging, lab data |
| Research / chemistry | 12 | Molecules, materials, computational chemistry |
| Research / environment | 2 | Environmental data and analysis |
| Research / materials | 1 | Materials science |
| Research / office tools | 24 | Documents, spreadsheets, slides, conversion |
| Research / ideation | 7 | Hypotheses, study design, brainstorming |
| Research / review | 7 | Peer review, quality, compliance |
| Research / reference management | 13 | Zotero, knowledge bases, lab records |
| Research / physics and quantum | 5 | Physics and quantum tools |
| Research / fiscal and economics | 1 | Fiscal and economic data |
| Research / compute infrastructure | 2 | Cloud and task execution |
| Development / frontend design | 17 | UI, visual design, frontend implementation |
| Development / agents and skills | 7 | Agents, MCP, skills, release workflows |
| Development / technical knowledge | 4 | Technical documentation and retrieval |
| Content / topic and trend research | 1 | Trends and topic discovery |
| Content / perspectives and expression | 16 | Mental models and content writing |

Directory convention:

```text
科研/<category>skills/<source>/<skill>/
开发/<category>skills/<source>/<skill>/
内容创作/<category>skills/<source>/<skill>/
```

## Installation options

| Method | Best for |
|---|---|
| Skills CLI | Installing selected skills for one or more agents |
| Manual copy | Installing one skill with full file control |
| Platform plugin | Upstream projects that publish Claude Code or Codex plugins |
| Repository skill | Team workflows under `.claude/skills/` or `.agents/skills/` |

Documentation:

- [English installation guide](docs/INSTALL.en.md)
- [中文安装指南](docs/INSTALL.zh-CN.md)
- [English maintenance guide](docs/MAINTENANCE.en.md)
- [中文维护指南](docs/MAINTENANCE.zh-CN.md)

## Repository-original skills

### `convert-documents-to-markdown`

Selects MarkItDown, vision OCR, or MinerU to convert PDFs, Office documents,
images, and audio into verified Markdown. It includes cross-platform dependency
diagnostics, OCR configuration checks, audio checks, and safe temporary-file
cleanup.

Path:

```text
科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/
```

## Sources and licenses

Copyright and licenses for third-party content remain with each upstream
project. This repository does not apply one blanket license to redistributed
skills. Review the relevant skill directory and
[Third-Party Notices](THIRD_PARTY_NOTICES.md) before use or redistribution.

Some official document skills are intentionally excluded because their licenses
do not permit redistribution. See the notices for details.

## Maintenance and contribution

When adding or updating a skill:

1. Preserve the complete directory and license files.
2. Use the category/source/skill hierarchy.
3. Scan for secrets, caches, large files, and restricted content.
4. Update counts, sources, and both language documents.
5. Validate UTF-8, links, and skill structure before publishing.

See the [English maintenance guide](docs/MAINTENANCE.en.md).

## Documentation

- [English installation guide](docs/INSTALL.en.md)
- [中文安装指南](docs/INSTALL.zh-CN.md)
- [English maintenance guide](docs/MAINTENANCE.en.md)
- [中文维护指南](docs/MAINTENANCE.zh-CN.md)
- [Third-Party Notices](THIRD_PARTY_NOTICES.md)

Medical, legal, financial, and laboratory-safety outputs require review by
qualified professionals.
