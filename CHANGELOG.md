# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Nothing user-facing yet, so no release was cut for these.

- Docs: README rewritten in English and Persian (banner, contents, before/after, features, limits, roadmap); CITATION.cff, issue forms and a pull-request template.
- Internal: unused imports and never-read variables removed; tests got named helpers and docstrings. No change in findings or output.

## [0.1.0] - 2026-10-24

First release.

### Added
- `vazhgun FILE.docx`: audit a Persian/Arabic `.docx` for places where what you typed and what the reader sees differ, or where the order depends on the renderer.
- Findings V101-V104 (paragraph direction, tables, stray control characters) and V201-V203 (number order: ranges, dates, caption numbers, signs), each with the line as typed, an approximate drawn view, why, and the Word-side fix.
- `--fix`: writes a **copy** with explicit direction (`w:bidi`, `w:bidiVisual`) and number order (`--chains ltr|reading`, `--strip-controls`); every other part of the file stays byte-identical.
- A small Unicode Bidirectional Algorithm (UAX #9) implementation, cross-checked against libfribidi (40,000 random strings, identical levels) and python-bidi.
- `--json`, `--strict`, `--demo`, `--make-sample`; reads `.txt`/`.md` for paragraph-level checks.
