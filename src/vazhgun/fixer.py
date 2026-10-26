"""Write a fixed copy of a .docx: only <w:t> text, w:bidi and w:bidiVisual are touched, everything else is copied byte for byte."""
from __future__ import annotations

import re
import zipfile
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape, unescape

from .checks import CHAIN_RE, MINUS_RE, MARK, RLM, LRM, SEP, _kind
from . import uba
from .docxio import read_docx

LATER_PPR = ("adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap",
             "jc", "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
             "sectPr", "pPrChange")
P_TOKEN = re.compile(r"<w:p(?=[\s>/])[^>]*?(/?)>|</w:p>|<w:txbxContent[\s>]|</w:txbxContent>")


def paragraph_spans(xml: str) -> List[Tuple[int, int]]:
    """(start, end) offsets of every block-level paragraph, in the same order docxio reports them."""
    spans, stack, tx = [], [], 0
    for m in P_TOKEN.finditer(xml):
        tok = m.group(0)
        if tok.startswith("<w:txbxContent"):
            tx += 1
        elif tok == "</w:txbxContent>":
            tx -= 1
        elif tok.startswith("<w:p"):
            if m.group(1) == "/":          # <w:p/>
                if tx == 0:
                    spans.append((m.start(), m.end()))
                continue
            stack.append((m.start(), tx))
        else:
            s, t = stack.pop()
            if t == 0:
                spans.append((s, m.end()))
    spans.sort()
    return spans


def set_bidi(pxml: str) -> str:
    m = re.search(r"<w:p(?=[\s>])[^>]*>", pxml)
    head_end = m.end()
    ppr = re.search(r"<w:pPr>(.*?)</w:pPr>", pxml[head_end:], flags=re.S)
    if not ppr or ppr.start() != 0:
        return pxml[:head_end] + "<w:pPr><w:bidi/></w:pPr>" + pxml[head_end:]
    inner = ppr.group(1)
    if re.search(r"<w:bidi(?=[\s/>])", inner):
        inner = re.sub(r"<w:bidi\b[^>]*/>", "<w:bidi/>", inner, count=1)
    else:
        mm = re.search(r"<w:(" + "|".join(LATER_PPR) + r")(?=[\s/>])", inner)
        pos = mm.start() if mm else len(inner)
        inner = inner[:pos] + "<w:bidi/>" + inner[pos:]
    a = head_end + ppr.start()
    return pxml[:a] + "<w:pPr>" + inner + "</w:pPr>" + pxml[a + ppr.end():]


_WT = re.compile(r"(<w:t(?=[\s>])[^>]*>)(.*?)(</w:t>)", re.S)


def edit_paragraph(pxml: str, plan) -> str:
    """Apply character-level edits to the concatenated <w:t> text of one paragraph.

    plan(T) -> (deletions: set of positions, insertions: {position: text inserted before that character}).
    Because the edits are per character they work across run boundaries (e.g. «شکل 2-» + a SEQ field result «1»)."""
    nodes = list(_WT.finditer(pxml))
    texts = [unescape(m.group(2)) for m in nodes]
    T = "".join(texts)
    dels, ins = plan(T)
    if not dels and not ins:
        return pxml
    out, last, pos = [], 0, 0
    for k, (m, t) in enumerate(zip(nodes, texts)):
        piece = []
        for j, ch in enumerate(t):
            i = pos + j
            if i in ins:
                piece.append(ins[i])
            if i not in dels:
                piece.append(ch)
        if k == len(nodes) - 1 and len(T) in ins:
            piece.append(ins[len(T)])
        pos += len(t)
        new = "".join(piece)
        out.append(pxml[last:m.start(2)])
        out.append(escape(new) if new != t else m.group(2))
        last = m.end(2)
    out.append(pxml[last:])
    return "".join(out)


def chain_edits(T: str, m: re.Match, policy: str, dels: set, ins: Dict[int, str]) -> None:
    """reading: an RLM after every separator -> the first number is drawn on the right (reading order).
    ltr: an LRM before and after the chain -> the whole chain is one left-to-right run (first number on the left)."""
    for k in re.finditer(rf"[{MARK}]*([{SEP}])[{MARK}]*", m.group(0)):
        s0 = m.start() + k.start()
        for i in range(s0, m.start() + k.end()):
            if T[i] in (RLM, LRM):
                dels.add(i)
        if policy == "reading":
            ins[m.start() + k.end()] = ins.get(m.start() + k.end(), "") + RLM
    if policy == "ltr":
        if T[max(0, m.start() - 1):m.start()] != LRM:
            ins[m.start()] = ins.get(m.start(), "") + LRM
        if T[m.end():m.end() + 1] != LRM:
            ins[m.end()] = ins.get(m.end(), "") + LRM


