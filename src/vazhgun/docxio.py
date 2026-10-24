"""Minimal, dependency-free DOCX reader (zipfile + xml.etree).

Only what the checks need: paragraphs with runs, resolved style properties, sections, fields,
tables, footers. Anything not modelled (text boxes, tracked changes, equations, content controls'
data binding) is counted in ``Document.unsupported`` so tools can say so honestly.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"w": W, "r": R, "a": A}


def q(tag: str) -> str:
    p, t = tag.split(":")
    return "{%s}%s" % ({"w": W, "r": R, "a": A}[p], t)


def attr(el: Optional[ET.Element], name: str, default=None):
    if el is None:
        return default
    return el.get(q("w:" + name), default)


def onoff(el: Optional[ET.Element]) -> Optional[bool]:
    """w:b / w:bidi style toggles: absent -> None, present without val -> True."""
    if el is None:
        return None
    v = el.get(q("w:val"))
    if v is None:
        return True
    return v.lower() not in ("0", "false", "off")


@dataclass
class Run:
    text: str
    rpr: Dict[str, object]          # resolved: cs_font, ascii_font, sz, szcs, bold, bold_cs, rtl, lang_bidi
    direct_rtl: Optional[bool] = None
    has_cs_chars: bool = False


@dataclass
class Section:
    index: int
    pg_w: Optional[int] = None
    pg_h: Optional[int] = None
    top: Optional[int] = None
    bottom: Optional[int] = None
    left: Optional[int] = None
    right: Optional[int] = None
    gutter: Optional[int] = None
    num_fmt: Optional[str] = None
    num_start: Optional[int] = None
    bidi: Optional[bool] = None
    title_pg: bool = False
    footer_has_page: Optional[bool] = None   # None = no footer reference (inherits or none)
    footer_refs: int = 0
    first_para: int = 0
    last_para: int = 0


@dataclass
class Paragraph:
    idx: int
    text: str
    runs: List[Run]
    style_id: Optional[str]
    style_name: Optional[str]
    bidi: bool                      # effective paragraph direction (w:bidi through style chain/section)
    bidi_direct: Optional[bool]
    jc: Optional[str]
    line: Optional[int]
    line_rule: Optional[str]
    section: int
    in_table: bool = False
    table_id: Optional[int] = None
    heading_level: Optional[int] = None
    fields: List[str] = field(default_factory=list)       # instrText of fields that start in this paragraph
    in_field: List[str] = field(default_factory=list)     # kinds of fields open while this paragraph is read (TOC, ...)
    has_drawing: bool = False
    has_page_break_before: bool = False
    list_level: Optional[int] = None

    @property
    def is_toc(self) -> bool:
        return any(k in ("TOC",) for k in self.in_field) or (self.style_name or "").lower().startswith(("toc", "table of"))


@dataclass
class Table:
    id: int
    bidi_visual: Optional[bool]
    rows: int
    cols: int
    first_para: int
    last_para: int


@dataclass
class Document:
    path: str
    paragraphs: List[Paragraph]
    sections: List[Section]
    tables: List[Table]
    unsupported: Dict[str, int]
    default_rpr: Dict[str, object]
    default_lang_bidi: Optional[str]
    has_toc: bool
    has_tof: bool                    # list of figures/tables field (TOC \c)
    raw_parts: List[str]
    kind: str = "docx"


# ------------------------------------------------------------------ styles


class Styles:
    def __init__(self, root: Optional[ET.Element], theme_fonts: Dict[str, str]):
        self.by_id: Dict[str, ET.Element] = {}
        self.default_p: Optional[ET.Element] = None
        self.default_r: Optional[ET.Element] = None
        self.default_para_style: Optional[str] = None
        self.default_char_style: Optional[str] = None
        self.theme = theme_fonts
        if root is None:
            return
        dd = root.find("w:docDefaults", NS)
        if dd is not None:
            self.default_r = dd.find("w:rPrDefault/w:rPr", NS)
            self.default_p = dd.find("w:pPrDefault/w:pPr", NS)
        for st in root.findall("w:style", NS):
            sid = st.get(q("w:styleId"))
            if sid:
                self.by_id[sid] = st
            if st.get(q("w:default")) in ("1", "true"):
                if st.get(q("w:type")) == "paragraph":
                    self.default_para_style = sid
                elif st.get(q("w:type")) == "character":
                    self.default_char_style = sid

    def chain(self, sid: Optional[str]) -> List[ET.Element]:
        out, seen = [], set()
        while sid and sid in self.by_id and sid not in seen:
            seen.add(sid)
            st = self.by_id[sid]
            out.append(st)
            b = st.find("w:basedOn", NS)
            sid = b.get(q("w:val")) if b is not None else None
        return list(reversed(out))   # base first

    def name(self, sid: Optional[str]) -> Optional[str]:
        st = self.by_id.get(sid or "")
        if st is None:
            return None
        n = st.find("w:name", NS)
        return n.get(q("w:val")) if n is not None else None


def _font(rfonts: ET.Element, slot: str, theme: Dict[str, str]) -> Optional[str]:
    """slot: ascii | cs.  Direct name wins over theme reference (as Word does)."""
    v = rfonts.get(q("w:" + slot))
    if v:
        return v
    th = rfonts.get(q("w:" + slot + "Theme"))
    if th:
        return theme.get(th)
    return None


def _apply_rpr(acc: Dict[str, object], rpr: Optional[ET.Element], theme: Dict[str, str]) -> None:
    if rpr is None:
        return
    rf = rpr.find("w:rFonts", NS)
    if rf is not None:
        a = _font(rf, "ascii", theme) or _font(rf, "hAnsi", theme)
        if a:
            acc["ascii_font"] = a
        c = _font(rf, "cs", theme)
        if c:
            acc["cs_font"] = c
    for tag, key in (("w:sz", "sz"), ("w:szCs", "szcs")):
        e = rpr.find(tag, NS)
        if e is not None and e.get(q("w:val")):
            try:
                acc[key] = int(e.get(q("w:val")))      # half-points
            except ValueError:
                pass
    for tag, key in (("w:b", "bold"), ("w:bCs", "bold_cs"), ("w:rtl", "rtl"), ("w:i", "italic")):
        v = onoff(rpr.find(tag, NS))
        if v is not None:
            acc[key] = v
    lg = rpr.find("w:lang", NS)
    if lg is not None and lg.get(q("w:bidi")):
        acc["lang_bidi"] = lg.get(q("w:bidi"))


def _apply_ppr(acc: Dict[str, object], ppr: Optional[ET.Element]) -> None:
    if ppr is None:
        return
    v = onoff(ppr.find("w:bidi", NS))
    if v is not None:
        acc["bidi"] = v
    jc = ppr.find("w:jc", NS)
    if jc is not None:
        acc["jc"] = jc.get(q("w:val"))
    sp = ppr.find("w:spacing", NS)
    if sp is not None:
        if sp.get(q("w:line")):
            try:
                acc["line"] = int(sp.get(q("w:line")))
            except ValueError:
                pass
        if sp.get(q("w:lineRule")):
            acc["line_rule"] = sp.get(q("w:lineRule"))
    ol = ppr.find("w:outlineLvl", NS)
    if ol is not None and ol.get(q("w:val")) is not None:
        acc["outline"] = int(ol.get(q("w:val")))
    # rPr inside pPr (paragraph mark) is intentionally ignored for text runs
    np_ = ppr.find("w:numPr/w:ilvl", NS)
    if np_ is not None:
        acc["ilvl"] = int(np_.get(q("w:val"), "0"))


# ------------------------------------------------------------------ char classes

_ARABIC_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def is_arabic_script(ch: str) -> bool:
    o = ord(ch)
    return any(a <= o <= b for a, b in _ARABIC_RANGES)


# ------------------------------------------------------------------ reading


def _theme_fonts(z: zipfile.ZipFile) -> Dict[str, str]:
    out: Dict[str, str] = {}
    names = [n for n in z.namelist() if n.startswith("word/theme/") and n.endswith(".xml")]
    if not names:
        return out
    root = ET.fromstring(z.read(names[0]))
    fs = root.find(".//a:fontScheme", NS)
    if fs is None:
        return out
    for kind, minor in (("majorFont", "major"), ("minorFont", "minor")):
        f = fs.find("a:" + kind, NS)
        if f is None:
            continue
        lat = f.find("a:latin", NS)
        if lat is not None:
            out[minor + "Ascii"] = out[minor + "HAnsi"] = lat.get("typeface")
        cs = f.find("a:cs", NS)
        csf = cs.get("typeface") if cs is not None else ""
        for sc in f.findall("a:font", NS):
            if sc.get("script") == "Arab":
                csf = sc.get("typeface") or csf
        if csf:
            out[minor + "Bidi"] = csf
    return out


def _rels(z: zipfile.ZipFile, part: str) -> Dict[str, str]:
    d, f = part.rsplit("/", 1)
    rp = f"{d}/_rels/{f}.rels"
    if rp not in z.namelist():
        return {}
    root = ET.fromstring(z.read(rp))
    return {r.get("Id"): r.get("Target") for r in root}


def _footer_has_page(z: zipfile.ZipFile, target: str) -> bool:
    name = "word/" + target if not target.startswith("/") else target[1:]
    if name not in z.namelist():
        return False
    root = ET.fromstring(z.read(name))
    for it in root.iter(q("w:instrText")):
        if (it.text or "").strip().upper().startswith("PAGE"):
            return True
    for f in root.iter(q("w:fldSimple")):
        if (f.get(q("w:instr")) or "").strip().upper().startswith("PAGE"):
            return True
    return False


def _section_from(sp: ET.Element, idx: int, z, rels) -> Section:
    s = Section(index=idx)
    pm = sp.find("w:pgMar", NS)
    if pm is not None:
        def gi(n):
            v = pm.get(q("w:" + n))
            try:
                return int(v) if v is not None else None
            except ValueError:
                return None
        s.top, s.bottom, s.left, s.right, s.gutter = gi("top"), gi("bottom"), gi("left"), gi("right"), gi("gutter")
    ps = sp.find("w:pgSz", NS)
    if ps is not None:
        for n, a in (("w", "pg_w"), ("h", "pg_h")):
            v = ps.get(q("w:" + n))
            if v and v.isdigit():
                setattr(s, a, int(v))
    pn = sp.find("w:pgNumType", NS)
    if pn is not None:
        s.num_fmt = pn.get(q("w:fmt"))
        v = pn.get(q("w:start"))
        s.num_start = int(v) if v and v.lstrip("-").isdigit() else None
    s.bidi = onoff(sp.find("w:bidi", NS))
    s.title_pg = onoff(sp.find("w:titlePg", NS)) is True
    refs = sp.findall("w:footerReference", NS)
    s.footer_refs = len(refs)
    if refs:
        s.footer_has_page = any(
            _footer_has_page(z, rels.get(r.get(q("r:id")), "")) for r in refs if rels.get(r.get(q("r:id"))))
    return s


def read_docx(path: str) -> Document:
    z = zipfile.ZipFile(path)
    if "word/document.xml" not in z.namelist():
        raise ValueError("not a Word document: word/document.xml is missing")
    root = ET.fromstring(z.read("word/document.xml"))
    theme = _theme_fonts(z)
    sroot = ET.fromstring(z.read("word/styles.xml")) if "word/styles.xml" in z.namelist() else None
    styles = Styles(sroot, theme)
    rels = _rels(z, "word/document.xml")
    body = root.find("w:body", NS)
    unsupported = {"text_boxes": 0, "tracked_deletions": 0, "equations": 0, "content_controls": 0, "footnotes": 0}
    unsupported["text_boxes"] = len(list(root.iter(q("w:txbxContent"))))
    unsupported["tracked_deletions"] = len(list(root.iter(q("w:del"))))
    unsupported["equations"] = len(list(root.iter("{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath")))
    unsupported["content_controls"] = len(list(root.iter(q("w:sdt"))))
    if "word/footnotes.xml" in z.namelist():
        fr = ET.fromstring(z.read("word/footnotes.xml"))
        unsupported["footnotes"] = max(0, len(fr.findall("w:footnote", NS)) - 2)

    # defaults
    drpr: Dict[str, object] = {}
    _apply_rpr(drpr, styles.default_r, theme)
    dppr: Dict[str, object] = {}
    _apply_ppr(dppr, styles.default_p)

    paras: List[Paragraph] = []
    sections: List[Section] = []
    tables: List[Table] = []
    field_stack: List[Dict[str, object]] = []
    st = {"sec": 0, "tbl": 0, "has_toc": False, "has_tof": False}

    def para_style_acc(sid: Optional[str]):
        acc_r, acc_p = dict(drpr), dict(dppr)
        sid = sid or styles.default_para_style
        for s in styles.chain(sid):
            _apply_rpr(acc_r, s.find("w:rPr", NS), theme)
            _apply_ppr(acc_p, s.find("w:pPr", NS))
        return acc_r, acc_p

    def do_p(p: ET.Element, in_table: bool, table_id: Optional[int]) -> None:
        ppr = p.find("w:pPr", NS)
        sid = None
        if ppr is not None and ppr.find("w:pStyle", NS) is not None:
            sid = ppr.find("w:pStyle", NS).get(q("w:val"))
        base_r, acc_p = para_style_acc(sid)
        direct_p: Dict[str, object] = {}
        _apply_ppr(direct_p, ppr)
        acc_p.update(direct_p)
        runs: List[Run] = []
        fields_started: List[str] = []
        in_field_kinds: List[str] = [f["kind"] for f in field_stack if f["kind"]]
        has_drawing = False
        text_parts: List[str] = []

        def run(r: ET.Element) -> None:
            nonlocal has_drawing
            rpr = r.find("w:rPr", NS)
            acc = dict(base_r)
            cs = rpr.find("w:rStyle", NS) if rpr is not None else None
            if cs is not None:
                for s in styles.chain(cs.get(q("w:val"))):
                    _apply_rpr(acc, s.find("w:rPr", NS), theme)
            elif styles.default_char_style:
                pass
            direct: Dict[str, object] = {}
            _apply_rpr(direct, rpr, theme)
            acc.update(direct)
            buf: List[str] = []
            visible = not field_stack or field_stack[-1]["phase"] != "instr"
            for ch in r:
                t = ch.tag
                if t == q("w:t"):
                    if visible:
                        buf.append(ch.text or "")
                elif t == q("w:tab"):
                    if visible:
                        buf.append("\t")
                elif t in (q("w:br"), q("w:cr")):
                    if ch.get(q("w:type")) != "page" and visible:
                        buf.append("\n")
                elif t == q("w:noBreakHyphen"):
                    buf.append("\u2011")
                elif t == q("w:instrText"):
                    if field_stack:
                        field_stack[-1]["instr"] += ch.text or ""
                elif t == q("w:fldChar"):
                    ft = ch.get(q("w:fldCharType"))
                    if ft == "begin":
                        field_stack.append({"instr": "", "phase": "instr", "kind": None})
                    elif ft == "separate" and field_stack:
                        f = field_stack[-1]
                        f["phase"] = "result"
                        ins = f["instr"].strip()
                        kind = ins.split(None, 1)[0].upper() if ins else ""
                        f["kind"] = kind
                        fields_started.append(ins)
                        if kind == "TOC":
                            st["has_toc"] = True
                            if re.search(r"\\c\b", ins):
                                st["has_tof"] = True
                    elif ft == "end" and field_stack:
                        f = field_stack.pop()
                        if f["phase"] == "instr":     # field without result
                            fields_started.append(f["instr"].strip())
                elif t in (q("w:drawing"), q("w:pict")):
                    has_drawing = True
            txt = "".join(buf)
            if txt:
                text_parts.append(txt)
                runs.append(Run(txt, acc, direct.get("rtl"), any(is_arabic_script(c) for c in txt)))

        def walk(el: ET.Element) -> None:
            for ch in el:
                t = ch.tag
                if t == q("w:r"):
                    run(ch)
                elif t == q("w:fldSimple"):
                    ins = (ch.get(q("w:instr")) or "").strip()
                    fields_started.append(ins)
                    if ins.upper().startswith("TOC"):
                        st["has_toc"] = True
                    walk(ch)
                elif t in (q("w:hyperlink"), q("w:ins"), q("w:smartTag"), q("w:sdt"), q("w:sdtContent"),
                           q("w:customXml"), q("w:moveTo")):
                    walk(ch)

        walk(p)
        text = "".join(text_parts)
        sname = styles.name(sid or styles.default_para_style)
        sec = st["sec"]
        heading = None
        sn = (sname or "").lower()
        m = re.match(r"(?:heading|عنوان)\s*(\d)", sn)
        if m:
            heading = int(m.group(1))
        elif "outline" in acc_p and isinstance(acc_p["outline"], int) and acc_p["outline"] < 9:
            heading = acc_p["outline"] + 1
        para = Paragraph(
            idx=len(paras), text=text, runs=runs, style_id=sid or styles.default_para_style, style_name=sname,
            bidi=bool(acc_p.get("bidi", False)), bidi_direct=direct_p.get("bidi"), jc=acc_p.get("jc"),
            line=acc_p.get("line"), line_rule=acc_p.get("line_rule"), section=sec, in_table=in_table,
            table_id=table_id, heading_level=heading, fields=fields_started, in_field=in_field_kinds,
            has_drawing=has_drawing, has_page_break_before=onoff(ppr.find("w:pageBreakBefore", NS)) is True if ppr is not None else False,
            list_level=acc_p.get("ilvl") if (ppr is not None and ppr.find("w:numPr", NS) is not None) or "ilvl" in acc_p else None,
        )
        paras.append(para)
        if ppr is not None:
            sp = ppr.find("w:sectPr", NS)
            if sp is not None:
                sec_obj = _section_from(sp, st["sec"], z, rels)
                sec_obj.last_para = para.idx
                sections.append(sec_obj)
                st["sec"] += 1

    def blocks(el: ET.Element, in_table=False, table_id=None) -> None:
        for ch in el:
            if ch.tag == q("w:p"):
                do_p(ch, in_table, table_id)
            elif ch.tag == q("w:tbl"):
                st["tbl"] += 1
                tid = st["tbl"]
                first = len(paras)
                rows = ch.findall("w:tr", NS)
                cols = max((len(r.findall("w:tc", NS)) for r in rows), default=0)
                bv = onoff(ch.find("w:tblPr/w:bidiVisual", NS))
                for tr in rows:
                    for tc in tr.findall("w:tc", NS):
                        blocks(tc, True, tid)
                tables.append(Table(tid, bv, len(rows), cols, first, len(paras) - 1))
            elif ch.tag in (q("w:sdt"),):
                c = ch.find("w:sdtContent", NS)
                if c is not None:
                    blocks(c, in_table, table_id)

    blocks(body)
    final = body.find("w:sectPr", NS)
    sec_obj = _section_from(final, st["sec"], z, rels) if final is not None else Section(index=st["sec"])
    sec_obj.last_para = len(paras) - 1
    sections.append(sec_obj)
    prev = 0
    for s in sections:
        s.first_para = prev
        prev = s.last_para + 1
    # section-level bidi flows into paragraphs that have no direct/style value
    for p in paras:
        if p.bidi_direct is None and not p.bidi:
            sb = sections[min(p.section, len(sections) - 1)].bidi
            if sb:
                p.bidi = True
    return Document(path=path, paragraphs=paras, sections=sections, tables=tables, unsupported=unsupported,
                    default_rpr=drpr, default_lang_bidi=drpr.get("lang_bidi"), has_toc=st["has_toc"],
                    has_tof=st["has_tof"], raw_parts=z.namelist())


def read_text(path: str) -> Document:
    """Plain .txt / .md input: one paragraph per non-empty line (text checks only)."""
    data = open(path, "rb").read()
    try:
        s = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        s = data.decode("cp1256", errors="replace")
    paras = []
    for ln in s.splitlines():
        t = ln.rstrip("\n")
        h = None
        m = re.match(r"(#{1,6})\s+(.*)", t)
        if m:
            h, t = len(m.group(1)), m.group(2)
        paras.append(Paragraph(idx=len(paras), text=t, runs=[Run(t, {}, None, any(is_arabic_script(c) for c in t))],
                               style_id=None, style_name=None, bidi=False, bidi_direct=None, jc=None, line=None,
                               line_rule=None, section=0, heading_level=h))
    return Document(path=path, paragraphs=paras, sections=[Section(index=0)], tables=[], unsupported={},
                    default_rpr={}, default_lang_bidi=None, has_toc=False, has_tof=False, raw_parts=[], kind="text")


def load(path: str) -> Document:
    low = path.lower()
    if low.endswith(".docx") or low.endswith(".docm"):
        return read_docx(path)
    if low.endswith((".txt", ".md", ".markdown")):
        return read_text(path)
    raise ValueError("unsupported file type (use .docx, .txt or .md): " + path)
