#!/usr/bin/env python3
"""TV broadcast-style cricket scoreboard overlay (1920x1080).

Professional TV look inspired by PTV Sports / Cric Axis broadcast graphics:
top score bar with team-color panels, info strip, ball-by-ball strip,
player cards, event banner, over a procedural night-stadium backdrop.

API:
    render_frame(state) -> PIL.Image  (1920x1080 RGB)

state keys:
    batting_team  "PAK" or "Pakistan" (code or full name)
    bowling_team  "IND" or "India"
    score         int/str, e.g. 86
    wickets       int/str, e.g. 2
    overs         str, e.g. "10.3"
    balls         list of recent ball tokens, e.g. ["1","0","4","W","wd","6"]
                  (optionally a list of (over_no, [tokens]) groups)
    batsmen       [{"name":..,"runs":..,"balls":..,"fours":..,"sixes":..}, ...]
    bowler        {"name":..,"overs":"2.3","maidens":0,"runs":18,"wkts":1}
    crr, rrr      str/float
    target_text   str, e.g. "PAK NEED 126 RUNS IN 57 BALLS"
    reviews       optional str, e.g. "PAK 2 | IND 2"
    event         optional flash text, e.g. "SIX!" (shown only when non-empty;
                  caller clears it by passing "" — auto-clear is the caller's job)

Preview:
    python3 scoreboard_tv.py   -> writes ~/workspace/cricket/tv-scoreboard-preview.png
"""

import math
import random

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080

TEAM_NAMES = {
    "PAK": "PAKISTAN", "IND": "INDIA", "AUS": "AUSTRALIA", "ENG": "ENGLAND",
    "NZ": "NEW ZEALAND", "SA": "SOUTH AFRICA", "RSA": "SOUTH AFRICA",
    "SL": "SRI LANKA", "BAN": "BANGLADESH", "AFG": "AFGHANISTAN",
    "WI": "WEST INDIES", "ZIM": "ZIMBABWE", "IRE": "IRELAND",
    "NED": "NETHERLANDS", "SCO": "SCOTLAND", "NAM": "NAMIBIA",
    "USA": "USA", "UAE": "UAE",
}

# team panel background + foreground text color
TEAM_COLORS = {
    "PAK": ((0, 128, 60), (255, 255, 255)),
    "IND": ((15, 80, 180), (255, 255, 255)),
    "AUS": ((235, 190, 20), (20, 20, 20)),
    "ENG": ((25, 45, 110), (255, 255, 255)),
    "NZ": ((25, 25, 32), (255, 255, 255)),
    "SA": ((0, 105, 70), (255, 255, 255)),
    "SL": ((10, 50, 140), (255, 255, 255)),
    "BAN": ((0, 120, 75), (255, 255, 255)),
    "AFG": ((10, 85, 165), (255, 255, 255)),
    "WI": ((125, 25, 45), (255, 255, 255)),
    "ZIM": ((200, 35, 35), (255, 255, 255)),
    "IRE": ((0, 135, 85), (255, 255, 255)),
    "NED": ((220, 110, 20), (255, 255, 255)),
}
DEFAULT_TEAM = ((35, 45, 78), (255, 255, 255))

GOLD = (255, 205, 70)
DARK = (14, 18, 32)
DARK2 = (24, 30, 50)
WHITE = (255, 255, 255)
MUTED = (175, 185, 200)
RED = (200, 25, 30)


def _font(name, size):
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}.ttf", size)


_FONTS = None


def F():
    global _FONTS
    if _FONTS is None:
        _FONTS = {
            "score": _font("DejaVuSans-Bold", 66),
            "team": _font("DejaVuSans-Bold", 36),
            "banner": _font("DejaVuSans-Bold", 110),
            "med": _font("DejaVuSans-Bold", 40),
            "med2": _font("DejaVuSans-Bold", 32),
            "sm": _font("DejaVuSans-Bold", 28),
            "sm_r": _font("DejaVuSans", 27),
            "tiny": _font("DejaVuSans-Bold", 24),
            "tiny_r": _font("DejaVuSans", 22),
            "ball": _font("DejaVuSans-Bold", 30),
            "card_big": _font("DejaVuSans-Bold", 46),
        }
    return _FONTS


