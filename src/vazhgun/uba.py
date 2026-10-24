"""A small implementation of the Unicode Bidirectional Algorithm (UAX #9) for ONE paragraph.

Scope (on purpose): implicit levels only -- weak types W1-W7, brackets N0, neutrals N1-N2, implicit levels
I1-I2, trailing whitespace L1, reordering L2 and mirroring L4. Explicit embeddings, overrides and isolates
(LRE RLE LRO RLO PDF LRI RLI FSI PDI) are NOT interpreted: ``resolve`` raises ``Unsupported`` so callers can
say so instead of guessing. The tests compare the result with the independent ``python-bidi`` package on
thousands of random strings (test-only dependency).

This is the *standard's* answer. Microsoft Word, LibreOffice, Google Docs and PDF viewers each have small
deviations, which is why vazhgun labels every preview "approximate" and mainly flags places where the
answer depends on the renderer.
"""
from __future__ import annotations

import unicodedata
from typing import List, Tuple

EXPLICIT = set("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
BRACKETS = {"(": ")", "[": "]", "{": "}", "\u2329": "\u232a", "\u2768": "\u2769", "\u27e8": "\u27e9",
            "\u3008": "\u3009", "\u300a": "\u300b", "\u300c": "\u300d", "\u300e": "\u300f", "\u3010": "\u3011",
            "\u3014": "\u3015"}
CLOSERS = {v: k for k, v in BRACKETS.items()}
MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<", "\u00ab": "\u00bb",
          "\u00bb": "\u00ab", "\u2039": "\u203a", "\u203a": "\u2039"}
MIRROR.update(BRACKETS)
MIRROR.update(CLOSERS)


class Unsupported(Exception):
    pass


def bidi_class(ch: str) -> str:
    return unicodedata.bidirectional(ch)


def has_explicit(text: str) -> bool:
    return any(c in EXPLICIT for c in text)


def resolve(text: str, rtl: bool = True) -> List[int]:
    """Return the resolved embedding level of every character (BN chars take the previous level)."""
    if has_explicit(text):
        raise Unsupported("explicit embedding/override/isolate characters")
    n = len(text)
    base = 1 if rtl else 0
    sos = eos = "R" if rtl else "L"
    cls = [bidi_class(c) for c in text]
    keep = [i for i in range(n) if cls[i] != "BN"]
    t = [cls[i] for i in keep]
    chars = [text[i] for i in keep]
    m = len(t)

    # W1
    prev = sos
    for i in range(m):
        if t[i] == "NSM":
            t[i] = prev
        prev = t[i]
    # W2
    last = sos
    for i in range(m):
        if t[i] in ("L", "R", "AL"):
            last = t[i]
        elif t[i] == "EN" and last == "AL":
            t[i] = "AN"
    # W3
    t = ["R" if x == "AL" else x for x in t]
    # W4
    for i in range(1, m - 1):
        if t[i] == "ES" and t[i - 1] == "EN" and t[i + 1] == "EN":
            t[i] = "EN"
        elif t[i] == "CS" and t[i - 1] == t[i + 1] and t[i - 1] in ("EN", "AN"):
            t[i] = t[i - 1]
    # W5
    i = 0
    while i < m:
        if t[i] == "ET":
            j = i
            while j < m and t[j] == "ET":
                j += 1
            if (i > 0 and t[i - 1] == "EN") or (j < m and t[j] == "EN"):
                for k in range(i, j):
                    t[k] = "EN"
            i = j
        else:
            i += 1
    # W6
    t = ["ON" if x in ("ES", "ET", "CS") else x for x in t]
    # W7
    last = sos
    for i in range(m):
        if t[i] in ("L", "R"):
            last = t[i]
        elif t[i] == "EN" and last == "L":
            t[i] = "L"

    e = "R" if rtl else "L"

    def strong(x: str) -> str:
        return "R" if x in ("R", "EN", "AN") else ("L" if x == "L" else "")

    # N0: bracket pairs
    pairs: List[Tuple[int, int]] = []
    stack: List[Tuple[str, int]] = []
    for i in range(m):
        if t[i] != "ON":
            continue
        c = chars[i]
        if c in BRACKETS:
            if len(stack) >= 63:
                break
            stack.append((BRACKETS[c], i))
        elif c in CLOSERS:
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0] == c:
                    pairs.append((stack[k][1], i))
                    del stack[k:]
                    break
    pairs.sort()
    for o, c in pairs:
        inside = {strong(x) for x in t[o + 1:c]} - {""}
        if not inside:
            continue
        if e in inside:
            new = e
        else:
            ctx = sos
            for k in range(o - 1, -1, -1):
                s = strong(t[k])
                if s:
                    ctx = s
                    break
            new = ctx if ctx != e else e
            # opposite direction found inside: use context before the opening bracket
            new = ctx if ctx != e else e
        t[o] = t[c] = new
        # NSM following the brackets take the bracket's direction (original NSM chars)
        for pos in (o, c):
            k = pos + 1
            while k < m and cls[keep[k]] == "NSM":
                t[k] = new
                k += 1
    # N1 / N2
    i = 0
    neutral = {"B", "S", "WS", "ON", "LRI", "RLI", "FSI", "PDI"}
    while i < m:
        if t[i] in neutral:
            j = i
            while j < m and t[j] in neutral:
                j += 1
            before = strong(t[i - 1]) if i > 0 else sos
            after = strong(t[j]) if j < m else eos
            new = before if before == after and before else e
            for k in range(i, j):
                t[k] = new
            i = j
        else:
            i += 1
    # I1 / I2
    lv = []
    for x in t:
        if base == 0:
            lv.append(0 if x == "L" else (1 if x == "R" else 2))
        else:
            lv.append(1 if x == "R" else 2)
    # L1: trailing whitespace (and separators) go to paragraph level
    for k in range(m - 1, -1, -1):
        if cls[keep[k]] in ("WS", "S", "B", "FSI", "LRI", "RLI", "PDI"):
            lv[k] = base
        else:
            break
    for k in range(m):
        if cls[keep[k]] in ("S", "B"):
            lv[k] = base
            q = k - 1
            while q >= 0 and cls[keep[q]] in ("WS",):
                lv[q] = base
                q -= 1
    out = [base] * n
    last_lv = base
    kk = 0
    for i in range(n):
        if kk < m and keep[kk] == i:
            last_lv = lv[kk]
            kk += 1
        out[i] = last_lv
    return out


