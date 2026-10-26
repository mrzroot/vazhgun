"""Chain-direction audit (V-codes), the --fix copy writer and the CLI, driven by the synthetic sample chapter.

A "chain" is a run of numbers joined by - / . : such as «شکل ۲-۳» or «۱۴۰۳/۰۵/۱۲». Word draws it left-to-right or
right-to-left depending on the characters around it, so one document can show the same pattern two ways.
"""
import json
import os
import zipfile

import pytest

from vazhgun import checks, cli, fixer, sample, uba
from vazhgun.docxbuild import Doc
from vazhgun.docxio import load

RLM, LRM = "\u200f", "\u200e"          # right-to-left / left-to-right marks: invisible, direction-only
CHAIN_KINDS = ("caption-number", "page-range", "year-range", "range", "date")


@pytest.fixture()
def flawed(tmp_path):
    return sample.chapter(str(tmp_path / "flawed.docx"))


def codes(path):
    """[(code, severity)] of every finding in the .docx at *path*."""
    return [(f.code, f.severity) for f in checks.analyse(load(path))]


def findings(path, code):
    """The findings with the given *code* in the .docx at *path*."""
    return [x for x in checks.analyse(load(path)) if x.code == code]


def chain_orders(path):
    """The set of drawing orders ('rtl'/'ltr') of all number chains inside right-to-left paragraphs."""
    orders = set()
    for p in load(path).paragraphs:
        if not p.bidi:
            continue
        for m in checks.CHAIN_RE.finditer(p.text):
            if checks._kind(p.text, m, p) in CHAIN_KINDS:
                orders.add(checks.chain_order(p.text, m, True))
    return orders


def test_flawed_chapter_reports_each_problem(flawed):
    got = {c for c, _ in codes(flawed)}
    assert {"V101", "V103", "V104", "V201", "V202", "V203"} <= got


def test_clean_chapter_has_no_findings(tmp_path):
    p = sample.chapter(str(tmp_path / "ok.docx"), flawed=False, marks="reading")
    assert codes(p) == []


def test_unmarked_but_consistent_chapter_gets_only_notes_and_the_inconsistency_warning(tmp_path):
    p = sample.chapter(str(tmp_path / "u.docx"), flawed=False, marks="none")
    sev = {s for c, s in codes(p) if c.startswith("V2")}
    assert sev == {"info", "warn"}
    assert not any(s == "error" for _, s in codes(p))


def test_inconsistency_is_found_because_context_changes_the_drawing(flawed):
    f = findings(flawed, "V202")
    assert {x.extra["order"] for x in f} == {"ltr"}           # «Fig. ۲-۳» and «(۲-۴)» differ from «شکل ۲-۱»
    assert all(x.segments for x in f)


def test_sign_after_number_finding_has_a_preview(flawed):
    f = findings(flawed, "V203")
    assert len(f) == 1 and f[0].fixable and "۵" in f[0].typed


def test_fix_reading_resolves_everything_and_orders_agree(flawed, tmp_path):
    dst = str(tmp_path / "fixed.docx")
    st = fixer.fix_docx(flawed, dst, chains="reading", strip_controls=True)
    assert st["bidi"] == 1 and st["table"] == 1 and st["signs"] == 1 and st["controls"] == 1 and st["chains"] >= 8
    assert codes(dst) == []
    assert chain_orders(dst) == {"rtl"}


def test_fix_ltr_makes_every_chain_left_to_right(flawed, tmp_path):
    dst = str(tmp_path / "fixed.docx")
    fixer.fix_docx(flawed, dst, chains="ltr", strip_controls=True)
    assert codes(dst) == []
    assert chain_orders(dst) == {"ltr"}


def test_fix_without_options_only_touches_direction_and_table_signs(flawed, tmp_path):
    dst = str(tmp_path / "fixed.docx")
    fixer.fix_docx(flawed, dst)
    got = {c for c, severity in codes(dst) if severity == "error"}
    assert got == {"V104"}                  # controls are only removed on request


def test_fix_changes_nothing_but_document_xml(flawed, tmp_path):
    dst = str(tmp_path / "fixed.docx")
    fixer.fix_docx(flawed, dst, chains="reading")
    a, b = zipfile.ZipFile(flawed), zipfile.ZipFile(dst)
    assert a.namelist() == b.namelist()
    for n in a.namelist():
        if n != "word/document.xml":
            assert a.read(n) == b.read(n)


