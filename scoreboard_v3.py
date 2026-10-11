#!/usr/bin/env python3
"""Cricket Point-style TV cricket scoreboard (1920x1080).

Broadcast look modelled on the Cricket Point reference graphic:
top team panels with a CENTER event banner (FOUR!/SIX!/WICKET!),
blue info strip (CRR | RRR | partnership | equation), ball-by-ball strip
with coloured ball circles, over totals, last-wicket / win-probability /
next-batsman blocks, and bottom player cards with initial-avatars over a
green cricket-ground backdrop watermarked "CRICKET PULSE".

API:
    render_frame(state) -> PIL.Image  (1920x1080 RGB)

state keys (superset of scoreboard_tv.py):
    batting_team  "PAK" / "SL" (code or full name)
    bowling_team  "SL" / "PAK"
    score, wickets, overs
    innings_target  int, e.g. 180 (target being chased; None in 1st innings)
    balls         flat token list or [(over_no, [tokens]), ...]
    batsmen       [{"name","runs","balls","fours","sixes","striker"?}, ...]
    bowler        {"name","overs","maidens","runs","wkts"}
    crr, rrr      str/float
    target_text   str, e.g. "PAK NEED 35 RUNS IN 28 BALLS"
    partnership   {"runs":..,"balls":..}
    last_wicket   {"name":..,"runs":..}
    next_batsman  str
    event         optional flash text, e.g. "FOUR!" (caller clears with "")

Preview:
    python3 scoreboard_v3.py -> ~/workspace/cricket/scoreboard-v3-preview.png
"""

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080

TEAM_NAMES = {
    "PAK": "PAKISTAN", "IND": "INDIA", "AUS": "AUSTRALIA", "ENG": "ENGLAND",
    "NZ": "NEW ZEALAND", "SA": "SOUTH AFRICA", "RSA": "SOUTH AFRICA",
    "SL": "SRI LANKA", "BAN": "BANGLADESH", "AFG": "AFGHANISTAN",
    "WI": "WEST INDIES", "ZIM": "ZIMBABWE", "IRE": "IRELAND",
}

TEAM_COLORS = {
    "PAK": ((0, 128, 60), (255, 255, 255)),
    "SL": ((10, 50, 140), (255, 255, 255)),
    "IND": ((15, 80, 180), (255, 255, 255)),
    "AUS": ((235, 190, 20), (20, 20, 20)),
    "ENG": ((25, 45, 110), (255, 255, 255)),
}
DEFAULT_TEAM = ((35, 45, 78), (255, 255, 255))

GOLD = (255, 205, 70)
DARK = (10, 12, 24)
WHITE = (255, 255, 255)
MUTED = (170, 180, 195)
RED = (205, 25, 35)
PINK = (200, 40, 110)


def _font(name, size):
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}.ttf", size)


_FONTS = None


