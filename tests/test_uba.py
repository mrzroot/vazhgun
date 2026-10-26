import random

import pytest

from vazhgun import uba

bidi = pytest.importorskip("bidi.algorithm", reason="python-bidi is the test oracle (pip install python-bidi)")

BASE = list("سلامکتابمنیوهرد") + list("abcXYZ") + list("۰۱۲۳۴۵۶۷۸۹") + list("0123456789") + list("-/.:, \u200f\u200e\u200c") + ["\u064e"]
BRACKETS = list("()[]")


def ref_display(s, rtl):
    return bidi.get_display(s, base_dir="R" if rtl else "L")


def test_display_matches_python_bidi_without_brackets():
    # python-bidi 0.6 resolves some bracket pairs differently from the Unicode text (and from FriBidi, see below),
    # so this oracle is used on bracket-free strings and the bracket rules are checked against FriBidi.
    rnd = random.Random(2026)
    bad = []
    for _ in range(2000):
        s = "".join(rnd.choice(BASE) for _ in range(rnd.randint(1, 14)))
        for rtl in (True, False):
            mine, ref = uba.display(s, rtl), ref_display(s, rtl)
            if mine.replace("\u200c", "") != ref.replace("\u200c", ""):
                bad.append((s, rtl, mine, ref))
    assert not bad, bad[:3]


def _fribidi():
    import ctypes
    import ctypes.util
    name = ctypes.util.find_library("fribidi")
    if not name:
        pytest.skip("libfribidi not installed")
    return ctypes.CDLL(name)


def test_levels_match_fribidi_including_brackets():
    import ctypes
    lib = _fribidi()

    def levels(s, rtl):
        n = len(s)
        cp = (ctypes.c_uint32 * n)(*[ord(c) for c in s])
        types = (ctypes.c_uint32 * n)()
        lib.fribidi_get_bidi_types(cp, n, types)
        br = (ctypes.c_uint32 * n)()
        lib.fribidi_get_bracket_types(cp, n, types, br)
        lv = (ctypes.c_int8 * n)()
        base = ctypes.c_uint32(0x111 if rtl else 0x110)
        assert lib.fribidi_get_par_embedding_levels_ex(types, br, n, ctypes.byref(base), lv) > 0
        return list(lv)
    rnd = random.Random(7)
    alphabet = BASE + BRACKETS
    bad = []
    for _ in range(3000):
        s = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(1, 12)))
        for rtl in (True, False):
            a, b = uba.resolve(s, rtl), levels(s, rtl)
            # BN (ZWNJ) is removed by rule X9 and gets no level of its own: compare everything else
            if [x for x, ch in zip(a, s) if ch != "\u200c"] != [x for x, ch in zip(b, s) if ch != "\u200c"]:
                bad.append((s, rtl))
    assert not bad, bad[:3]


def test_digits_after_arabic_script_letters_become_arabic_numbers_W2():
    # the hyphen is not joined to the digits there: reading order stays right-to-left
    assert uba.display("مطابق شکل ۲-۱ شبکه", True) == "هکبش ۱-۲ لکش قباطم"


def test_chain_after_latin_letter_is_one_left_to_right_run():
    segs = uba.segments("Fig. ۲-۳", True)
    assert any("۲-۳" in t and not r for r, t in segs)


def test_chain_at_line_start_is_left_to_right():
    assert uba.display("(۲-۴)", True).replace("(", "").replace(")", "") == "۲-۴"


def test_slash_date_stays_left_to_right_after_persian():
    # CS between two Arabic-number digits joins them (W4)
    assert uba.display("تاریخ ۱۴۰۳/۰۵/۱۲ است", True).count("۱۴۰۳/۰۵/۱۲") == 1


def test_segments_cover_text_once():
    s = "نتیجه در جدول ۲-۲ و Fig. 3 آمد."
    segs = uba.segments(s, True)
    assert sorted("".join(t for _, t in segs)) == sorted(s)
