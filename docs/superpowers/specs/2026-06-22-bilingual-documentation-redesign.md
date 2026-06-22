# Bilingual Documentation Redesign

## Objective

Replace the current documentation with a concise bilingual structure that serves both skill users and repository maintainers. Keep the existing skill collection layout and current Draft PR, then merge only after documentation validation.

## Information architecture

- `README.md`: complete Chinese project entry point.
- `README_EN.md`: complete English project entry point with matching sections.
- `docs/INSTALL.zh-CN.md`: Chinese installation and troubleshooting guide.
- `docs/INSTALL.en.md`: English installation and troubleshooting guide.
- `docs/MAINTENANCE.zh-CN.md`: Chinese maintenance, contribution, validation, and release workflow.
- `docs/MAINTENANCE.en.md`: English counterpart with matching sections.
- `THIRD_PARTY_NOTICES.md`: authoritative upstream and license notice in English, with a Chinese navigation note.
- `INSTALL-Claude-Code-and-Codex.md`: compatibility redirect to the new installation guides.
- `UPDATING.md`: compatibility redirect to the new maintenance guides.

## README scope

Both READMEs must contain:

1. language switch;
2. project purpose and non-goals;
3. collection statistics;
4. quick start;
5. directory and category navigation;
6. installation choices;
7. repository-original skills;
8. license and safety notice;
9. documentation index.

The READMEs must not duplicate long command references from the installation guides.

## Installation guide scope

Cover:

- platform-native plugins where verified;
- Skills CLI installation;
- manual copying of the innermost skill directory;
- Claude Code and Codex user skill locations;
- this repository's original skill;
- verification, update, and removal;
- Windows, macOS, and Linux command differences;
- troubleshooting and duplicate-name risks.

Commands that may change must be verified against currently installed CLI help or official documentation before publication.

## Maintenance guide scope

Cover:

- category and source-group naming rules;
- adding original and third-party skills;
- preserving license files;
- excluded/restricted content;
- count updates;
- UTF-8, secret, large-file, cache, and link checks;
- branch, PR, and release workflow.

## Compatibility and local-only files

- Keep the old installation and updating filenames as redirect documents so existing links do not break.
- Keep `科研Skills分类详细说明.txt` local-only by adding it to `.git/info/exclude`; do not commit it or add it to repository `.gitignore`.

## Validation

Before merge:

- all Markdown is valid UTF-8 without replacement characters;
- Chinese and English documents have matching high-level sections;
- internal relative links resolve;
- skill and category counts match the repository tree;
- installation commands are supported by current CLI help or official documentation;
- no secrets, local paths, caches, or oversized files are introduced;
- the Draft PR accurately describes the full change.