def F():
    global _FONTS
    if _FONTS is None:
        _FONTS = {
            "code": _font("DejaVuSans-Bold", 46),
            "score": _font("DejaVuSans-Bold", 78),
            "overs": _font("DejaVuSans-Bold", 34),
            "banner": _font("DejaVuSans-Bold", 96),
            "strip": _font("DejaVuSans-Bold", 34),
            "med": _font("DejaVuSans-Bold", 40),
            "sm": _font("DejaVuSans-Bold", 30),
            "tiny": _font("DejaVuSans-Bold", 26),
            "tiny_r": _font("DejaVuSans", 25),
            "ball": _font("DejaVuSans-Bold", 30),
            "card_big": _font("DejaVuSans-Bold", 44),
            "avatar": _font("DejaVuSans-Bold", 44),
            "wm": _font("DejaVuSans-Bold", 150),
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
    size = start_size
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    while size > 10:
        f = _font(font_name, size)
        if probe.textlength(text, font=f) <= max_width:
            return f
        size -= 2
    return _font(font_name, 10)


# ---------------- backdrop ----------------

_BACKDROP = None


def ground_backdrop():
    """Green cricket ground with big CRICKET PULSE watermark."""
    global _BACKDROP
    if _BACKDROP is not None:
        return _BACKDROP.copy()
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    # day-sky gradient top
    for y in range(0, 300):
        k = y / 300
        d.line([(0, y), (W, y)],
               fill=(int(70 + 60 * k), int(150 + 60 * k), int(200 + 40 * k)))
    # green outfield gradient
    for y in range(300, H):
        k = (y - 300) / (H - 300)
        d.line([(0, y), (W, y)],
               fill=(int(46 + 20 * k), int(140 + 30 * k), int(66 + 18 * k)))
    # mowing stripes
    stripe = Image.new("RGB", (W, H - 300), (62, 158, 78))
    m = Image.new("L", (W, H - 300), 0)
    md = ImageDraw.Draw(m)
    for x in range(0, W, 360):
        md.rectangle([x, 0, x + 180, H - 300], fill=60)
    img.paste(Image.composite(stripe, img.crop((0, 300, W, H)), m), (0, 300))
    d = ImageDraw.Draw(img)
    # watermark
    wm_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wm_layer)
    f_wm = F()["wm"]
    txt = "CRICKET PULSE"
    tw = wd.textlength(txt, font=f_wm)
    wd.text(((W - tw) / 2, 560), txt, font=f_wm, fill=(255, 255, 255, 46))
    # ball logo under watermark text
    cx, cy, r = W / 2, 700, 46
    wd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(185, 25, 30, 60),
               outline=(255, 255, 255, 70), width=3)
    img = Image.alpha_composite(img.convert("RGBA"), wm_layer).convert("RGB")
    d = ImageDraw.Draw(img)
    # boundary rope
    d.ellipse([W / 2 - 720, 420, W / 2 + 720, 1120],
              outline=(245, 245, 245), width=5)
    _BACKDROP = img
    return img.copy()


# ---------------- pieces ----------------

