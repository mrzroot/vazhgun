"""vazhgun checks: where does the order a reader sees differ from, or depend on, what was typed?"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from . import uba
from .docxio import Document, Paragraph

RLM, LRM = "\u200f", "\u200e"
DIGIT = "0-9\u06f0-\u06f9\u0660-\u0669"
SEP = "-\u2013\u2212/.:\u066b\u066c,\u060c"
MARK = "\u200e\u200f"
CHAIN_RE = re.compile(rf"[{DIGIT}]+(?:[{MARK}]*[{SEP}][{MARK}]*[{DIGIT}]+)+")
MINUS_RE = re.compile(rf"(?<![{DIGIT}\w{MARK}])([-\u2212+])(?=[{DIGIT}])")
CAPTION_WORDS = ("شکل", "جدول", "نمودار", "رابطه", "معادله", "فرمول", "فصل", "بخش", "پیوست", "تصویر", "عکس",
                 "figure", "fig", "table", "eq", "equation", "chapter", "section", "appendix")
PAGE_WORDS = ("صفحه", "صفحات", "ص", "صص", "p", "pp", "page", "pages")

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}


@dataclass
class Finding:
    code: str
    severity: str
    title: str
    para: Optional[int]          # paragraph index (0-based) or None
    where: str
    snippet: str
    why: str
    fix: str
    typed: Optional[str] = None
    shown: Optional[str] = None                 # drawn string, left to right (letters in drawn order)
    segments: Optional[List[List[object]]] = None   # drawn runs, left to right: [is_rtl, logical text]
    fixable: bool = False
    extra: Dict[str, object] = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, {}, "")}


def _letters(text: str):
    r = l = 0
    for ch in text:
        if not ch.isalpha():
            continue
        c = unicodedata.bidirectional(ch)
        if c in ("R", "AL"):
            r += 1
        elif c == "L":
            l += 1
    return r, l


def is_persian_text(text: str) -> bool:
    r, l = _letters(text)
    return r >= 3 and r >= l


def is_latin_text(text: str) -> bool:
    r, l = _letters(text)
    return l >= 12 and l > 3 * r


_VIS = {"\u200e": "⟨LRM⟩", "\u200f": "⟨RLM⟩", "\u202a": "⟨LRE⟩", "\u202b": "⟨RLE⟩", "\u202c": "⟨PDF⟩", "\u202d": "⟨LRO⟩",
        "\u202e": "⟨RLO⟩", "\u2066": "⟨LRI⟩", "\u2067": "⟨RLI⟩", "\u2068": "⟨FSI⟩", "\u2069": "⟨PDI⟩"}


def visible(s: str) -> str:
    """Make invisible bidi marks visible in reports."""
    return "".join(_VIS.get(ch, ch) for ch in s)


def snip(text: str, a: int = 0, b: Optional[int] = None, width: int = 70) -> str:
    if b is None:
        b = min(len(text), a + width)
    lo = max(0, a - 25)
    hi = min(len(text), b + 25)
    s = text[lo:hi].replace("\n", " ")
    return visible(("…" if lo > 0 else "") + s + ("…" if hi < len(text) else ""))


def _vis(text: str, rtl: bool) -> Optional[str]:
    try:
        return uba.display(text, rtl)
    except uba.Unsupported:
        return None


def _seg(text: str, rtl: bool):
    try:
        return [[r, t] for r, t in uba.segments(text, rtl)]
    except uba.Unsupported:
        return None


def _where(p: Paragraph) -> str:
    bits = [f"¶{p.idx + 1}"]
    if p.in_table:
        bits.append("table")
    if p.style_name:
        bits.append(p.style_name)
    return " · ".join(bits)


def _kind(text: str, m: re.Match, p: Paragraph) -> str:
    chain = m.group(0)
    clean = re.sub(f"[{MARK}]", "", chain)
    comps = re.split(f"[{SEP}]", clean)
    seps = re.findall(f"[{SEP}]", clean)
    before = text[max(0, m.start() - 14):m.start()]
    before_words = re.findall(r"[^\W\d_]+\.?", before)
    last = before_words[-1].rstrip(".").lower() if before_words else ""
    st = (p.style_name or "").lower()
    if len(comps) == 2 and set(seps) <= {".", "\u066b"} :
        return "decimal"
    if set(seps) <= {":"} and len(comps) <= 3:
        return "time"
    if len(comps) >= 4 or any(len(c) >= 6 for c in comps):
        return "id"
    if last in CAPTION_WORDS or "caption" in st or "شرح" in st:
        return "caption-number"
    stripped = text.strip()
    if re.fullmatch(rf"[(\[]?\s*{re.escape(chain)}\s*[)\]]?", stripped):
        return "caption-number"          # equation number alone, e.g. (۲-۴)
    if last in PAGE_WORDS:
        return "page-range"
    nums = [re.sub(f"[{MARK}]", "", c) for c in comps]
    if len(comps) == 3 and (len(nums[0]) == 4 or len(nums[2]) == 4):
        return "date"
    if len(comps) == 2 and all(len(c) == 4 for c in comps):
        return "year-range"
    if len(comps) == 2 and set(seps) <= {"-", "\u2013", "\u2212"}:
        return "range"
    return "other"


def chain_order(text: str, m: re.Match, rtl: bool = True) -> Optional[str]:
    """'ltr' if the first number is drawn to the left of the last one, 'rtl' otherwise."""
    try:
        pos = uba.positions(text, rtl)
    except uba.Unsupported:
        return None
    digits = [i for i in range(m.start(), m.end()) if re.match(f"[{DIGIT}]", text[i])]
    if len(digits) < 2:
        return None
    first, last = digits[0], digits[-1]
    return "ltr" if pos[first] < pos[last] else "rtl"


def analyse(doc: Document, scope: str = "all") -> List[Finding]:
    out: List[Finding] = []
    chains: List[Dict[str, object]] = []
    for p in doc.paragraphs:
        text = p.text
        if not text.strip() or p.is_toc:
            continue
        persian = is_persian_text(text)
        # -- V101 / V102 paragraph direction
        if persian and not p.bidi:
            sample = text if len(text) <= 90 else text[:90]
            out.append(Finding(
                "V101", "error", "Persian text in a left-to-right paragraph", p.idx, _where(p), snip(text),
                "Word draws the paragraph's base direction from its own setting (w:bidi), not from the language. "
                "In a left-to-right paragraph punctuation and brackets at the ends of a Persian sentence jump to the wrong side and number order flips.",
                "Select the paragraph and press Ctrl+Right Shift (right-to-left), or set the style to right-to-left. `--fix` adds w:bidi.",
                typed=sample, shown=_vis(sample, False), segments=_seg(sample, False), fixable=True))
        elif is_latin_text(text) and p.bidi:
            ends = text.strip()[-1:]
            if ends and unicodedata.category(ends).startswith("P") or text.strip()[:1] in "([\"'":
                sample = text if len(text) <= 90 else text[:90]
                out.append(Finding(
                    "V102", "info", "Latin paragraph set right-to-left", p.idx, _where(p), snip(text),
                    "A mostly Latin paragraph with a right-to-left base direction puts its final punctuation at the left end.",
                    "Make this paragraph left-to-right (Ctrl+Left Shift) unless it is deliberately a Persian paragraph with long English quotes.",
                    typed=sample, shown=_vis(sample, True), segments=_seg(sample, True)))
        rtl = p.bidi
        # -- V104 stray bidi controls
        ctrl = [c for c in text if c in uba.EXPLICIT]
        if ctrl:
            openers = sum(1 for c in ctrl if c in "\u202a\u202b\u202d\u202e\u2066\u2067\u2068")
            closers = sum(1 for c in ctrl if c in "\u202c\u2069")
            override = any(c in "\u202d\u202e" for c in ctrl)
            names = ", ".join(sorted({unicodedata.name(c).title().replace("Left-To-Right", "LR").replace("Right-To-Left", "RL") for c in ctrl}))
            sev = "error" if override or openers != closers else "info"
            out.append(Finding(
                "V104", sev, "Invisible bidi control characters" + (" (override/unbalanced)" if sev == "error" else ""),
                p.idx, _where(p), snip(text, text.index(ctrl[0]), text.index(ctrl[0]) + 1),
                f"{len(ctrl)} embedding/override/isolate character(s) found ({names}). They are typically pasted in from PDFs or web pages; "
                "overrides force the visual order and an unclosed one leaks into the following text. Word only inserts them through its «Insert Unicode control character» menu. "
                "vazhgun cannot preview this paragraph (explicit controls are outside its scope).",
                "Retype the passage, or run `--fix --strip-controls` to delete them (review the result: removing an embedding changes the drawing).",
                fixable=True, extra={"count": len(ctrl), "overrides": override}))
            continue          # no preview/chain analysis for paragraphs with explicit controls
        if not rtl:
            continue
        # -- V201 number chains
        for m in CHAIN_RE.finditer(text):
            kind = _kind(text, m, p)
            if kind in ("decimal", "time", "id", "other"):
                continue
            order = chain_order(text, m, True)
            if order is None:
                continue
            marked = RLM in m.group(0) or LRM in m.group(0) or text[max(0, m.start() - 1):m.start()] in (RLM, LRM)
            chains.append({"para": p, "m": m, "kind": kind, "order": order, "marked": marked})
        # -- V203 sign before a number
        for m in MINUS_RE.finditer(text):
            try:
                pos = uba.positions(text, True)
            except uba.Unsupported:
                continue
            j = m.end()
            if pos[m.start()] > pos[j]:           # sign drawn to the RIGHT of its number
                a, b = max(0, m.start() - 20), min(len(text), m.end() + 12)
                seg = text[a:b]
                out.append(Finding(
                    "V203", "warn", f"Sign «{m.group(1)}» is drawn after its number", p.idx, _where(p), snip(text, m.start(), m.end()),
                    "In a right-to-left paragraph a hyphen or plus in front of a digit is a weak character that goes with the Persian text around it, "
                    "so it is drawn on the right of the number: -۵ looks like ۵-.",
                    "Put a left-to-right mark (U+200E) before the sign, or use the real minus U+2212 with it. `--fix` inserts the mark.",
                    typed=seg, shown=_vis(seg, True), segments=_seg(seg, True), fixable=True, extra={"offset": m.start()}))
    # group chains by kind: consistency and ambiguity
    by_kind: Dict[str, List[dict]] = {}
    for c in chains:
        by_kind.setdefault(str(c["kind"]), []).append(c)
    for kind, items in by_kind.items():
        orders = {c["order"] for c in items}
        label = {"caption-number": "caption / chapter-style numbers (شکل ۲-۳, (۲-۴))", "page-range": "page ranges (صفحات ۱۲-۱۵)",
                 "year-range": "year ranges (۱۳۹۸-۱۳۹۹)", "date": "dates (۱۴۰۳/۰۹/۰۴)", "range": "numeric ranges (۱۰-۲۰)"}[kind]
        if len(orders) > 1:
            cnt = {o: sum(1 for c in items if c["order"] == o) for o in ("ltr", "rtl")}
            minority = "ltr" if cnt["ltr"] < cnt["rtl"] else "rtl"
            for c in [c for c in items if c["order"] == minority][:50]:
                p, m = c["para"], c["m"]
                seg = p.text[max(0, m.start() - 12):min(len(p.text), m.end() + 6)]
                out.append(Finding(
                    "V202", "warn", f"Inconsistent drawing of {label}", p.idx, _where(p), snip(p.text, m.start(), m.end()),
                    f"{cnt['ltr']} of these are drawn left-to-right (first number on the left) and {cnt['rtl']} right-to-left "
                    "(first number on the right) in this document, so the same kind of number appears as ۲-۳ in one place and ۳-۲ in another. "
                    f"This is one of the {cnt[minority]} drawn {'left-to-right' if minority == 'ltr' else 'right-to-left'}.",
                    "Pick one convention for the whole thesis and apply it: `--fix --chains reading` (first number on the right, RLM after the separator) "
                    "or `--fix --chains ltr` (first number on the left).",
                    typed=seg, shown=_vis(seg, True), segments=_seg(seg, True), fixable=True, extra={"order": minority, "kind": kind, "offset": m.start()}))
        else:
            o = next(iter(orders))
            unmarked = [c for c in items if not c["marked"]]
            for c in unmarked[:3]:
                p, m = c["para"], c["m"]
                seg = p.text[max(0, m.start() - 12):min(len(p.text), m.end() + 6)]
                out.append(Finding(
                    "V201", "info", f"Number order rests on the renderer: {label}", p.idx, _where(p), snip(p.text, m.start(), m.end()),
                    f"Typed «{m.group(0)}»; by the Unicode algorithm it is drawn {'left-to-right here (first number on the LEFT)' if o == 'ltr' else 'right-to-left here (first number on the RIGHT, reading order)'}. "
                    "How a number with a hyphen or slash is drawn depends on what comes before it (Persian letters, Latin letters, start of the line, a bracket) "
                    "and can differ between Word versions, LibreOffice, Google Docs and PDF export (a published Persian-Word note reports a slash date shown day-first in Word although the Unicode algorithm draws it left-to-right). "
                    "Consistent here, but not explicit.",
                    "Optional: `--fix --chains ltr` (LRM around the chain: first number on the left) or `--chains reading` (RLM after each separator: first number on the right).",
                    typed=seg, shown=_vis(seg, True), segments=_seg(seg, True), fixable=True, extra={"order": o, "kind": kind, "offset": m.start()}))
            if len(unmarked) > 3:
                out.append(Finding("V201", "info", f"… and {len(unmarked) - 3} more unmarked {label}", None, "document", "",
                                   "Same situation as above.", "Apply one `--chains` policy to all of them.", fixable=True,
                                   extra={"kind": kind, "count": len(unmarked)}))
    # -- V103 tables
    for t in doc.tables:
        paras = doc.paragraphs[t.first_para:t.last_para + 1]
        texts = [p for p in paras if p.text.strip()]
        if texts and t.cols >= 2 and not t.bidi_visual and sum(1 for p in texts if is_persian_text(p.text)) >= max(2, len(texts) // 2):
            p0 = texts[0]
            out.append(Finding(
                "V103", "warn", "Persian table laid out left-to-right", p0.idx, f"table {t.id} ({t.rows}×{t.cols})", snip(p0.text),
                "Without the table property «right-to-left» (w:bidiVisual) the first column is drawn at the LEFT edge, so the columns of a Persian table read backwards.",
                "Select the table → Table Properties → Table → Alignment, or Layout → Table Direction → Right-to-Left. `--fix` adds w:bidiVisual.",
                fixable=True, extra={"table": t.id}))
    out.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.para if f.para is not None else 10**9, f.code))
    return out


def summarize(doc: Document, findings: List[Finding]) -> Dict[str, object]:
    persian = sum(1 for p in doc.paragraphs if p.text.strip() and is_persian_text(p.text))
    return {
        "paragraphs": len(doc.paragraphs), "persian_paragraphs": persian, "tables": len(doc.tables),
        "errors": sum(1 for f in findings if f.severity == "error"),
        "warnings": sum(1 for f in findings if f.severity == "warn"),
        "info": sum(1 for f in findings if f.severity == "info"),
        "fixable": sum(1 for f in findings if f.fixable),
        "not_analysed": {k: v for k, v in doc.unsupported.items() if v},
    }
