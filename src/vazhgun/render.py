from __future__ import annotations

import json
import os
from typing import List

from . import __version__
from .checks import Finding, summarize, visible

C = {"error": "\x1b[31m", "warn": "\x1b[33m", "info": "\x1b[36m", "dim": "\x1b[2m", "b": "\x1b[1m", "0": "\x1b[0m"}
SIGN = {"error": "✗", "warn": "!", "info": "·"}


def _bidi_safe(s: str) -> str:
    """Terminals re-order RTL text themselves; fence quoted samples with LRI…PDI so the line layout stays stable."""
    return "\u2066" + s + "\u2069"


def _segs(segments) -> str:
    """Every drawn run is isolated (LRI/RLI … PDI) inside one left-to-right line, so a bidi-aware viewer
    keeps the left-to-right order of the runs while each run reads correctly."""
    return _bidi_safe("".join(("\u2067" if rtl else "\u2066") + t + "\u2069" for rtl, t in segments))


def text(doc, findings: List[Finding], color: bool = False, show_all: bool = False, fixed_path: str = "") -> str:
    def c(k, s):
        return f"{C[k]}{s}{C['0']}" if color else s
    sm = summarize(doc, findings)
    out = [f"vazhgun {__version__} · {os.path.basename(doc.path)} · {sm['paragraphs']} paragraphs ({sm['persian_paragraphs']} Persian), {sm['tables']} tables", ""]
    if not findings:
        out.append("✓ nothing found that depends on bidi order.")
    for f in findings:
        out.append(f"{c(f.severity, SIGN[f.severity])} {f.code} {f.title}   [{f.where}]")
        if not (f.typed is not None and f.segments is not None):
            out.append(f"    text : {_bidi_safe(f.snippet)}")
        if f.typed is not None and f.segments is not None:
            out.append(f"    typed: {_bidi_safe(visible(f.typed))}")
            out.append("    drawn: " + _segs(f.segments) + c("dim", "   (approximate; runs listed left to right)"))
        out.append(f"    why  : {f.why}")
        out.append(f"    fix  : {f.fix}")
        out.append("")
    out.append(f"{sm['errors']} error(s), {sm['warnings']} warning(s), {sm['info']} note(s); {sm['fixable']} fixable with --fix.")
    na = sm["not_analysed"]
    if na:
        out.append("not analysed: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in na.items()))
    out.append("The drawn lines follow the Unicode Bidirectional Algorithm; Word/LibreOffice/Google Docs can differ slightly. Open the file to confirm.")
    if fixed_path:
        out.append(fixed_path)
    return "\n".join(out) + "\n"


def as_json(doc, findings: List[Finding]) -> str:
    return json.dumps({"tool": "vazhgun", "version": __version__, "file": os.path.basename(doc.path),
                       "summary": summarize(doc, findings), "findings": [f.to_dict() for f in findings]},
                      ensure_ascii=False, indent=2)