def team_code(t):
    t = str(t or "").strip().upper()
    if t in TEAM_NAMES:
        return t
    for code, full in TEAM_NAMES.items():
        if full == t:
            return code
    return (t[:3] or "TBD")


def team_full(code):
    return TEAM_NAMES.get(code, code)


def team_colors(code):
    return TEAM_COLORS.get(code, DEFAULT_TEAM)


def _rr(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _fit_font(text, font_name, start_size, max_width):
    """Shrink a DejaVu font until text fits max_width."""
    size = start_size
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    while size > 10:
        f = _font(font_name, size)
        if probe.textlength(text, font=f) <= max_width:
            return f
        size -= 2
    return _font(font_name, 10)


# ---------------- stadium backdrop (procedural, cached) ----------------

_BACKDROP = None


def stadium_backdrop():
    global _BACKDROP
    if _BACKDROP is not None:
        return _BACKDROP.copy()
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    # night sky gradient
    for y in range(0, 430):
        k = y / 430
        d.line([(0, y), (W, y)],
               fill=(int(6 + 22 * k), int(10 + 34 * k), int(26 + 62 * k)))
    # floodlight towers + glow
    for x in (200, 700, 1220, 1720):
        d.rectangle([x - 6, 30, x + 6, 200], fill=(55, 62, 80))
        d.rectangle([x - 70, 18, x + 70, 60], fill=(70, 78, 100))
        for i in range(6):
            r = 150 - i * 22
            b = 60 + i * 30
            d.ellipse([x - r, 40 - r * 0.55, x + r, 40 + r * 0.55],
                      fill=(b, b + 12, min(255, b + 60)))
        d.rectangle([x - 62, 24, x + 62, 54], fill=(235, 242, 255))
    # stands band
    d.rectangle([0, 200, W, 440], fill=(22, 27, 46))
    rnd = random.Random(1234)
    palette = [(200, 60, 60), (60, 120, 200), (230, 200, 80), (90, 180, 90),
               (200, 200, 210), (150, 90, 180)]
    for _ in range(2600):
        x = rnd.randrange(0, W)
        y = rnd.randrange(208, 432)
        c = rnd.choice(palette)
        if rnd.random() < 0.05:
            c = (255, 255, 255)
        d.ellipse([x, y, x + 6, y + 6], fill=c)
    # LED ad boards
    y0, y1 = 440, 486
    seg_w = 240
    cols = [(16, 90, 200), (190, 30, 40)]
    for i, x in enumerate(range(0, W, seg_w)):
        d.rectangle([x, y0, min(x + seg_w, W), y1], fill=cols[i % 2])
    bd = ImageDraw.Draw(img)
    for i, x in enumerate(range(0, W, seg_w)):
        txt = "WORLD CRICKET" if i % 2 == 0 else "LIVE CRICKET"
        bf = _fit_font(txt, "DejaVuSans-Bold", 26, seg_w - 24)
        bd.text((x + seg_w / 2, (y0 + y1) / 2), txt, font=bf,
                anchor="mm", fill=(255, 255, 255))
    # field gradient + mowing stripes
    for y in range(486, H):
        k = (y - 486) / (H - 486)
        d.line([(0, y), (W, y)],
               fill=(int(36 + 14 * k), int(122 + 26 * k), int(58 + 16 * k)))
    # mowing stripes via alpha overlay
    stripe = Image.new("RGB", (W, H - 486), (52, 140, 70))
    m = Image.new("L", (W, H - 486), 0)
    md = ImageDraw.Draw(m)
    for i, x in enumerate(range(0, W, 340)):
        md.rectangle([x, 0, x + 170, H - 486], fill=70)
    img.paste(Image.composite(stripe,
                              img.crop((0, 486, W, H)), m), (0, 486))
    d = ImageDraw.Draw(img)
    # boundary rope
    d.ellipse([W / 2 - 760, 560, W / 2 + 760, 1150], outline=(240, 240, 240), width=6)
    _BACKDROP = img
    return img.copy()


# ---------------- pieces ----------------

def draw_flag(d, box, code):
    """Mini flag-inspired block for the team panel."""
    x0, y0, x1, y1 = box
    bg, _ = team_colors(code)
    if code == "PAK":
        d.rectangle(box, fill=(0, 128, 60))
        d.rectangle([x0, y0, x0 + (x1 - x0) // 4, y1], fill=(240, 240, 240))
    elif code == "IND":
        h = (y1 - y0) / 3
        d.rectangle([x0, y0, x1, y0 + h], fill=(255, 153, 51))
        d.rectangle([x0, y0 + h, x1, y0 + 2 * h], fill=(245, 245, 245))
        d.rectangle([x0, y0 + 2 * h, x1, y1], fill=(19, 136, 8))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], outline=(10, 40, 120), width=3)
    else:
        d.rectangle(box, fill=bg)
        f = _font("DejaVuSans-Bold", 34)
        d.text(((x0 + x1) / 2, (y0 + y1) / 2), code, font=f, anchor="mm", fill=(255, 255, 255))
    d.rectangle(box, outline=(255, 255, 255), width=2)


def draw_cricket_ball(d, cx, cy, r):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(185, 25, 30),
              outline=(120, 12, 16), width=3)
    # highlight + seam
    d.ellipse([cx - r * 0.55, cy - r * 0.62, cx - r * 0.05, cy - r * 0.12],
              fill=(235, 120, 125))
    d.arc([cx - r * 0.5, cy - r, cx + r * 0.5, cy + r], start=250, end=110,
          fill=(245, 235, 235), width=3)


