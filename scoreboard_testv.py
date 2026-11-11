#!/usr/bin/env python3
"""Test-match TV scoreboard renderer (Adnan's screenshot design, 2026-11-11).

Layout modelled on the broadcast overlay Adnan sent:
- Top bar: batting-team panel (left), black last-ball box (center),
  other-team panel (right, with Day/Session line)
- Info row: CRR / RRR / P'SHIP (left), win-probability bar (center),
  match status text (right)
- Chip row: last wicket (left), match label / venue (right)
- Open stadium view in the middle
- Bottom: two batter cards + bowler card, recent-balls strip

API matches the other renderers:
    TestRenderer(F)        # F = anim_match.load_fonts()
    r.render(st, frame_no) # st = fetch_rich-style live state -> 1920x1080 RGB
    r.enrich(st, url)      # optional hook: adds team_scores, last-wicket
                           # text, match label and venue from the same page

No hardcoded teams: names/codes come from the live state via
anim_match.resolve_teams / title_team_codes; unknown pieces stay blank.
Player "photos" are drawn as initials badges (never fake faces).
"""

import re

import requests
from PIL import Image, ImageDraw, ImageFont

import anim_match
import scoreboard_v2

OUT_W, OUT_H = 1920, 1080
UA = scoreboard_v2.UA

WHITE = (245, 248, 255)
MUTED = (168, 180, 205)
GOLD = (255, 205, 50)
PANEL = (10, 16, 30)
PANEL2 = (16, 24, 44)
BLACK = (4, 5, 9)
CHIP_RED = (122, 18, 30)
CHIP_TEAL = (10, 74, 84)
BALL_4 = (30, 110, 220)
BALL_6 = (130, 60, 200)
BALL_W = (205, 32, 48)
BALL_X = (232, 164, 32)
BALL_N = (56, 64, 84)


def _font(bold, size):
    name = "DejaVuSans-Bold" if bold else "DejaVuSans"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}.ttf",
                              size)


def _fit(d, text, bold, size, max_w, min_size=18):
    """Largest font (<= size) that keeps text within max_w pixels."""
    s = size
    while s > min_size:
        f = _font(bold, s)
        if d.textlength(text, font=f) <= max_w:
            return f
        s -= 2
    return _font(bold, min_size)


def _rr(d, box, rad, **kw):
    d.rounded_rectangle(box, radius=rad, **kw)


def _initials(name):
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# --------------------------------------------------------------------------
# enrich: extra fields the base fetch_rich parse does not carry
# --------------------------------------------------------------------------

def enrich_state(st, url):
    """Add team_scores / last_wicket_text / last10_text / match_label / venue.

    Best-effort: any piece that cannot be parsed is simply left unset and
    the renderer hides the matching element.
    """
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    html = r.text
    i = html.find('id="miniscore-branding-container"')
    seg = html[i:i + 30000] if i != -1 else html

    # every innings score on the miniscore; keep the LAST hit per team code
    scores = {}
    for code0, runs, wkts, overs in scoreboard_v2._score_hits(seg):
        code = scoreboard_v2.canon_team_code(code0) or code0
        scores[code] = (runs, wkts, overs)
    if scores:
        st["team_scores"] = scores

    parts = scoreboard_v2._parts(seg)
    for key, label in (("last_wicket_text", "Last Wkt:"),
                       ("last10_text", "Last 10 overs")):
        try:
            j = parts.index(label)
            if j + 1 < len(parts):
                st[key] = parts[j + 1]
        except ValueError:
            pass

    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if m:
        t = m.group(1)
        g = re.search(r"vs\s+[A-Za-z ]+?,\s*([^,|]+),", t)
        if g:
            st["match_label"] = g.group(1).strip().upper()
        v = re.search(r"([A-Za-z][A-Za-z .]*?(?:Stadium|Ground|Oval|Arena))"
                      r"\s*,\s*[A-Za-z ]+", html)
        if v:
            st["venue"] = v.group(0).strip()


