# Novelty check: vazhgun

Done 2026-10-24 before building. Wording is deliberately modest: **no existing tool found as of October 2026** that audits a
Persian `.docx` for bidirectional number-order problems (a range or date that is typed one way and drawn the other way, or
drawn two ways in one thesis) by running the Unicode Bidirectional Algorithm on each paragraph and offering an explicit,
non-destructive fix. That is not a claim that none exists anywhere, and the *paragraph/table direction* part overlaps with
tools listed below.

## Searches

GitHub repository search (API, total results; AND-of-terms and noisy):

| query | total |
|---|---|
| `docx bidi checker` | 0 |
| `rtl mixed text docx audit` | 0 |
| `bidi parentheses docx fix` | 0 |
| `persian docx rtl lint` | 0 |
| `word rtl run language tag` | 0 |
| `persian english mixed text punctuation fix` | 0 |
| `rlm docx persian` | 0 |
| `right-to-left mark docx insert` | 0 |
| `docx rtl paragraph bidi python` | 0 |
| `arabic docx formatter` | 11 |
| `hebrew docx rtl fix punctuation` | 0 |
| `rtl punctuation mixed english fix` | 0 |
| `persian number hyphen reversed word` | 0 |
| `word rtl numbering reversed persian` | 0 |
| `unicode bidi visualizer` | 0 |
| `bidi algorithm python visual order` | 0 |
| `persian digits english digits mixed detect` | 0 |

Also searched (2026-10-24): npm registry (`docx bidi`, `docx rtl`, `rtl docx`, `bidi docx fix`, `persian docx`, `arabic docx`: only
generic libraries such as `docx`, `mammoth`, `bidi-js`, `rtl-detect`), a local copy of the PyPI project-name index
(~922,000 names; names containing `bidi`, `rtl`, `persian`, `farsi`, `docx`, `thesis`, `virastar`, `hazm`: no DOCX bidi auditor; closest
`rtl-lint-mcp` = hardware RTL, `bidirectional-text` = a Streamlit widget, `persianize` = Arabic-to-Persian character converter,
`mcp-docx-thesis-server` = generates theses), and web searches (`Word docx Persian numbers reversed «شکل ۲-۱» dash direction RLM fix`,
`docx bidi audit tool detect Arabic Persian paragraphs missing w:bidi RTL linter`).

## Closest existing work

| project | what it is | difference |
|---|---|---|
| [Arabic Word Production](https://bannovich.github.io/arabic-word-production/) (Apache-2.0 skill/plugin) | creates and structurally audits Arabic-first DOCX: paragraph/run direction, tables, alignment, geometry | Arabic-first, structural (OOXML properties); I did not find number-chain order analysis. Overlaps with V101-V103. |
| [ibadwi/arabic-rtl-fixer-ai-skill](https://github.com/ibadwi/arabic-rtl-fixer-ai-skill) | AI skill for fixing Arabic RTL/BiDi in DOCX/PPTX | an agent prompt, not a deterministic offline checker |
| [sadeghr64/persian-docx](https://github.com/sadeghr64/persian-docx) | agent skill for *producing* Persian DOCX that renders correctly (its notes report a slash date shown day-first in unmarked Word, fixed only by an LRM) | generation guidance, not an auditor of an existing file |
| `docxaudit` (PyPI) | audits what a converter dropped from a `.docx` | structural, no bidi |
| `python-bidi`, `fribidi`, `bidi-js`, ICU | implementations of the Unicode algorithm | libraries; they do not read DOCX or know about captions/ranges. Used here as test oracles. |
| Word's own tutorials (Persian blogs) | manual steps: set paragraph RTL, insert RLM/LRM by hand | by hand, per occurrence |
| Generic and Chinese thesis format checkers (e.g. `thesis-format-checker`, `china-thesis-docx-formatter`) | margins, fonts, headings for GB-style theses | no bidi/Persian logic |

## Verdict

Distinct combination: **a Unicode-algorithm preview of every number chain in a Persian DOCX + consistency check across the
document + an explicit, reversible fix written to a copy**. The individual facts (a hyphen between Persian digits can swap
order; Word needs an LRM) are well known to people who have been bitten and are discussed in forum posts and blogs; I found no
tool that detects them in a file. If you know of one, please open an issue and it will be linked here.

Not verified: how every Word version draws these chains (see README "Limits").