def ball_style(tok):
    t = str(tok).strip()
    tl = t.lower()
    if t == "4":
        return (25, 150, 65), WHITE, "4"
    if t == "6":
        return (125, 65, 185), WHITE, "6"
    if t.upper() == "W":
        return RED, WHITE, "W"
    if tl in ("wd", "nb"):
        return (235, 195, 25), (30, 30, 30), tl
    if t == "0":
        return (95, 100, 112), WHITE, "0"
    if t in ("1", "2", "3"):
        return (240, 242, 246), (25, 28, 38), t
    return (70, 78, 98), WHITE, t[:2]


def group_balls(balls, overs):
    """-> list of (over_no, [tokens]). Accepts flat token list or pre-grouped."""
    if not balls:
        return []
    if isinstance(balls[0], (list, tuple)):
        return [(int(g[0]), list(g[1])) for g in balls]
    try:
        cur = int(float(str(overs))) + 1
    except Exception:
        cur = 0
    # TV "recent balls" = last 18 deliveries, grouped 6 per over from the
    # current (partial) over backwards; the oldest excess is dropped.
    toks = list(balls)[-18:]
    groups = []
    while toks:
        chunk = toks[-6:]
        toks = toks[:-6]
        groups.append((cur, chunk))
        cur -= 1
    groups.reverse()
    return groups


# ---------------- main render ----------------

# ---------------- main render (piece functions) ----------------

def _ctx(state):
    """Shared computed values for the piece-drawing functions."""
    bat = team_code(state.get("batting_team"))
    bowl = team_code(state.get("bowling_team"))
    bat_bg, bat_fg = team_colors(bat)
    bowl_bg, bowl_fg = team_colors(bowl)
    return {
        "bat": bat, "bowl": bowl,
        "bat_bg": bat_bg, "bat_fg": bat_fg,
        "bowl_bg": bowl_bg, "bowl_fg": bowl_fg,
        "score_txt": f"{state.get('score', 0)}-{state.get('wickets', 0)}",
        "overs": str(state.get("overs", "0")),
    }