def fix_docx(src: str, dst: str, chains: Optional[str] = None, strip_controls: bool = False) -> Dict[str, int]:
    from .checks import analyse
    doc = read_docx(src)
    findings = analyse(doc)
    want_bidi = {f.para for f in findings if f.code == "V101"}
    want_tbl = {f.extra.get("table") for f in findings if f.code == "V103"}
    sign_paras = {f.para for f in findings if f.code == "V203"}
    ctrl_paras = {f.para for f in findings if f.code == "V104"} if strip_controls else set()
    chain_paras = {p.idx for p in doc.paragraphs
                   if (p.bidi or p.idx in want_bidi) and (p.idx in ctrl_paras or not any(c in uba.EXPLICIT for c in p.text))} if chains else set()
    stats = {"bidi": 0, "table": 0, "signs": 0, "chains": 0, "controls": 0}
    zin = zipfile.ZipFile(src)
    xml = zin.read("word/document.xml").decode("utf-8")
    spans = paragraph_spans(xml)
    if len(spans) != len(doc.paragraphs):
        raise RuntimeError(f"internal check failed: {len(spans)} paragraphs in XML vs {len(doc.paragraphs)} parsed; refusing to edit")
    out, last = [], 0
    for idx, (a, b) in enumerate(spans):
        p = xml[a:b]
        new = p
        if idx in want_bidi:
            new = set_bidi(new)
            stats["bidi"] += 1
        counts = {"signs": 0, "chains": 0, "controls": 0}

        def plan(T: str, idx=idx):
            dels, ins = set(), {}
            if idx in ctrl_paras:
                for i, ch in enumerate(T):
                    if ch in uba.EXPLICIT:
                        dels.add(i)
                        counts["controls"] += 1
            if idx in sign_paras:
                for m in MINUS_RE.finditer(T):
                    ins[m.start()] = ins.get(m.start(), "") + LRM
                    counts["signs"] += 1
            if idx in chain_paras:
                for m in CHAIN_RE.finditer(T):
                    if _kind(T, m, doc.paragraphs[idx]) in ("decimal", "time", "id", "other"):
                        continue
                    counts["chains"] += 1
                    chain_edits(T, m, chains, dels, ins)
            return dels, ins
        if idx in sign_paras or idx in chain_paras or idx in ctrl_paras:
            new = edit_paragraph(new, plan)
        for k in counts:
            stats[k] += counts[k]
        out.append(xml[last:a])
        out.append(new)
        last = b
    out.append(xml[last:])
    xml2 = "".join(out)
    if want_tbl:
        xml2 = _patch_tables(xml2, want_tbl, stats)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = xml2.encode("utf-8")
            zout.writestr(item, data)
    return stats


def _patch_tables(xml: str, want: set, stats: Dict[str, int]) -> str:
    out, n = [], 0
    for m in re.finditer(r"<w:tbl>|<w:tbl\s[^>]*>", xml):
        n += 1
        if n not in want:
            continue
        seg_end = xml.find("</w:tblPr>", m.end())
        head = xml[m.end():seg_end] if seg_end != -1 else ""
        if "<w:bidiVisual" in head or seg_end == -1 and "<w:tblPr" not in xml[m.end():m.end() + 12]:
            continue
        stats["table"] += 1
        ins = m.end()
        if xml.startswith("<w:tblPr>", ins):
            ins += len("<w:tblPr>")
            mm = re.match(r"(?:<w:tblStyle\b[^>]*/>)?(?:<w:tblpPr\b[^>]*/>)?(?:<w:tblOverlap\b[^>]*/>)?", xml[ins:])
            ins += mm.end()
            out.append((ins, "<w:bidiVisual/>"))
        else:
            out.append((ins, "<w:tblPr><w:bidiVisual/></w:tblPr>"))
    res, prev = [], 0
    for pos, s in out:
        res.append(xml[prev:pos])
        res.append(s)
        prev = pos
    res.append(xml[prev:])
    return "".join(res)