def visual_order(levels: List[int]) -> List[int]:
    """L2: logical indices in left-to-right display order."""
    order = list(range(len(levels)))
    if not levels:
        return order
    hi = max(levels)
    lo = min(l for l in levels if l % 2 == 1) if any(l % 2 for l in levels) else hi + 1
    for lev in range(hi, lo - 1, -1):
        i = 0
        while i < len(order):
            if levels[order[i]] >= lev:
                j = i
                while j < len(order) and levels[order[j]] >= lev:
                    j += 1
                order[i:j] = reversed(order[i:j])
                i = j
            else:
                i += 1
    return order


def display(text: str, rtl: bool = True) -> str:
    """Visual string (left to right) as UAX #9 would draw it, with mirrored brackets."""
    lv = resolve(text, rtl)
    out = []
    for i in visual_order(lv):
        ch = text[i]
        if lv[i] % 2 == 1 and ch in MIRROR:
            ch = MIRROR[ch]
        out.append(ch)
    return "".join(out)


def positions(text: str, rtl: bool = True) -> List[int]:
    """For each logical index, its visual (left-to-right) slot."""
    order = visual_order(resolve(text, rtl))
    pos = [0] * len(order)
    for slot, i in enumerate(order):
        pos[i] = slot
    return pos


def segments(text: str, rtl: bool = True) -> List[Tuple[bool, str]]:
    """The drawing as runs, left to right: (is_right_to_left, text in LOGICAL order).

    Each run is a maximal stretch of consecutive drawn characters with the same level parity. Showing runs
    (instead of a letter-reversed string) keeps the preview readable in bidi-aware viewers and terminals.
    """
    lv = resolve(text, rtl)
    order = visual_order(lv)
    out: List[Tuple[bool, List[int]]] = []
    for i in order:
        r = lv[i] % 2 == 1
        if out and out[-1][0] == r:
            out[-1][1].append(i)
        else:
            out.append((r, [i]))
    return [(r, "".join(text[i] for i in sorted(ix))) for r, ix in out]