def draw_top_bar(d, fonts, state, c=None):
    """Top score bar (y 0..118). Draws on RGB or RGBA."""
    c = c or _ctx(state)
    bat, bat_bg, bat_fg = c["bat"], c["bat_bg"], c["bat_fg"]
    bowl, bowl_bg, bowl_fg = c["bowl"], c["bowl_bg"], c["bowl_fg"]
    score_txt, overs = c["score_txt"], c["overs"]
    bar_h = 118
    # left: batting team (0..760)
    d.rectangle([0, 0, 760, bar_h], fill=bat_bg)
    draw_flag(d, [22, 20, 132, 98], bat)
    f_team = _fit_font(team_full(bat), "DejaVuSans-Bold", 32, 560)
    d.text((155, 22), team_full(bat), font=f_team, anchor="lm", fill=bat_fg)
    f_score = _fit_font(score_txt, "DejaVuSans-Bold", 60, 420)
    d.text((155, 74), score_txt, font=f_score, anchor="lm", fill=bat_fg)
    score_w = d.textlength(score_txt, font=f_score)
    d.text((155 + score_w + 18, 94), "(" + overs + ")",
           font=fonts["med2"], anchor="lm", fill=bat_fg)
    d.text((700, 100), "OVERS", font=fonts["tiny"], anchor="rm", fill=bat_fg)

    # center: ball indicator (760..1160)
    d.rectangle([760, 0, 1160, bar_h], fill=(12, 15, 28))
    d.rectangle([760, 0, 1160, bar_h], outline=(70, 78, 100), width=2)
    draw_cricket_ball(d, 850, bar_h / 2, 34)
    d.text((905, bar_h / 2 - 4), "BALL", font=fonts["med"], anchor="lm", fill=WHITE)
    d.text((905, bar_h / 2 + 34), f"OVER {overs}", font=fonts["tiny"],
           anchor="lm", fill=MUTED)

    # right: bowling team (1160..1920)
    d.rectangle([1160, 0, 1920, bar_h], fill=bowl_bg)
    draw_flag(d, [1788, 20, 1898, 98], bowl)
    f_team2 = _fit_font(team_full(bowl), "DejaVuSans-Bold", 32, 560)
    tw = d.textlength(team_full(bowl), font=f_team2)
    d.text((1765 - tw, 22), team_full(bowl), font=f_team2, anchor="lm", fill=bowl_fg)
    f_opp = _fit_font(str(state.get("opp_score", "")), "DejaVuSans-Bold", 40, 300)
    opp_score = state.get("opp_score", "")
    if opp_score:
        ot = d.textlength(opp_score, font=f_opp)
        d.text((1765 - ot, 74), opp_score, font=f_opp, anchor="lm", fill=bowl_fg)
    else:
        d.text((1765, 80), "FIELDING", font=fonts["med2"], anchor="rm", fill=bowl_fg)


def draw_info_strip(d, fonts, state, c=None):
    """Info strip (y 118..168)."""
    bar_h = 118
    sy0, sy1 = bar_h, bar_h + 50
    d.rectangle([0, sy0, W, sy1], fill=(10, 13, 26))
    d.line([(0, sy1), (W, sy1)], fill=(70, 78, 100), width=2)
    parts = []
    if state.get("crr") not in (None, ""):
        parts.append(f"CRR {state['crr']}")
    if state.get("rrr") not in (None, ""):
        parts.append(f"RRR {state['rrr']}")
    if state.get("target_text"):
        parts.append(str(state["target_text"]))
    if state.get("reviews"):
        parts.append(f"REVIEWS: {state['reviews']}")
    info = "   |   ".join(parts) if parts else "LIVE CRICKET"
    f_info = _fit_font(info, "DejaVuSans-Bold", 30, W - 60)
    d.text((W / 2, (sy0 + sy1) / 2), info, font=f_info, anchor="mm", fill=WHITE)


def draw_event_banner(d, fonts, state, c=None, y0=320, y1=470):
    """Center flash banner (SIX! / WICKET! ...). No-op when state['event'] empty."""
    c = c or _ctx(state)
    event = str(state.get("event") or "").strip()
    if not event:
        return
    if "WICKET" in event.upper():
        ebg = RED
    elif any(k in event.upper() for k in ("SIX", "FOUR", "50", "100")):
        ebg = c["bat_bg"]
    else:
        ebg = DARK2
    bw0, bw1, bh0, bh1 = 520, 1400, y0, y1
    # shadow + glow
    _rr(d, [bw0 + 10, bh0 + 12, bw1 + 10, bh1 + 12], 28, (0, 0, 0))
    _rr(d, [bw0 - 6, bh0 - 6, bw1 + 6, bh1 + 6], 32, GOLD)
    _rr(d, [bw0, bh0, bw1, bh1], 28, ebg, outline=WHITE, width=4)
    f_ev = _fit_font(event.upper(), "DejaVuSans-Bold", 110, (bw1 - bw0) - 80)
    d.text(((bw0 + bw1) / 2, (bh0 + bh1) / 2), event.upper(),
           font=f_ev, anchor="mm", fill=WHITE)