def visible(text):
    """*text* without direction controls (embeddings, isolates, RLM/LRM): only what a reader sees."""
    return "".join(c for c in text if c not in uba.EXPLICIT and c not in (RLM, LRM))


def test_fix_never_changes_visible_letters(flawed, tmp_path):
    dst = str(tmp_path / "fixed.docx")
    fixer.fix_docx(flawed, dst, chains="reading", strip_controls=True)
    for before, after in zip(load(flawed).paragraphs, load(dst).paragraphs):
        assert visible(before.text) == visible(after.text)


def test_fix_survives_xml_special_characters(tmp_path):
    d = Doc()
    d.p("فرمول <a> & «b» در شکل ۲-۳ و -۴ آمده است.", bidi=False)
    src = d.save(str(tmp_path / "x.docx"))
    dst = str(tmp_path / "y.docx")
    fixer.fix_docx(src, dst, chains="reading")
    assert "<a> & «b»" in load(dst).paragraphs[0].text


def test_cli_exit_codes_json_and_strict(flawed, tmp_path, capsys):
    assert cli.main([flawed, "--json"]) == 1                       # errors present
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["errors"] >= 2 and data["findings"][0]["code"].startswith("V")
    assert "segments" in data["findings"][-1]
    ok = sample.chapter(str(tmp_path / "ok.docx"), flawed=False, marks="reading")
    assert cli.main([ok, "--strict"]) == 0
    warn_only = sample.chapter(str(tmp_path / "w.docx"), flawed=False, marks="none")
    assert cli.main([warn_only]) == 0
    assert cli.main([warn_only, "--strict"]) == 1
    capsys.readouterr()


def test_cli_fix_writes_copy_and_refuses_to_overwrite(flawed, tmp_path, capsys):
    assert cli.main([flawed, "--fix", "--chains", "reading", "--no-color"]) == 1       # report is about the original
    assert os.path.exists(flawed.replace(".docx", ".vazhgun.docx"))
    assert cli.main([flawed, "--fix", "-o", flawed]) == 2
    capsys.readouterr()


def test_cli_bad_inputs(tmp_path, capsys):
    assert cli.main([str(tmp_path / "missing.docx")]) == 2
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip")
    assert cli.main([str(bad)]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_cli_demo_and_sample(tmp_path, capsys):
    assert cli.main(["--demo"]) == 1          # the demo chapter has errors on purpose
    assert "V201" in capsys.readouterr().out
    out = str(tmp_path / "s.docx")
    assert cli.main(["--make-sample", out]) == 0 and os.path.exists(out)
    capsys.readouterr()


def test_text_file_input(tmp_path, capsys):
    t = tmp_path / "a.txt"
    t.write_text("این یک بند فارسی است.\n\nThis is English.\n", encoding="utf-8")
    assert cli.main([str(t)]) in (0, 1)
    capsys.readouterr()


def test_report_makes_bidi_marks_visible(flawed):
    f = findings(flawed, "V104")[0]
    assert "⟨RLE⟩" in f.snippet or "RLE" in f.why


def test_fix_is_idempotent(flawed, tmp_path):
    a, b = str(tmp_path / "a.docx"), str(tmp_path / "b.docx")
    fixer.fix_docx(flawed, a, chains="ltr", strip_controls=True)
    st = fixer.fix_docx(a, b, chains="ltr", strip_controls=True)
    assert st["bidi"] == st["table"] == st["signs"] == 0
    assert [p.text for p in load(a).paragraphs] == [p.text for p in load(b).paragraphs]


def test_dates_are_reported_with_the_renderer_note(flawed):
    f = [x for x in checks.analyse(load(flawed)) if x.code == "V201" and "dates" in x.title]
    assert f and "day-first" in f[0].why


def test_demo_json_and_fix_guard(capsys):
    assert cli.main(["--demo", "--json"]) == 1
    d = json.loads(capsys.readouterr().out)
    assert {f["code"] for f in d["findings"]} >= {"V101", "V103", "V104", "V201", "V202", "V203"}
    with pytest.raises(SystemExit):
        cli.main(["--demo", "--fix"])
