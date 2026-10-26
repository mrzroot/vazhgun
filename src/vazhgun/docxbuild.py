"""Generate small, realistic-looking .docx files from code (for tests and --demo).

No real thesis is ever used: every fixture is synthetic text written for this project.
"""
from __future__ import annotations

import zipfile
from typing import List, Optional, Sequence, Tuple, Union
from xml.sax.saxutils import escape

WNS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')

Run = Union[str, Tuple[str, str]]     # text or (text, extra rPr xml)


def rpr(extra: str = "", rtl: bool = False, cs_font: Optional[str] = None, szcs: Optional[int] = None,
        sz: Optional[int] = None, ascii_font: Optional[str] = None) -> str:
    parts = []
    if cs_font or ascii_font:
        a = f' w:ascii="{ascii_font}" w:hAnsi="{ascii_font}"' if ascii_font else ""
        c = f' w:cs="{cs_font}"' if cs_font else ""
        parts.append(f"<w:rFonts{a}{c}/>")
    if rtl:
        parts.append("<w:rtl/>")
    if sz:
        parts.append(f'<w:sz w:val="{sz}"/>')
    if szcs:
        parts.append(f'<w:szCs w:val="{szcs}"/>')
    parts.append(extra)
    s = "".join(parts)
    return f"<w:rPr>{s}</w:rPr>" if s else ""


def run_xml(text: str, rpr_xml: str = "") -> str:
    return f'<w:r>{rpr_xml}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def field_runs(instr: str, result: str, rpr_xml: str = "") -> str:
    return (f'<w:r>{rpr_xml}<w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r>{rpr_xml}<w:instrText xml:space="preserve"> {escape(instr)} </w:instrText></w:r>'
            f'<w:r>{rpr_xml}<w:fldChar w:fldCharType="separate"/></w:r>'
            f'{run_xml(result, rpr_xml)}'
            f'<w:r>{rpr_xml}<w:fldChar w:fldCharType="end"/></w:r>')