def draw_ball_strip(d, fonts, state, c=None, y=748):
    """Ball-by-ball strip. Caller may draw its own backing bar first."""
    c = c or _ctx(state)
    overs = c["overs"]
    strip_y = y
    d.text((60, strip_y), "RECENT BALLS", font=fonts["tiny"], anchor="lm", fill=GOLD)
    groups = group_balls(state.get("balls") or [], overs)[-3:]
    x = 60
    cy = strip_y + 52
    cr = 27
    for over_no, toks in groups:
        label = f"OV {over_no}"
        f_lab = fonts["tiny"]
        lw = d.textlength(label, font=f_lab)
        need = lw + 16 + len(toks) * (cr * 2 + 12) + 40
        if x + need > W - 40 and groups.index((over_no, toks)) != len(groups) - 1:
            continue  # drop older groups that don't fit
        d.text((x, cy), label, font=f_lab, anchor="lm", fill=MUTED)
        x += lw + 16
        for tok in toks:
            if x + cr * 2 > W - 40:
                break
            fill, fg, txt = ball_style(tok)
            d.ellipse([x, cy - cr, x + cr * 2, cy + cr], fill=fill,
                      outline=(255, 255, 255), width=2)
            d.text((x + cr, cy), txt, font=fonts["ball"], anchor="mm", fill=fg)
            x += cr * 2 + 12
        x += 40


def _avatar(d, dx, dy, color):
    r = 34
    d.ellipse([dx - r, dy - r, dx + r, dy + r], fill=color,
              outline=(255, 255, 255), width=3)
    # simple head/shoulders silhouette
    d.ellipse([dx - 13, dy - 20, dx + 13, dy + 2], fill=(235, 205, 175))
    d.arc([dx - 22, dy - 2, dx + 22, dy + 40], start=180, end=360,
          fill=(235, 205, 175), width=22)


def draw_player_cards(d, fonts, state, c=None, y0=868, body_fill=None):
    """Batsmen + bowler cards. body_fill may be an RGBA tuple for overlays."""
    c = c or _ctx(state)
    bat_bg, bowl_bg = c["bat_bg"], c["bowl_bg"]
    if body_fill is None:
        body_fill = DARK2
    cards_y0, cards_y1 = y0, y0 + 184
    card_w, gap = 580, 40
    total_w = 3 * card_w + 2 * gap
    cx = (W - total_w) / 2

    def player_card(x0, role, name, big, sub, header_bg):
        _rr(d, [x0, cards_y0, x0 + card_w, cards_y1], 20, body_fill,
            outline=(80, 90, 120), width=2)
        _rr(d, [x0, cards_y0, x0 + card_w, cards_y0 + 46], 20, header_bg)
        d.rectangle([x0, cards_y0 + 26, x0 + card_w, cards_y0 + 46], fill=header_bg)
        d.text((x0 + 24, cards_y0 + 23), role, font=fonts["sm"],
               anchor="lm", fill=WHITE)
        _avatar(d, x0 + 66, cards_y0 + 112, header_bg)
        f_nm = _fit_font(str(name).upper(), "DejaVuSans-Bold", 30, card_w - 170)
        d.text((x0 + 118, cards_y0 + 66), str(name).upper(), font=f_nm,
               anchor="lm", fill=WHITE)
        d.text((x0 + 118, cards_y0 + 112), big, font=fonts["card_big"],
               anchor="lm", fill=GOLD)
        d.text((x0 + 118, cards_y0 + 152), sub, font=fonts["tiny_r"],
               anchor="lm", fill=MUTED)

    batsmen = state.get("batsmen") or []
    for i in range(2):
        b = batsmen[i] if i < len(batsmen) else {}
        name = b.get("name", f"Batsman {i + 1}")
        runs = b.get("runs", 0)
        balls_faced = b.get("balls", 0)
        fours = b.get("fours", 0)
        sixes = b.get("sixes", 0)
        try:
            sr = float(runs) / float(balls_faced) * 100 if float(balls_faced) else 0
        except Exception:
            sr = 0
        role = "BATSMAN" + ("  ★" if b.get("striker") else "")
        player_card(cx + i * (card_w + gap), role, name,
                    f"{runs} ({balls_faced})",
                    f"4s: {fours}   6s: {sixes}   SR: {sr:.1f}", bat_bg)

    bw = state.get("bowler") or {}
    bname = bw.get("name", "Bowler")
    bovers = str(bw.get("overs", "0"))
    maid = bw.get("maidens", 0)
    bruns = bw.get("runs", 0)
    bwkts = bw.get("wkts", bw.get("wickets", 0))
    try:
        if "." in bovers:
            wh, bl = bovers.split(".")
            dec_ov = int(wh) + int(bl) / 6
        else:
            dec_ov = float(bovers)
        eco = float(bruns) / dec_ov if dec_ov else 0
    except Exception:
        eco = 0
    player_card(cx + 2 * (card_w + gap), "BOWLER", bname,
                f"{bovers}-{maid}-{bruns}-{bwkts}",
                f"Econ: {eco:.2f}", bowl_bg)


