# Skills Installation Guide

English | [简体中文](INSTALL.zh-CN.md)

This guide explains how to install an individual skill from this repository.
Do not copy `科研/`, `开发/`, or `内容创作/` as a whole. Install the innermost
directory that contains `SKILL.md`.

## Prerequisites

- Install Git.
- Node.js 18 or newer is required for the Skills CLI.
- Python 3.9 or newer is required when a skill contains Python scripts.
- Review the target skill's license, scripts, and dependencies before installing.

## Recommended method: Skills CLI

Install the repository-original document conversion skill:

```bash
npx skills add luffysolution-svg/research-skills-collection \
  --skill convert-documents-to-markdown \
  --agent claude-code codex \
  --global --copy --full-depth --yes
```

On Windows PowerShell, use `npx.cmd` if the execution policy blocks `npx.ps1`.
`--full-depth` is required because this repository has a deep category hierarchy.

Install for one agent only:

```bash
npx skills add luffysolution-svg/research-skills-collection \
  --skill convert-documents-to-markdown \
  --agent claude-code \
  --global --copy --full-depth --yes
```

Replace `claude-code` with `codex` for a Codex-only installation. For another
skill, replace the value after `--skill` with its frontmatter `name`.

## Manual installation

Copy the complete skill directory, including `SKILL.md`, `scripts/`,
`references/`, `assets/`, and license files.

| Scope | Claude Code | Codex |
|---|---|---|
| User | `~/.claude/skills/<skill-name>/` | `~/.agents/skills/<skill-name>/` |
| Project | `<project>/.claude/skills/<skill-name>/` | `<project>/.agents/skills/<skill-name>/` |

Windows PowerShell example:

```powershell
$source = "科研\办公专用skills\luffysolution-skills\convert-documents-to-markdown"
$target = Join-Path $HOME ".agents\skills\convert-documents-to-markdown"
Copy-Item -LiteralPath $source -Destination $target -Recurse
```

If the destination exists, compare it first instead of overwriting local changes.

## Native platform plugins

Some upstream projects publish Claude Code or Codex plugins. Follow the
upstream project's official instructions in that case, because a plugin may
include commands, hooks, MCP configuration, and multiple skills. This
repository categorizes skill files and does not replace upstream manifests.

Do not use `claude plugin` or `codex plugin` on an ordinary directory that only
contains `SKILL.md`. Use the Skills CLI or manual copy for a plain skill.

## Invocation and verification

Claude Code supports `/skill-name` and automatic loading from the description.
Codex supports `$skill-name`, and `/skills` lists available skills. Restart the
agent session if a newly copied or replaced skill is not detected.

List global installations:

```bash
npx skills list --global --agent claude-code
npx skills list --global --agent codex
```

For `convert-documents-to-markdown`, run its dependency doctor:

```bash
python ~/.agents/skills/convert-documents-to-markdown/scripts/document-tools-doctor.py
```

Claude Code users should replace `.agents` with `.claude`. On Windows, an
absolute `%USERPROFILE%` path may be used.

## Updating and removal

```bash
npx skills check
npx skills update --global
```

Before removal, confirm that the skill directory has no local modifications,
then delete that one directory. Never delete the complete
`~/.claude/skills/` or `~/.agents/skills/` directory.

## Conflicts and troubleshooting

- **Skill not found:** Confirm that `SKILL.md` is at the skill root and restart
  the session.
- **Duplicate name:** Different sources may use the same `name`. Keep one, or
  rename both the directory and frontmatter and maintain that fork yourself.
- **Skills CLI cannot discover it:** Include `--full-depth`.
- **PowerShell blocks npx:** Use `npx.cmd`; do not weaken the global execution policy.
- **A script fails:** Read its dependency notes and run its doctor/check script.
- **OCR or MinerU credentials are missing:** Obtain credentials from the
  selected provider's official dashboard. A third-party relay is not an
  official OpenAI service. Never commit credentials.
- **Paths contain CJK characters or spaces:** Quote paths and prefer Python 3 with UTF-8.

## Security

Skills may contain executable scripts and network calls. Review the source,
license, commands, and credential handling before installing third-party
content. Do not commit API keys, tokens, `.env` files, conversion output, or
personal documents to this repository.

For repository work, read the [maintenance guide](MAINTENANCE.en.md).