def _short_last_wicket(text):
    """'Kamindu Mendis c Ghazi Ghori b Abbas 58(131) - 155/4 in 41.6 ov'
    -> 'Kamindu Mendis 58 (131)'."""
    if not text:
        return ""
    m = re.match(r"(.+?)\s+(\d+)\((\d+)\)", text)
    if not m:
        return text.split(" - ")[0][:52]
    name = m.group(1)
    for verb in (" c ", " b ", " lbw ", " run out", " st ", " hit wicket",
                 " retired"):
        k = name.find(verb)
        if k != -1:
            name = name[:k]
    return f"{name.strip()} {m.group(2)} ({m.group(3)})"


# --------------------------------------------------------------------------
# background: drawn stadium (always match-neutral; bg_custom is ignored so
# a previous match's poster can never leak into a new match's stream)
# --------------------------------------------------------------------------

def _make_bg():
    W, H = OUT_W, OUT_H
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=(int(14 + 26 * k), int(52 + 74 * k),
                                      int(30 + 38 * k)))
    # mowing stripes
    for x in range(0, W, 320):
        d.rectangle([x, 120, x + 160, H], fill=(24, 108, 52))
    d = ImageDraw.Draw(img, "RGBA")
    # floodlight glows
    for gx in (180, 1740):
        for r in range(300, 0, -30):
            d.ellipse([gx - r, 60 - r // 2, gx + r, 60 + r // 2],
                      fill=(255, 250, 210, 5))
    # stands band
    d.rectangle([0, 318, W, 402], fill=(8, 14, 26, 120))
    d.rectangle([0, 402, W, 410], fill=(255, 255, 255, 26))
    # 30-yard circle + boundary
    cx, cy = W / 2, H * 0.66
    d.ellipse([cx - 640, cy - 300, cx + 640, cy + 300],
              outline=(255, 255, 255, 90), width=4)
    d.ellipse([cx - 900, cy - 430, cx + 900, cy + 430],
              outline=(245, 245, 245, 60), width=5)
    # pitch
    pw, ph = 150, 400
    d.rectangle([cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2],
                fill=(196, 168, 118, 200))
    d.rectangle([cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2],
                outline=(255, 255, 255, 90), width=3)
    # watermark
    f = _font(True, 110)
    txt = "CRICKET PULSE TV"
    tw = d.textlength(txt, font=f)
    d.text(((W - tw) / 2, 470), txt, font=f, fill=(255, 255, 255, 26))
    return img


class TestRenderer:
    """Screenshot-style Test/TV scoreboard over a drawn stadium."""

    def __init__(self, F):
        self.F = F
        self._bg = _make_bg()

    def enrich(self, st, url):
        enrich_state(st, url)

    # -- pieces -----------------------------------------------------------

    def _team_panel(self, d, box, code, name, score_txt, sub_txt,
                    align_right=False):
        x0, y0, x1, y1 = box
        _rr(d, box, 14, fill=PANEL, outline=(70, 84, 120), width=2)
        d.rectangle([x0, y1 - 8, x1, y1], fill=GOLD)
        col = anim_match.TEAM_COLORS.get(code, PANEL2)
        if not align_right:
            # badge
            d.ellipse([x0 + 22, y0 + 26, x0 + 118, y0 + 122], fill=col,
                      outline=WHITE, width=3)
            f_c = _fit(d, code or "?", True, 34, 84)
            d.text((x0 + 70, y0 + 74), code or "?", font=f_c, anchor="mm",
                   fill=WHITE)
            f_n = _fit(d, name or "", True, 40, x1 - x0 - 480)
            d.text((x0 + 140, y0 + 18), name or "", font=f_n, fill=WHITE)
            f_s = _font(True, 82)
            d.text((x1 - 26, y0 + 8), score_txt, font=f_s, anchor="ra",
                   fill=WHITE)
            if sub_txt:
                f_o = _font(False, 29)
                d.text((x1 - 26, y1 - 44), sub_txt, font=f_o, anchor="ra",
                       fill=MUTED)
        else:
            d.ellipse([x1 - 118, y0 + 26, x1 - 22, y0 + 122], fill=col,
                      outline=WHITE, width=3)
            f_c = _fit(d, code or "?", True, 34, 84)
            d.text((x1 - 70, y0 + 74), code or "?", font=f_c, anchor="mm",
                   fill=WHITE)
            f_n = _fit(d, name or "", True, 40, x1 - x0 - 480)
            nw = d.textlength(name or "", font=f_n)
            d.text((x1 - 140 - nw, y0 + 18), name or "", font=f_n, fill=WHITE)
            f_s = _font(True, 82)
            d.text((x0 + 26, y0 + 8), score_txt, font=f_s, fill=WHITE)
            if sub_txt:
                f_o = _fit(d, sub_txt, False, 29, x1 - x0 - 160)
                d.text((x0 + 26, y1 - 44), sub_txt, font=f_o, fill=GOLD)

    def _player_card(self, d, box, header, header_col, name, main_txt,
                     sub_txt, badge_col, star=False):
        x0, y0, x1, y1 = box
        _rr(d, box, 14, fill=PANEL, outline=(70, 84, 120), width=2)
        _rr(d, [x0, y0, x1, y0 + 46], 14, fill=header_col)
        d.rectangle([x0, y0 + 30, x1, y0 + 46], fill=header_col)
        f_h = _font(True, 27)
        d.text((x0 + 22, y0 + 8), header, font=f_h, fill=WHITE)
        # initials badge (photo slot)
        cy = (y0 + 46 + y1) / 2 + 6
        d.ellipse([x0 + 22, cy - 58, x0 + 138, cy + 58], fill=badge_col,
                  outline=WHITE, width=3)
        f_i = _font(True, 42)
        d.text((x0 + 80, cy), _initials(name), font=f_i, anchor="mm",
               fill=WHITE)
        tx = x0 + 158
        f_n = _fit(d, name or "", True, 40, x1 - tx - 14)
        d.text((tx, y0 + 58), (name or "") + (" *" if star else ""),
               font=f_n, fill=GOLD if star else WHITE)
        f_m = _fit(d, main_txt, True, 56, x1 - tx - 14)
        d.text((tx, y0 + 108), main_txt, font=f_m, fill=WHITE)
        if sub_txt:
            f_s = _font(False, 27)
            d.text((tx, y1 - 40), sub_txt, font=f_s, fill=MUTED)

    # -- main render ------------------------------------------------------

    def render(self, st, frame_no):
        img = self._bg.copy().convert("RGBA")
        ov = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)

        bat_code, bowl_code = anim_match.resolve_teams(st)
        names = anim_match.TEAM_NAMES
        bat_name = names.get(bat_code, bat_code or "")
        bowl_name = names.get(bowl_code, bowl_code or "")
        scores = st.get("team_scores") or {}

        status = (st.get("status") or "").strip()
        day_line, detail = "", status
        if " - " in status:
            day_line, detail = (p.strip() for p in status.split(" - ", 1))

        # ---- top bar ----
        bat_score = ""
        if st.get("runs") not in ("", None):
            bat_score = f"{st.get('runs')}/{st.get('wkts')}"
        bat_sub = f"{st.get('overs')} OVERS" if st.get("overs") else ""
        self._team_panel(d, (24, 24, 700, 176), bat_code, bat_name.upper(),
                         bat_score, bat_sub)
        opp = scores.get(bowl_code)
        opp_score = f"{opp[0]}/{opp[1]}" if opp else "—"
        self._team_panel(d, (1220, 24, 1896, 176), bowl_code,
                         bowl_name.upper(), opp_score, day_line.upper(),
                         align_right=True)

        # center black box: last ball
        flat = []
        for _, toks in (st.get("recent_overs") or []):
            flat.extend(str(t) for t in toks)
        last = flat[-1] if flat else ""
        _rr(d, (724, 24, 1196, 176), 14, fill=BLACK,
            outline=(90, 98, 124), width=2)
        if last:
            col = {"4": BALL_4, "6": BALL_6, "W": BALL_W}.get(
                last.strip().upper(), WHITE)
            f_b = _font(True, 104)
            d.text((960, 92), last, font=f_b, anchor="mm", fill=col)
            f_l = _font(False, 21)
            d.text((960, 158), "LAST BALL", font=f_l, anchor="mm",
                   fill=MUTED)
        else:
            f_b = _font(True, 64)
            d.text((960, 100), "LIVE", font=f_b, anchor="mm", fill=BALL_W)

        # ---- info row ----
        iy0, iy1 = 190, 248
        _rr(d, (24, iy0, 700, iy1), 10, fill=PANEL2)
        cells = []
        if st.get("crr"):
            cells.append(("CRR", st["crr"]))
        cells.append(("RRR", st.get("rrr") or "--"))
        if st.get("pship_runs"):
            cells.append(("P'SHIP",
                          f"{st['pship_runs']} ({st.get('pship_balls', '')})"))
        cx = 44
        for lab, val in cells:
            f_l = _font(False, 25)
            d.text((cx, iy0 + 15), lab + ":", font=f_l, fill=MUTED)
            cx += d.textlength(lab + ":", font=f_l) + 10
            f_v = _font(True, 32)
            d.text((cx, iy0 + 10), val, font=f_v, fill=WHITE)
            cx += d.textlength(val, font=f_v) + 34

        # win probability bar (center)
        wa, wb = st.get("win_a"), st.get("win_b")
        pa = int(st.get("win_a_pct") or 0)
        pb = int(st.get("win_b_pct") or 0)
        if wa and wb and (pa or pb):
            bx0, bx1 = 724, 1196
            draw_pct = max(0, 100 - pa - pb)
            segs = [(wa, pa, anim_match.TEAM_COLORS.get(wa, PANEL)),
                    ("DRAW", draw_pct, (96, 104, 128)),
                    (wb, pb, anim_match.TEAM_COLORS.get(wb, PANEL))]
            x = bx0
            for j, (code, pct, colr) in enumerate(segs):
                w = int((bx1 - bx0) * pct / 100)
                if j == len(segs) - 1:
                    w = bx1 - x
                if w > 0:
                    d.rectangle([x, iy0, x + w, iy1], fill=colr)
                if pct and w > 84:
                    f_p = _fit(d, f"{code} {pct}%", True, 27, w - 10)
                    d.text((x + w / 2, (iy0 + iy1) / 2), f"{code} {pct}%",
                           font=f_p, anchor="mm", fill=WHITE)
                x += w
            d.rectangle([bx0, iy0, bx1, iy1], outline=(70, 84, 120), width=2)
        # status detail (right)
        _rr(d, (1220, iy0, 1896, iy1), 10, fill=PANEL2)
        if detail:
            f_d = _fit(d, detail.upper(), True, 31, 640)
            tw = d.textlength(detail.upper(), font=f_d)
            d.text((1896 - 20 - tw, iy0 + 12), detail.upper(), font=f_d,
                   fill=GOLD)

        # ---- chip row ----
        lw = _short_last_wicket(st.get("last_wicket_text", ""))
        if lw:
            txt = f"LAST WICKET: {lw}"
            f_c = _fit(d, txt, True, 25, 900)
            w = d.textlength(txt, font=f_c) + 36
            _rr(d, (24, 260, 24 + w, 302), 8, fill=CHIP_RED)
            d.text((42, 268), txt, font=f_c, fill=WHITE)
        right_bits = [b for b in (st.get("match_label", ""),
                                  st.get("venue", "")) if b]
        if right_bits:
            txt = "  •  ".join(right_bits).upper()
            f_c = _fit(d, txt, True, 25, 900)
            w = d.textlength(txt, font=f_c) + 36
            _rr(d, (1896 - w, 260, 1896, 302), 8, fill=CHIP_TEAL)
            d.text((1896 - w + 18, 268), txt, font=f_c, fill=WHITE)

        # ---- player cards ----
        bat_col = anim_match.TEAM_COLORS.get(bat_code, PANEL2)
        bowl_col = anim_match.TEAM_COLORS.get(bowl_code, PANEL2)
        batters = st.get("batters") or []
        for k in range(2):
            b = batters[k] if k < len(batters) else {}
            name = b.get("name", "")
            main = (f"{b.get('r', '')} ({b.get('b', '')})" if name else "")
            sub = (f"4s: {b.get('fours', 0)}   6s: {b.get('sixes', 0)}"
                   f"   SR: {b.get('sr', '')}" if name else "")
            self._player_card(d, (24 + k * 628, 800, 652 + k * 628, 1006),
                              "BATTER", (146, 108, 10), name, main, sub,
                              bat_col, star=bool(b.get("striker")))
        bowlers = st.get("bowlers") or []
        bw = next((x for x in bowlers if x.get("cur")),
                  bowlers[0] if bowlers else {})
        bname = bw.get("name", "")
        bmain = f"{bw.get('w', '')}/{bw.get('r', '')}" if bname else ""
        bsub = (f"OVERS: {bw.get('o', '')}   ECON: {bw.get('eco', '')}"
                if bname else "")
        self._player_card(d, (1280, 800, 1896, 1006), "BOWLER",
                          (30, 90, 160), bname, bmain, bsub, bowl_col)

        # ---- recent strip ----
        ry0 = 1022
        _rr(d, (24, ry0, 150, 1072), 8, fill=(200, 30, 90))
        f_r = _font(True, 24)
        d.text((87, ry0 + 25), "RECENT", font=f_r, anchor="mm", fill=WHITE)
        x = 170
        f_o = _font(True, 24)
        for over_no, toks in (st.get("recent_overs") or []):
            lab = f"OVER {over_no}:"
            d.text((x, ry0 + 13), lab, font=f_o, fill=MUTED)
            x += d.textlength(lab, font=f_o) + 12
            for tok in toks:
                t = str(tok)
                tu = t.strip().upper()
                colr = BALL_N
                if tu == "W":
                    colr = BALL_W
                elif tu == "4":
                    colr = BALL_4
                elif tu == "6":
                    colr = BALL_6
                elif tu in ("WD", "NB"):
                    colr = BALL_X
                d.ellipse([x, ry0 + 5, x + 40, ry0 + 45], fill=colr)
                f_t = _fit(d, t, True, 22, 34)
                d.text((x + 20, ry0 + 25), t, font=f_t, anchor="mm",
                       fill=WHITE)
                x += 50
            x += 22
            if x > 1860:
                break

        return Image.alpha_composite(img, ov).convert("RGB")


def _demo():
    from scoreboard_v2 import fetch_rich
    url = ("https://www.cricbuzz.com/live-cricket-scores/170703/"
           "pak-vs-sl-1st-test-sri-lanka-tour-of-pakistan-2026")
    st = fetch_rich(url)
    try:
        enrich_state(st, url)
    except Exception as e:
        print("enrich failed:", e)
    r = TestRenderer(anim_match.load_fonts())
    img = r.render(st, 0)
    out = "/tmp/testv_preview.png"
    img.save(out)
    print("saved", out, "| state:", st.get("team"), st.get("runs"),
          st.get("wkts"), st.get("overs"), "| scores:", st.get("team_scores"),
          "| lw:", st.get("last_wicket_text"), "| label:",
          st.get("match_label"), "| venue:", st.get("venue"))


if __name__ == "__main__":
    _demo()