def render_frame(state):
    fonts = F()
    img = stadium_backdrop()
    d = ImageDraw.Draw(img)
    c = _ctx(state)

    # ===== 1. TOP SCORE BAR (y 0..118) =====
    draw_top_bar(d, fonts, state, c)
    # ===== 2. INFO STRIP (y 118..168) =====
    draw_info_strip(d, fonts, state, c)
    # ===== 5. EVENT BANNER (center flash) =====
    draw_event_banner(d, fonts, state, c)
    # ===== 3. BALL-BY-BALL STRIP (y ~748..848) =====
    draw_ball_strip(d, fonts, state, c)
    # ===== 4. PLAYER CARDS (y 868..1052) =====
    draw_player_cards(d, fonts, state, c)

    # slim bottom brand line
    d.rectangle([0, H - 14, W, H], fill=c["bat_bg"])
    return img


# ---------------- preview ----------------

def _sample_states():
    base_balls = ["1", "0", "4", "1", "wd", "2", "0", "1", "6", "0", "1", "4",
                  "W", "1", "0", "2", "1", "6"]
    base = {
        "batting_team": "PAK",
        "bowling_team": "IND",
        "score": 148, "wickets": 2, "overs": "14.3",
        "opp_score": "211-6 (20)",
        "balls": base_balls,
        "batsmen": [
            {"name": "Saim Ayub", "runs": 58, "balls": 34, "fours": 6, "sixes": 2,
             "striker": True},
            {"name": "Babar Azam", "runs": 44, "balls": 31, "fours": 5, "sixes": 0},
        ],
        "bowler": {"name": "Jasprit Bumrah", "overs": "2.3", "maidens": 0,
                   "runs": 26, "wkts": 1},
        "crr": "10.21", "rrr": "11.35",
        "target_text": "PAK NEED 64 RUNS IN 33 BALLS",
        "reviews": "PAK 2 | IND 2",
        "event": "",
    }
    six = dict(base)
    six["event"] = "SIX!"
    six["balls"] = base_balls + ["6"]
    six["score"] = 154
    wicket = dict(base)
    wicket["event"] = "WICKET!"
    wicket["balls"] = base_balls + ["W"]
    wicket["wickets"] = 3
    wicket["batsmen"] = [
        {"name": "Mohammad Rizwan", "runs": 0, "balls": 1, "fours": 0, "sixes": 0,
         "striker": True},
        {"name": "Babar Azam", "runs": 44, "balls": 31, "fours": 5, "sixes": 0},
    ]
    return [("Mid-innings", base), ("Six event", six), ("Wicket event", wicket)]


def main():
    frames = []
    for label, st in _sample_states():
        frames.append(render_frame(st))
        print("rendered:", label)
    stack = Image.new("RGB", (W, H * 3))
    for i, fr in enumerate(frames):
        stack.paste(fr, (0, i * H))
    out = "/home/hatch/workspace/cricket/tv-scoreboard-preview.png"
    stack.save(out)
    print("saved", out)


if __name__ == "__main__":
    main()
