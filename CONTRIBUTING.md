# Contributing

Thanks for helping! vazhgun is small on purpose: standard library only, no telemetry, no network.

```sh
git clone https://github.com/mrzroot/vazhgun && cd vazhgun
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest
python -m vazhgun --demo
```

Ground rules

- **No new runtime dependencies**, and Python 3.9 must keep working.
- Tests use synthetic, generated `.docx` fixtures only. Never commit a real thesis or any real person's document.
- Anything that claims to say how *Word* draws a line must be backed by the Unicode algorithm tests (`tests/test_uba.py`) or labelled as unverified.
- Add your change to `CHANGELOG.md`.
- Found a tool that already does this? Open an issue; it will be linked in the README and NOVELTY.md.
