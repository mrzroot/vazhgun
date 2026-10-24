from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__, checks, render
from .docxio import load


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="vazhgun", description=(
        "Audit a Persian/Arabic .docx for places where the order a reader sees depends on bidirectional rules or the renderer: "
        "left-to-right paragraphs, ۲-۳ vs ۳-۲, -۵ vs ۵-, tables, stray invisible controls. Offline; never edits your file."))
    ap.add_argument("file", nargs="?", help=".docx (or .txt/.md for paragraph-level checks)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too (default: only on errors)")
    ap.add_argument("--fix", action="store_true", help="write a fixed COPY (never overwrites the input)")
    ap.add_argument("--chains", choices=["reading", "ltr"], help="with --fix: make number chains explicit; reading = first number on the right")
    ap.add_argument("--strip-controls", action="store_true", help="with --fix: delete embedding/override/isolate characters")
    ap.add_argument("-o", "--output", help="path of the fixed copy (default: <name>.vazhgun.docx)")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--demo", action="store_true", help="offline: generate a sample thesis chapter and audit it")
    ap.add_argument("--make-sample", metavar="PATH", help="write the synthetic demo chapter (.docx) to PATH and exit")
    ap.add_argument("--version", action="version", version=f"vazhgun {__version__}")
    a = ap.parse_args(argv)
    if a.demo:
        if a.fix:
            ap.error("--fix needs your own file; use --make-sample PATH to get a sample .docx and fix that")
        import tempfile
        from . import sample
        with tempfile.TemporaryDirectory() as td:
            a.demo = False
            a.file = sample.chapter(os.path.join(td, "chapter2.docx"))
            return main([a.file] + [x for x in (argv if argv is not None else sys.argv[1:]) if x != "--demo"])
    if a.make_sample:
        from . import sample
        print(sample.chapter(a.make_sample))
        return 0
    if not a.file:
        ap.error("give a .docx file (or use --demo)")
    if not os.path.exists(a.file):
        print(f"vazhgun: no such file: {a.file}", file=sys.stderr)
        return 2
    try:
        doc = load(a.file)
    except Exception as e:           # damaged or unsupported file: say so, do not crash with a traceback
        print(f"vazhgun: cannot read {a.file}: {e}", file=sys.stderr)
        return 2
    findings = checks.analyse(doc)
    extra = ""
    if a.fix:
        if doc.kind != "docx":
            print("vazhgun: --fix works on .docx only", file=sys.stderr)
            return 2
        from . import fixer
        dst = a.output or os.path.splitext(a.file)[0] + ".vazhgun.docx"
        if os.path.abspath(dst) == os.path.abspath(a.file):
            print("vazhgun: refusing to overwrite the input file", file=sys.stderr)
            return 2
        st = fixer.fix_docx(a.file, dst, chains=a.chains, strip_controls=a.strip_controls)
        extra = (f"fixed copy: {dst}  (paragraph direction: {st['bidi']}, tables: {st['table']}, signs: {st['signs']}, "
                 f"number chains: {st['chains']}, controls removed: {st['controls']}). Re-run vazhgun on it to check.")
    sys.stdout.write((render.as_json(doc, findings) + "\n") if a.json else render.text(doc, findings, color=sys.stdout.isatty() and not a.no_color, fixed_path=extra))
    bad = sum(1 for f in findings if f.severity == "error") + (sum(1 for f in findings if f.severity == "warn") if a.strict else 0)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