class Doc:
    def __init__(self, cs_font: str = "B Nazanin", szcs: int = 28, ascii_font: str = "Times New Roman", sz: int = 24,
                 bidi_normal: bool = True, jc: str = "both", line: int = 360,
                 margins: Tuple[int, int, int, int] = (1701, 1701, 1417, 1985),   # top bottom left right (twips)
                 lang_bidi: str = "fa-IR", style_cs: bool = True):
        self.body: List[str] = []
        self.cs_font, self.szcs, self.ascii_font, self.sz = cs_font, szcs, ascii_font, sz
        self.bidi_normal, self.jc, self.line = bidi_normal, jc, line
        self.margins = margins
        self.lang_bidi = lang_bidi
        self.style_cs = style_cs
        self.footers: List[str] = []
        self.default_sect = None
        self.rpr_auto_rtl = True

    # -- paragraphs
    def p(self, content: Union[str, Sequence[Run]] = "", style: Optional[str] = None, bidi: Optional[bool] = None,
          jc: Optional[str] = None, ppr_extra: str = "", rtl: Optional[bool] = None, rpr_extra: str = "",
          cs_font: Optional[str] = None, szcs: Optional[int] = None, sz: Optional[int] = None,
          raw: Optional[str] = None) -> "Doc":
        ppr = ""
        if style:
            ppr += f'<w:pStyle w:val="{style}"/>'
        if bidi is True:
            ppr += "<w:bidi/>"
        elif bidi is False:
            ppr += '<w:bidi w:val="0"/>'
        if jc:
            ppr += f'<w:jc w:val="{jc}"/>'
        ppr += ppr_extra
        ppr = f"<w:pPr>{ppr}</w:pPr>" if ppr else ""
        if raw is not None:
            self.body.append(f"<w:p>{ppr}{raw}</w:p>")
            return self
        runs = [content] if isinstance(content, str) else list(content)
        out = []
        for r in runs:
            t, extra = (r, "") if isinstance(r, str) else r
            use_rtl = rtl if rtl is not None else None
            out.append(run_xml(t, rpr(extra + rpr_extra, rtl=bool(use_rtl), cs_font=cs_font, szcs=szcs, sz=sz)))
        self.body.append(f"<w:p>{ppr}{''.join(out)}</w:p>")
        return self

    def heading(self, text: str, level: int = 1, **kw) -> "Doc":
        return self.p(text, style=f"Heading{level}", **kw)

    def caption_seq(self, label: str, chapter: int, n: int, title: str, sep: str = "-", seq: str = "Figure",
                    style: str = "Caption", **kw) -> "Doc":
        """«شکل ۲-۳: عنوان» with a real SEQ field for the running number."""
        raw = run_xml(f"{label} {chapter}{sep}") + field_runs(f"SEQ {seq} \\* ARABIC", str(n)) + run_xml(f": {title}")
        return self.p(style=style, raw=raw, **kw)

    def page_break(self) -> "Doc":
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        return self

    def toc(self) -> "Doc":
        self.body.append(
            '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>فهرست مطالب</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
        return self

    def table(self, rows: List[List[str]], bidi_visual: bool = False, cell_bidi: bool = True) -> "Doc":
        bv = "<w:bidiVisual/>" if bidi_visual else ""
        trs = []
        for r in rows:
            tcs = []
            for c in r:
                ppr = "<w:pPr><w:bidi/></w:pPr>" if cell_bidi else ""
                tcs.append(f"<w:tc><w:p>{ppr}{run_xml(c)}</w:p></w:tc>")
            trs.append(f"<w:tr>{''.join(tcs)}</w:tr>")
        self.body.append(f'<w:tbl><w:tblPr>{bv}<w:tblW w:w="0" w:type="auto"/></w:tblPr>{"".join(trs)}</w:tbl>')
        return self

    # -- sections
    def sectpr(self, fmt: Optional[str] = None, start: Optional[int] = None, footer: Optional[int] = None,
               margins: Optional[Tuple[int, int, int, int]] = None, bidi: bool = False, title_pg: bool = False) -> str:
        t, b, l, r = margins or self.margins
        pn = ""
        if fmt or start is not None:
            pn = "<w:pgNumType" + (f' w:fmt="{fmt}"' if fmt else "") + (f' w:start="{start}"' if start is not None else "") + "/>"
        fr = f'<w:footerReference w:type="default" r:id="rIdF{footer}"/>' if footer else ""
        return (f'<w:sectPr>{fr}<w:pgSz w:w="11906" w:h="16838"/>'
                f'<w:pgMar w:top="{t}" w:right="{r}" w:bottom="{b}" w:left="{l}" w:header="708" w:footer="708" w:gutter="0"/>'
                f'{pn}{"<w:bidi/>" if bidi else ""}{"<w:titlePg/>" if title_pg else ""}</w:sectPr>')

    def end_section(self, **kw) -> "Doc":
        self.body.append(f"<w:p><w:pPr>{self.sectpr(**kw)}</w:pPr></w:p>")
        return self

    def add_footer(self, with_page: bool = True) -> int:
        n = len(self.footers) + 1
        inner = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
                 '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
                 if with_page else "")
        self.footers.append(f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {WNS}><w:p><w:pPr><w:jc w:val="center"/></w:pPr>{inner}</w:p></w:ftr>')
        return n

    # -- packaging
    def styles_xml(self) -> str:
        cs = f' w:cs="{self.cs_font}"' if self.cs_font else ""
        szcs = f'<w:szCs w:val="{self.szcs}"/>' if self.szcs else ""
        rfonts = f'<w:rFonts w:ascii="{self.ascii_font}" w:hAnsi="{self.ascii_font}"{cs}/>'
        bidi = "<w:bidi/>" if self.bidi_normal else ""
        jc = f'<w:jc w:val="{self.jc}"/>' if self.jc else ""
        lang = f'<w:lang w:val="en-US" w:bidi="{self.lang_bidi}"/>' if self.lang_bidi else ""
        def hs(i, sz, szc):
            return (f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/><w:basedOn w:val="Normal"/>'
                    f'<w:pPr><w:keepNext/><w:outlineLvl w:val="{i-1}"/><w:jc w:val="right"/></w:pPr>'
                    f'<w:rPr><w:b/><w:bCs/><w:sz w:val="{sz}"/><w:szCs w:val="{szc}"/></w:rPr></w:style>')
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {WNS}>'
                f'<w:docDefaults><w:rPrDefault><w:rPr>{rfonts}<w:sz w:val="{self.sz}"/>{szcs}{lang}</w:rPr></w:rPrDefault>'
                f'<w:pPrDefault><w:pPr><w:spacing w:line="{self.line}" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
                f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr>{bidi}{jc}</w:pPr></w:style>'
                + hs(1, 32, 36) + hs(2, 28, 32) + hs(3, 26, 28) +
                '<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/>'
                '<w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:bCs/></w:rPr></w:style>'
                '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/></w:pPr></w:style>'
                '</w:styles>')

    def save(self, path: str) -> str:
        final = self.default_sect or self.sectpr(footer=1 if self.footers else None)
        doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {WNS}><w:body>{"".join(self.body)}{final}</w:body></w:document>'
        ct = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              + "".join(f'<Override PartName="/word/footer{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                        for i in range(1, len(self.footers) + 1)) + '</Types>')
        rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        drels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                 + "".join(f'<Relationship Id="rIdF{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer{i}.xml"/>'
                           for i in range(1, len(self.footers) + 1)) + '</Relationships>')
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("_rels/.rels", rels)
            z.writestr("word/document.xml", doc)
            z.writestr("word/styles.xml", self.styles_xml())
            z.writestr("word/_rels/document.xml.rels", drels)
            for i, f in enumerate(self.footers, 1):
                z.writestr(f"word/footer{i}.xml", f)
        return path