def draw_flag(d, box, code):
    x0, y0, x1, y1 = box
    if code == "PAK":
        d.rectangle(box, fill=(0, 128, 60))
        d.rectangle([x0, y0, x0 + (x1 - x0) // 4, y1], fill=(240, 240, 240))
        cx = x0 + (x1 - x0) * 0.62
        cy = (y0 + y1) / 2
        d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=(255, 255, 255), width=4)
    elif code == "SL":
        d.rectangle(box, fill=(10, 50, 140))
        d.rectangle(box, outline=(255, 205, 70), width=4)
        d.ellipse([x0 + 18, y0 + 18, x1 - 18, y1 - 18],
                  outline=(255, 205, 70), width=5)
    else:
        bg, _ = team_colors(code)
        d.rectangle(box, fill=bg)
        f = _font("DejaVuSans-Bold", 34)
        d.text(((x0 + x1) / 2, (y0 + y1) / 2), code, font=f,
               anchor="mm", fill=WHITE)
    d.rectangle(box, outline=WHITE, width=2)


def ball_style(tok):
    t = str(tok).strip()
    tl = t.lower()
    if t == "4":
        return (22, 150, 66), WHITE, "4"
    if t == "6":
        return (128, 64, 190), WHITE, "6"
    if t.upper() == "W":
        return RED, WHITE, "W"
    if tl in ("wd", "nb"):
        return (235, 195, 25), (30, 30, 30), tl
    if t == "0":
        return (105, 110, 122), WHITE, "0"
    if t in ("1", "2", "3"):
        return (238, 240, 245), (25, 28, 38), t
    return (70, 78, 98), WHITE, t[:2]


def group_balls(balls, overs):
    if not balls:
        return []
    if isinstance(balls[0], (list, tuple)):
        return [(int(g[0]), list(g[1])) for g in balls]
    try:
        cur = int(float(str(overs))) + 1
    except Exception:
        cur = 0
    toks = list(balls)[-18:]
    groups = []
    while toks:
        chunk = toks[-6:]
        toks = toks[:-6]
        groups.append((cur, chunk))
        cur -= 1
    groups.reverse()
    return groups


def over_runs(toks):
    total = 0
    for t in toks:
        tl = str(t).strip().lower()
        if tl == "w":
            continue
        if tl in ("wd", "nb"):
            total += 1
            continue
        try:
            total += int(tl)
        except Exception:
            pass
    return total


def win_probability(state):
    """Simple heuristic -> (batting_pct, bowling_pct), clamped 5..95."""
    bat = team_code(state.get("batting_team"))
    target = state.get("innings_target")
    try:
        rrr = float(state.get("rrr") or 0)
        crr = float(state.get("crr") or 0)
    except Exception:
        rrr = crr = 0
    if target:  # chasing
        p = 50 + (9.0 - rrr) * 8
    else:       # first innings
        p = 50 + (crr - 8.0) * 6
    p = max(5, min(95, round(p)))
    return p, 100 - p


def initials(name):
    parts = str(name).split()
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# ---------------- top bar ----------------

def draw_top_bar(d, fonts, state):
    bat = team_code(state.get("batting_team"))
    bowl = team_code(state.get("bowling_team"))
    bat_bg, bat_fg = team_colors(bat)
    bowl_bg, bowl_fg = team_colors(bowl)
    score_txt = f"{state.get('score', 0)}/{state.get('wickets', 0)}"
    overs = str(state.get("overs", "0"))
    bar_h = 150

    # LEFT: batting team panel (0..600)
    d.rectangle([0, 0, 600, bar_h], fill=bat_bg)
    draw_flag(d, [18, 28, 118, 122], bat)
    f_code = _fit_font(bat, "DejaVuSans-Bold", 46, 180)
    d.text((140, 34), bat, font=f_code, anchor="lm", fill=bat_fg)
    f_score = _fit_font(score_txt, "DejaVuSans-Bold", 78, 430)
    sw = d.textlength(score_txt, font=f_score)
    d.text((140, 96), score_txt, font=f_score, anchor="lm", fill=bat_fg)
    d.text((140 + sw + 16, 128), f"({overs})", font=fonts["overs"],
           anchor="lm", fill=bat_fg)

    # CENTER: event banner (600..1320)
    d.rectangle([600, 0, 1320, bar_h], fill=DARK)
    d.rectangle([600, 0, 1320, bar_h], outline=(70, 78, 100), width=2)
    event = str(state.get("event") or "").strip().upper()
    if event:
        if "WICKET" in event:
            ebg, efg = RED, WHITE
        else:
            ebg, efg = DARK, GOLD
        _rr(d, [640, 22, 1280, 128], 22, ebg, outline=GOLD, width=3)
        f_ev = _fit_font(event, "DejaVuSans-Bold", 92, 560)
        d.text((960, 75), event, font=f_ev, anchor="mm", fill=efg)
    else:
        f_ev = _fit_font("PAKISTAN vs SRI LANKA", "DejaVuSans-Bold", 44, 660)
        d.text((960, 62), "PAKISTAN vs SRI LANKA", font=f_ev,
               anchor="mm", fill=GOLD)
        d.text((960, 112), "2nd T20I  •  LIVE", font=fonts["tiny"],
               anchor="mm", fill=MUTED)

    # RIGHT: bowling team panel (1320..1920)
    d.rectangle([1320, 0, 1920, bar_h], fill=bowl_bg)
    f_name = _fit_font(team_full(bowl), "DejaVuSans-Bold", 40, 380)
    tw = d.textlength(team_full(bowl), font=f_name)
    d.text((1902 - 118 - 16 - tw, 26), team_full(bowl), font=f_name,
           anchor="lm", fill=bowl_fg)
    opp = str(state.get("opp_score") or "")
    if state.get("innings_target"):
        line1 = f"{opp}" if opp else ""
        line2 = f"TARGET: {state['innings_target']}"
    else:
        line1, line2 = opp, "BOWLING"
    f_s = _fit_font(line1, "DejaVuSans-Bold", 56, 420)
    w1 = d.textlength(line1, font=f_s)
    d.text((1902 - 118 - 16 - w1, 92), line1, font=f_s, anchor="lm", fill=bowl_fg)
    f_t = _fit_font(line2, "DejaVuSans-Bold", 34, 420)
    w2 = d.textlength(line2, font=f_t)
    d.text((1902 - 118 - 16 - w2, 132), line2, font=f_t, anchor="lm", fill=GOLD)
    draw_flag(d, [1802, 28, 1902, 122], bowl)


# ---------------- info strip ----------------

def draw_info_strip(d, fonts, state):
    y0, y1 = 150, 210
    d.rectangle([0, y0, W, y1], fill=(12, 42, 125))
    d.line([(0, y1), (W, y1)], fill=GOLD, width=3)
    parts = []
    if state.get("crr") not in (None, ""):
        parts.append(f"CRR: {state['crr']}")
    if state.get("rrr") not in (None, ""):
        parts.append(f"RRR: {state['rrr']}")
    p = state.get("partnership") or {}
    if p.get("runs") is not None:
        parts.append(f"P'SHIP: {p.get('runs')} ({p.get('balls', 0)})")
    if state.get("target_text"):
        parts.append(str(state["target_text"]).upper())
    info = "    |    ".join(parts) if parts else "LIVE CRICKET"
    f_info = _fit_font(info, "DejaVuSans-Bold", 33, W - 60)
    d.text((W / 2, (y0 + y1) / 2), info, font=f_info, anchor="mm", fill=WHITE)


# ---------------- ball strip ----------------

def draw_ball_strip(d, fonts, state):
    y0, y1 = 210, 305
    d.rectangle([0, y0, W, y1], fill=DARK)
    d.line([(0, y1), (W, y1)], fill=(70, 78, 100), width=2)
    bat = team_code(state.get("batting_team"))
    bowl = team_code(state.get("bowling_team"))
    cy = (y0 + y1) / 2

    # RECENT label
    _rr(d, [14, y0 + 14, 150, y1 - 14], 12, PINK)
    d.text((82, cy), "RECENT", font=fonts["tiny"], anchor="mm", fill=WHITE)

    # ---- right-side blocks first (measure, then draw right-aligned) ----
    items = []  # (kind, text, font, width, bg, fg)
    lw_ = state.get("last_wicket") or {}
    if lw_.get("name"):
        t = f"Last Wkt: {lw_['name']} {lw_.get('runs', 0)}"
        f = _fit_font(t, "DejaVuSans-Bold", 28, 380)
        items.append(("badge", t, f, d.textlength(t, font=f) + 36, RED, WHITE))
    p_bat, p_bowl = win_probability(state)
    for code, p, col in ((bowl, p_bowl, WHITE), (bat, p_bat, GOLD)):
        t = f"{code} {p}%"
        f = _fit_font(t, "DejaVuSans-Bold", 30, 220)
        items.append(("text", t, f, d.textlength(t, font=f), None, col))
    nb = str(state.get("next_batsman") or "")
    if nb:
        t = f"Next: {nb}"
        f = _fit_font(t, "DejaVuSans-Bold", 28, 340)
        items.append(("text", t, f, d.textlength(t, font=f), None, MUTED))
    rx = W - 20
    for kind, t, f, w, bg, fg in items:
        if kind == "badge":
            _rr(d, [rx - w, y0 + 14, rx, y1 - 14], 12, bg)
            d.text((rx - w + 18, cy), t, font=f, anchor="lm", fill=fg)
        else:
            d.text((rx - w, cy), t, font=f, anchor="lm", fill=fg)
        rx -= w + 28
    balls_right_edge = rx

    # ---- over groups: two most recent, chronological, fit before right edge ----
    groups = group_balls(state.get("balls") or [], str(state.get("overs", "0")))
    groups = sorted(groups, key=lambda g: g[0])[-2:]
    x = 175
    cr = 26
    for over_no, toks in groups:
        lab = f"OVER {over_no}:"
        lw = d.textlength(lab, font=fonts["tiny"])
        tot = over_runs(toks)
        tot_txt = f"= {tot}"
        tot_w = d.textlength(tot_txt, font=fonts["med"])
        need = lw + 14 + len(toks) * (cr * 2 + 10) + 16 + tot_w + 60
        if x + need > balls_right_edge:
            continue  # not enough room; keep the most recent that fits
        d.text((x, cy), lab, font=fonts["tiny"], anchor="lm", fill=MUTED)
        x += lw + 14
        for tok in toks:
            fill, fg, txt = ball_style(tok)
            d.ellipse([x, cy - cr, x + cr * 2, cy + cr], fill=fill,
                      outline=WHITE, width=2)
            d.text((x + cr, cy), txt, font=fonts["ball"], anchor="mm", fill=fg)
            x += cr * 2 + 10
        d.text((x + 16, cy), tot_txt, font=fonts["med"], anchor="lm", fill=GOLD)
        x += 16 + tot_w + 60


# ---------------- player cards ----------------

# Avatar images for player cards (cartoon-style, generated). Falls back to
# initials circles when files are absent (e.g. on the GitHub runner without
# the avatars/ directory).
_AVATAR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatars")
_AVATAR_CACHE = {}


def _avatar_img(team, role):
    key = (team, role)
    if key in _AVATAR_CACHE:
        return _AVATAR_CACHE[key]
    fname = {
        ("PAK", "bat"): "pak_batsman.webp",
        ("PAK", "bowl"): "pak_bowler.webp",
        ("SL", "bat"): "sl_batsman.webp",
        ("SL", "bowl"): "sl_bowler.webp",
    }.get(key)
    img = None
    if fname:
        p = os.path.join(_AVATAR_DIR, fname)
        if os.path.exists(p):
            try:
                img = Image.open(p).convert("RGB")
            except Exception:
                img = None
    _AVATAR_CACHE[key] = img
    return img


def _paste_avatar(base, ax, ay, ar, team, role, header_bg):
    """Paste circular-cropped avatar image; fallback to initials circle."""
    img = _avatar_img(team, role)
    if img is None:
        return None
    s = min(img.size)
    img = img.crop(((img.size[0] - s) // 2, (img.size[1] - s) // 2,
                   (img.size[0] + s) // 2, (img.size[1] + s) // 2))
    img = img.resize((ar * 2, ar * 2), Image.LANCZOS)
    mask = Image.new("L", (ar * 2, ar * 2), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, ar * 2, ar * 2], fill=255)
    base.paste(img, (ax - ar, ay - ar), mask)
    return True


def draw_player_cards(d, fonts, state, base_img=None):
    bat = team_code(state.get("batting_team"))
    bowl = team_code(state.get("bowling_team"))
    bat_bg, _ = team_colors(bat)
    bowl_bg, _ = team_colors(bowl)

    y0, y1 = 800, 1010
    card_w, gap = 560, 45
    total = 3 * card_w + 2 * gap
    x0 = (W - total) / 2

    def card(cx0, role, header_bg, name, big, sub, accent_on=False,
             team="PAK", avatar_role="bat"):
        _rr(d, [cx0, y0, cx0 + card_w, y1], 20, (13, 17, 32),
            outline=(85, 95, 125), width=2)
        _rr(d, [cx0, y0, cx0 + card_w, y0 + 52], 20, header_bg)
        d.rectangle([cx0, y0 + 32, cx0 + card_w, y0 + 52], fill=header_bg)
        d.text((cx0 + 26, y0 + 26), role, font=fonts["sm"], anchor="lm", fill=WHITE)
        # avatar: player picture in circle, fallback to initials
        ax, ay, ar = cx0 + 74, y0 + 128, 42
        drew = False
        if base_img is not None:
            drew = bool(_paste_avatar(base_img, int(ax), int(ay), ar,
                                      team, avatar_role, header_bg))
        if not drew:
            d.ellipse([ax - ar, ay - ar, ax + ar, ay + ar], fill=header_bg,
                      outline=WHITE, width=3)
            f_av = _fit_font(initials(name), "DejaVuSans-Bold", 44, ar * 2 - 14)
            d.text((ax, ay), initials(name), font=f_av, anchor="mm", fill=WHITE)
        else:
            d.ellipse([ax - ar, ay - ar, ax + ar, ay + ar],
                      outline=WHITE, width=3)
        f_nm = _fit_font(str(name).upper(), "DejaVuSans-Bold", 32, card_w - 200)
        d.text((cx0 + 132, y0 + 78), str(name).upper(), font=f_nm,
               anchor="lm", fill=WHITE)
        d.text((cx0 + 132, y0 + 128), big, font=fonts["card_big"],
               anchor="lm", fill=GOLD)
        d.text((cx0 + 132, y0 + 172), sub, font=fonts["tiny_r"],
               anchor="lm", fill=MUTED)
        if accent_on:
            d.ellipse([cx0 + card_w - 40, y0 + 70, cx0 + card_w - 16, y0 + 94],
                      fill=RED)
            d.ellipse([cx0 + card_w - 34, y0 + 76, cx0 + card_w - 22, y0 + 88],
                      fill=WHITE)

    batsmen = state.get("batsmen") or []
    for i in range(2):
        b = batsmen[i] if i < len(batsmen) else {}
        name = b.get("name", f"Batsman {i + 1}")
        runs, bf = b.get("runs", 0), b.get("balls", 0)
        try:
            sr = float(runs) / float(bf) * 100 if float(bf) else 0
        except Exception:
            sr = 0
        role = "BATTER" + ("  ★" if b.get("striker") else "")
        card(x0 + i * (card_w + gap), role, bat_bg, name,
             f"{runs} ({bf})",
             f"4s: {b.get('fours', 0)}   6s: {b.get('sixes', 0)}   SR: {sr:.1f}",
             accent_on=bool(b.get("striker")),
             team=bat, avatar_role="bat")

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
    card(x0 + 2 * (card_w + gap), "BOWLER", bowl_bg, bname,
         f"{bovers}-{maid}-{bruns}-{bwkts}", f"Econ: {eco:.2f}",
         team=bowl, avatar_role="bowl")

    # LIVE badge bottom-right of cards row
    lx0 = x0 + total - 150
    _rr(d, [lx0, y1 + 12, lx0 + 150, y1 + 58], 14, RED)
    d.ellipse([lx0 + 26, y1 + 24, lx0 + 46, y1 + 44], fill=WHITE)
    d.text((lx0 + 88, y1 + 35), "LIVE", font=fonts["sm"], anchor="mm", fill=WHITE)


# ---------------- main ----------------

def render_frame(state):
    fonts = F()
    img = ground_backdrop()
    d = ImageDraw.Draw(img)
    draw_top_bar(d, fonts, state)
    draw_info_strip(d, fonts, state)
    draw_ball_strip(d, fonts, state)
    draw_player_cards(d, fonts, state, base_img=img)
    return img


# ---------------- preview ----------------

def main():
    state = {
        "batting_team": "PAK",
        "bowling_team": "SL",
        "score": 145, "wickets": 3, "overs": "15.2",
        "opp_score": "179-10",
        "innings_target": 180,
        "balls": [
            (16, ["4", "1"]),
            (15, ["1", "4", "1", "W", "2", "0"]),
            (14, ["6", "1", "1", "0", "4", "1"]),
        ],
        "batsmen": [
            {"name": "Saim Ayub", "runs": 55, "balls": 30, "fours": 6,
             "sixes": 2, "striker": True},
            {"name": "Babar Azam", "runs": 40, "balls": 28, "fours": 4, "sixes": 0},
        ],
        "bowler": {"name": "Wanindu Hasaranga", "overs": "2.2", "maidens": 0,
                   "runs": 24, "wkts": 1},
        "crr": "9.47", "rrr": "8.10",
        "target_text": "PAK NEED 35 RUNS IN 28 BALLS",
        "partnership": {"runs": 45, "balls": 28},
        "last_wicket": {"name": "Fakhar Zaman", "runs": 32},
        "next_batsman": "Mohammad Rizwan",
        "event": "FOUR!",
    }
    img = render_frame(state)
    out = "/home/hatch/workspace/cricket/scoreboard-v3-preview.png"
    img.save(out)
    print("saved", out)


if __name__ == "__main__":
    main()
