#!/usr/bin/env python3
"""2D animated live cricket match renderer.

A cartoon cricket match plays ball-by-ball on the left ~70% of the frame,
driven by REAL live score deltas from Cricbuzz (same reliable source as
commentary.py). The right side shows the live score panel.

Layout (1280x720 @ 10fps):
  - x 0..900:   animated 2D cricket field (side view)
  - x 900..1280: live score panel

Ball animation timeline (10fps, ~5.5s per ball):
  RUNUP(10f) -> DELIVERY(5f) -> FLIGHT(5f) -> SHOT(5f) -> OUTCOME(30f) -> SETTLE(10f)

Outcome animations: dot, 1, 2, 3, 4 (boundary race), 6 (big arc into stands),
W (stumps shatter), wd/nb (wide/no-ball).
"""
import math
import random
import re

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 10
FIELD_W = 900  # animated field width; rest is score panel

# ---------------- palette ----------------
NAVY = (16, 22, 38)
NAVY2 = (26, 34, 56)
RED = (178, 20, 20)
GOLD = (255, 210, 60)
BLUE = (0, 144, 255)
WIRED = (226, 60, 60)
WHITE = (255, 255, 255)
SKIN = (196, 140, 100)
PITCH_C = (196, 164, 110)
GRASS1 = (34, 110, 50)
GRASS2 = (30, 100, 46)

TEAM_COLORS = {
    "IND": (30, 90, 200), "PAK": (20, 140, 60), "WI": (140, 30, 40),
    "AUS": (230, 200, 40), "ENG": (40, 60, 160), "NZ": (30, 30, 30),
    "SA": (20, 120, 80), "SL": (30, 60, 180), "BAN": (20, 120, 70),
    "AFG": (200, 40, 40), "ZIM": (200, 30, 30), "IRE": (20, 140, 80),
}
TEAM_NAMES = {
    "WI": "WEST INDIES", "IND": "INDIA", "PAK": "PAKISTAN", "AUS": "AUSTRALIA",
    "ENG": "ENGLAND", "NZ": "NEW ZEALAND", "SA": "SOUTH AFRICA", "RSA": "SOUTH AFRICA",
    "SL": "SRI LANKA", "BAN": "BANGLADESH", "AFG": "AFGHANISTAN", "ZIM": "ZIMBABWE",
    "IRE": "IRELAND",
}

# ---------------- geometry (field coordinates) ----------------
PITCH_Y = 520            # vertical centre of the pitch strip
PITCH_TOP, PITCH_BOT = 478, 562
BOWLER_CREASE_X = 250    # delivery point
BAT_X = 660              # batsman position
STUMPS_X = 715           # batsman-end stumps
KEEPER_X = 795


def load_fonts():
    def f(name, sz):
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}.ttf", sz)
    return {
        "huge": f("DejaVuSans-Bold", 96),
        "big": f("DejaVuSans-Bold", 64),
        "med": f("DejaVuSans-Bold", 40),
        "med2": f("DejaVuSans-Bold", 32),
        "sm": f("DejaVuSans-Bold", 26),
        "sm_r": f("DejaVuSans", 24),
        "tiny": f("DejaVuSans-Bold", 21),
        "tiny_r": f("DejaVuSans", 19),
        "banner": f("DejaVuSans-Bold", 110),
    }


def _rr(d, box, radius, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def ease_out(t):
    return 1 - (1 - t) ** 2


def ease_in_out(t):
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------- static scene ----------------
_SCENE = None
_CROWD = None


def build_scene():
    """Static night-match scene: sky, stands, crowd dots, field, pitch."""
    global _CROWD
    img = Image.new("RGB", (FIELD_W, H), (10, 14, 26))
    d = ImageDraw.Draw(img)
    # night sky
    for y in range(0, 150):
        k = y / 150
        d.line([(0, y), (FIELD_W, y)],
               fill=(int(10 + 14 * k), int(16 + 18 * k), int(40 + 30 * k)))
    # floodlight towers
    for x in (120, 450, 780):
        d.rectangle([x - 5, 20, x + 5, 150], fill=(70, 78, 96))
        d.ellipse([x - 42, 0, x + 42, 62], fill=(235, 240, 250))
        d.ellipse([x - 30, 8, x + 30, 54], fill=(255, 255, 255))
    # stands
    d.rectangle([0, 150, FIELD_W, 330], fill=(28, 34, 56))
    d.rectangle([0, 150, FIELD_W, 168], fill=(36, 44, 70))
    # crowd dots (positions cached; bobbing done per-frame)
    rnd = random.Random(1234)
    _CROWD = []
    for _ in range(1100):
        x = rnd.randrange(6, FIELD_W - 6)
        y = rnd.randrange(176, 322)
        c = rnd.choice([(200, 60, 60), (60, 120, 200), (230, 200, 80),
                        (90, 180, 90), (220, 220, 230), (240, 240, 245)])
        r = rnd.randrange(3, 6)
        _CROWD.append((x, y, r, c, rnd.random() * 6.28))
    # LED ad boards
    for i, (txt, col) in enumerate([("WORLD CRICKET", BLUE), ("LIVE SCORES", RED),
                                    ("CRICKET", GOLD), ("T20", BLUE)]):
        x0 = 20 + i * 225
        d.rectangle([x0, 332, x0 + 205, 362], fill=(12, 16, 30),
                    outline=col, width=2)
    # field grass
    for y in range(364, H):
        k = (y - 364) / (H - 364)
        base = GRASS1 if int(y / 26) % 2 == 0 else GRASS2
        d.line([(0, y), (FIELD_W, y)],
               fill=(int(base[0] * (1 - 0.25 * k) + 8 * k),
                     int(base[1] * (1 - 0.25 * k) + 10 * k),
                     int(base[2] * (1 - 0.25 * k) + 8 * k)))
    # boundary rope
    d.ellipse([-70, 380, FIELD_W + 70, H + 90], outline=WHITE, width=4)
    # pitch strip
    d.rectangle([110, PITCH_TOP, 800, PITCH_BOT], fill=PITCH_C)
    d.rectangle([110, PITCH_TOP, 800, PITCH_BOT], outline=(255, 255, 255), width=2)
    # creases
    d.line([(BOWLER_CREASE_X, PITCH_TOP), (BOWLER_CREASE_X, PITCH_BOT)],
           fill=WHITE, width=3)
    d.line([(STUMPS_X - 40, PITCH_TOP), (STUMPS_X - 40, PITCH_BOT)],
           fill=WHITE, width=3)
    return img


def draw_stumps(d, x, y_base, shattered=0.0):
    """Three stumps + bails. shattered 0..1 animates them flying."""
    for i, dx in enumerate((-11, 0, 11)):
        tilt = shattered * (14 if i == 0 else (-16 if i == 2 else 4))
        top_y = y_base - 52
        if shattered > 0:
            # stumps tip over outward
            d.line([(x + dx, y_base), (x + dx + tilt, top_y + shattered * 18)],
                   fill=(240, 220, 160), width=7)
        else:
            d.rectangle([x + dx - 3, top_y, x + dx + 3, y_base], fill=(240, 220, 160))
    if shattered <= 0:
        d.rectangle([x - 11, y_base - 58, x + 11, y_base - 52], fill=(250, 230, 170))
    else:
        # bails pop up
        by = y_base - 58 - shattered * 46
        d.ellipse([x - 14 - shattered * 20, by, x - 2 - shattered * 20, by + 10],
                  fill=(250, 230, 170))
        d.ellipse([x + 2 + shattered * 20, by - 8, x + 14 + shattered * 20, by + 2],
                  fill=(250, 230, 170))


def draw_player(d, x, y_feet, s, shirt, pants, pose="stand", t=0.0, bat_angle=None,
               helmet=False, jersey="", F=None):
    """Flat cartoon cricketer with big-head proportions. y_feet = ground position."""
    s = s * 1.35  # bigger, cuter characters
    hip_y = y_feet - 46 * s
    sh_y = y_feet - 72 * s
    head_r = 15 * s
    head_y = y_feet - 92 * s
    # shadow
    d.ellipse([x - 24 * s, y_feet - 4 * s, x + 24 * s, y_feet + 4 * s],
              fill=(0, 0, 0, 60))
    # legs (thicker, with shoes)
    spread = {"stand": 9, "run": 22, "bowl": 15, "bat": 13, "crouch": 17,
              "dive": 26, "appeal": 10, "keep": 14}.get(pose, 9)
    phase = math.sin(t * 11) if pose == "run" else 0
    for side in (-1, 1):
        sw = spread * s * (1 + 0.55 * phase * side)
        kx = x + side * sw * 0.5
        ky = (hip_y + y_feet) / 2
        d.line([(x, hip_y), (kx, ky), (x + side * sw, y_feet)],
               fill=pants, width=int(10 * s), joint="curve")
        # shoe
        d.ellipse([x + side * sw - 7 * s, y_feet - 5 * s,
                   x + side * sw + 7 * s, y_feet + 3 * s], fill=(30, 30, 34))
    # torso (jersey with white side stripe)
    lean = {"bowl": 9, "bat": -7, "dive": 22, "crouch": 7, "run": 6}.get(pose, 0)
    tx = x + lean * s
    d.line([(x, hip_y), (tx, sh_y)], fill=shirt, width=int(20 * s))
    d.line([(x - 3 * s, hip_y + 4 * s), (tx - 3 * s, sh_y + 6 * s)],
           fill=WHITE, width=int(4 * s))
    # jersey team code on chest
    if jersey and F is not None:
        d.text((tx, (hip_y + sh_y) / 2), jersey, font=F["tiny"],
               anchor="mm", fill=WHITE)
    # arms
    arm_w = int(8 * s)
    if pose == "bowl":
        ang = t * 6.28
        ax = tx + math.cos(ang) * 30 * s
        ay = sh_y - math.sin(ang) * 30 * s
        d.line([(tx, sh_y), (ax, ay)], fill=shirt, width=arm_w)
        d.line([(tx, sh_y), (tx - 22 * s, sh_y + 10 * s)], fill=shirt, width=arm_w)
    elif pose == "bat" and bat_angle is not None:
        hx = tx + math.cos(bat_angle) * 22 * s
        hy = sh_y + math.sin(bat_angle) * 22 * s
        d.line([(tx, sh_y), (hx, hy)], fill=shirt, width=arm_w)
        d.line([(tx, sh_y), (tx - 12 * s, sh_y + 18 * s)], fill=shirt, width=arm_w)
        # proper bat: handle + wide blade as rotated polygon
        dx, dy = math.cos(bat_angle), math.sin(bat_angle)
        px, py = -dy, dx  # perpendicular
        bx, by = hx + dx * 12 * s, hy + dy * 12 * s  # handle end -> blade start
        ex, ey = hx + dx * 52 * s, hy + dy * 52 * s  # blade end
        bw = 11 * s
        d.polygon([(bx + px * 3 * s, by + py * 3 * s),
                   (bx - px * 3 * s, by - py * 3 * s),
                   (ex - px * bw, ey - py * bw),
                   (ex + px * bw, ey + py * bw)], fill=(222, 184, 120),
                  outline=(160, 120, 70))
    elif pose == "appeal":
        d.line([(tx, sh_y), (tx - 10 * s, sh_y - 34 * s)], fill=shirt, width=arm_w)
        d.line([(tx, sh_y), (tx + 10 * s, sh_y - 34 * s)], fill=shirt, width=arm_w)
    elif pose == "keep":
        # gloves up
        for side in (-1, 1):
            gx, gy = tx + side * 16 * s, sh_y - 12 * s
            d.line([(tx, sh_y), (gx, gy)], fill=shirt, width=arm_w)
            d.ellipse([gx - 7 * s, gy - 7 * s, gx + 7 * s, gy + 7 * s], fill=(250, 250, 250))
    else:
        d.line([(tx, sh_y), (tx - 15 * s, sh_y + 18 * s)], fill=shirt, width=arm_w)
        d.line([(tx, sh_y), (tx + 15 * s, sh_y + 18 * s)], fill=shirt, width=arm_w)
    # head
    d.ellipse([tx - head_r, head_y - head_r, tx + head_r, head_y + head_r], fill=SKIN)
    # eyes (simple, facing right = direction of play)
    ex = tx + 5 * s
    d.ellipse([ex - 3 * s, head_y - 4 * s, ex + 1 * s, head_y + 0 * s], fill=(20, 20, 24))
    if helmet:
        # cricket helmet: colored shell + grill
        d.pieslice([tx - head_r - 3 * s, head_y - head_r - 10 * s,
                    tx + head_r + 3 * s, head_y + 6 * s], 180, 360, fill=shirt)
        d.rectangle([tx - head_r - 3 * s, head_y - head_r - 2 * s,
                     tx + head_r + 3 * s, head_y - head_r + 2 * s], fill=(40, 40, 48))
        for gx in range(int(tx - head_r + 4 * s), int(tx + head_r - 2 * s), int(6 * s)):
            d.line([(gx, head_y - 2 * s), (gx, head_y + head_r - 2 * s)],
                   fill=(60, 60, 70), width=2)
    else:
        # cap
        d.pieslice([tx - head_r, head_y - head_r - 7 * s,
                    tx + head_r, head_y + 5 * s], 180, 360, fill=shirt)
        d.rectangle([tx + head_r - 4 * s, head_y - 4 * s,
                     tx + head_r + 10 * s, head_y - 1 * s], fill=shirt)

# ---------------- ball animation state machine ----------------
# phases (in frames @10fps): RUNUP 10, DELIVERY 5, FLIGHT 5, SHOT 5, OUTCOME 30, SETTLE 12
PH_RUNUP, PH_DELIVERY, PH_FLIGHT, PH_SHOT, PH_OUTCOME, PH_SETTLE = range(6)
PH_LEN = [10, 5, 5, 5, 30, 12]

# where the ball goes after the shot, per token
OUTCOME_PATH = {
    "0":  [(660, 512), (795, 512)],          # to keeper
    "1":  [(660, 512), (560, 600)],          # to fielder
    "2":  [(660, 512), (380, 620)],          # deep
    "3":  [(660, 512), (830, 590)],          # nearly boundary, stopped
    "4":  [(660, 512), (895, 545)],          # boundary!
    "6":  [(660, 512), (700, 180)],          # huge arc into stands (apex)
    "W":  [(660, 512), (715, 520)],          # into the stumps
    "wd": [(660, 512), (790, 470)],          # wide past batsman
    "nb": [(660, 512), (795, 512)],
}
BANNERS = {
    "4": ("FOUR!", (30, 160, 60)), "6": ("SIX!", (200, 120, 10)),
    "W": ("WICKET!", (178, 20, 20)), "wd": ("WIDE", (110, 70, 150)),
    "nb": ("NO BALL", (110, 70, 150)), "0": ("DOT BALL", (70, 80, 110)),
}


class BallAnim:
    """One ball's full animation. token in 0,1,2,3,4,6,W,wd,nb."""

    def __init__(self, token):
        self.token = token
        self.phase = PH_RUNUP
        self.f = 0  # frame within phase
        self.trail = []
        self.done = False

    def step(self):
        self.f += 1
        if self.f >= PH_LEN[self.phase]:
            self.f = 0
            self.phase += 1
            if self.phase > PH_SETTLE:
                self.done = True

    def _ball_pos(self):
        """Ball (x, y) for current phase/frame. None when ball not visible."""
        p, f = self.phase, self.f
        if p == PH_RUNUP:
            return None
        if p == PH_DELIVERY:
            t = f / PH_LEN[p]
            return (lerp(262, 330, t), lerp(498, 492, t))
        if p == PH_FLIGHT:
            t = f / PH_LEN[p]
            x = lerp(330, BAT_X - 20, ease_in_out(t))
            # proper pitch bounce: drop to the pitch, then rise to the bat
            if t < 0.55:
                k = t / 0.55
                y = lerp(484, 524, k * k)
            else:
                k = (t - 0.55) / 0.45
                y = lerp(524, 506, ease_out(k))
            return (x, y)
        if p == PH_SHOT:
            return (BAT_X - 20, 510)
        if p == PH_OUTCOME:
            t = f / PH_LEN[p]
            path = OUTCOME_PATH.get(self.token, OUTCOME_PATH["0"])
            (x0, y0), (x1, y1) = path[0], path[1]
            if self.token == "6":
                # parabolic arc: up over the stands then down
                x = lerp(x0, 760, ease_out(min(1, t * 1.6)))
                y = y0 - math.sin(min(1, t * 1.15) * math.pi) * 380
                return (x, y)
            if self.token == "4":
                t2 = ease_out(min(1, t * 1.4))
                return (lerp(x0, x1, t2), lerp(y0, y1, t2))
            if self.token == "W":
                return (x1, y1) if t > 0.15 else (lerp(x0, x1, t * 6), lerp(y0, y1, t * 6))
            return (lerp(x0, x1, ease_out(t)), lerp(y0, y1, ease_out(t)))
        return None  # SETTLE: ball dead

    def bowler_x(self):
        p, f = self.phase, self.f
        if p == PH_RUNUP:
            return lerp(150, 250, ease_in_out(f / PH_LEN[p]))
        if p in (PH_DELIVERY, PH_FLIGHT):
            return 262
        if p == PH_SHOT:
            return 280
        # follow-through then walk back
        t = f / PH_LEN[p]
        return lerp(300, 190, t) if p == PH_OUTCOME else lerp(190, 150, t)

    def batsman_swing(self):
        """Bat angle (radians). None = guard pose."""
        p, f = self.phase, self.f
        if p == PH_SHOT:
            t = f / PH_LEN[p]
            return lerp(2.4, -0.6, ease_out(t))  # big swing
        if p == PH_FLIGHT:
            return 2.4  # bat raised, waiting
        return None

    def banner(self):
        if self.phase == PH_OUTCOME and self.token in BANNERS:
            txt, col = BANNERS[self.token]
            # pop-in over first 4 frames, hold, fade at end
            tin = min(1, self.f / 4)
            tout = max(0, min(1, (PH_LEN[PH_OUTCOME] - self.f) / 6))
            return txt, col, tin * tout
        return None

    def shattered(self):
        if self.token == "W" and self.phase == PH_OUTCOME:
            return min(1, self.f / 8)
        return 0.0

    def crowd_excite(self):
        if self.phase == PH_OUTCOME and self.token in ("4", "6", "W"):
            return min(1, self.f / 6)
        return 0.0

    def fielder_chase(self, idx):
        """Offset for the chasing fielder (index into FIELDERS)."""
        if self.phase != PH_OUTCOME:
            return (0, 0)
        t = ease_out(self.f / PH_LEN[PH_OUTCOME])
        if self.token in ("1", "2") and idx == 1:
            return (60 * t, -30 * t)
        if self.token == "3" and idx == 3:
            return (50 * t, 40 * t)  # dive towards boundary
        if self.token == "4" and idx == 3:
            return (30 * t, 20 * t)  # late chase, too late
        return (0, 0)


def draw_crowd(d, frame_no, excite=0.0):
    amp = 3 + excite * 9
    for (x, y, r, c, ph) in _CROWD:
        yo = math.sin(frame_no * 0.35 + ph) * amp
        d.ellipse([x - r, y + yo - r, x + r, y + yo + r], fill=c)


def draw_ball(d, pos, trail):
    for i, (tx, ty) in enumerate(trail):
        a = int(90 * (i + 1) / max(1, len(trail)))
        r = 4 + 3 * (i + 1) / max(1, len(trail))
        d.ellipse([tx - r, ty - r, tx + r, ty + r],
                  fill=(255, 120 - a // 3, 120 - a // 3))
    x, y = pos
    d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=WHITE, outline=(178, 20, 20), width=2)
    d.arc([x - 8, y - 8, x + 8, y + 8], 200, 340, fill=(178, 20, 20), width=2)


def draw_banner(d, F, txt, col, alpha):
    if alpha <= 0:
        return
    # dark pill behind text
    tw = d.textlength(txt, font=F["banner"])
    cx, cy = FIELD_W / 2, 250
    sc = 0.6 + 0.4 * alpha
    pad = 40 * sc
    _rr(d, [cx - tw * sc / 2 - pad, cy - 70 * sc, cx + tw * sc / 2 + pad, cy + 70 * sc],
        26, (10, 12, 24), outline=col, width=5)
    d.text((cx, cy), txt, font=F["banner"], anchor="mm", fill=col)

# ---------------- per-frame field renderer ----------------
FIELDERS = [(430, 425), (540, 630), (320, 640), (770, 425), (660, 645), (300, 400)]

def render_field(F, frame_no, ball_anim, bat_col, bowl_col, bat_code="IND",
                 bowl_code="WI", excite=0.0, banner=True):
    img = build_scene() if _SCENE is None else _SCENE.copy()
    d = ImageDraw.Draw(img)
    draw_crowd(d, frame_no, excite + (ball_anim.crowd_excite() if ball_anim else 0))
    # sightscreen behind the bowler's arm (white panel beyond boundary, left)
    d.rectangle([18, 392, 108, 470], fill=(235, 238, 242), outline=(160, 166, 178), width=2)

    # bowler
    if ball_anim and not ball_anim.done:
        bx = ball_anim.bowler_x()
        pose = "run" if ball_anim.phase == PH_RUNUP else ("bowl" if ball_anim.phase in (PH_DELIVERY, PH_FLIGHT) else "stand")
        draw_player(d, bx, PITCH_Y + 40, 1.0, bowl_col, (30, 30, 40), pose,
                    t=frame_no / FPS, jersey=bowl_code, F=F)
    else:
        draw_player(d, 150, PITCH_Y + 40, 1.0, bowl_col, (30, 30, 40), "stand",
                    t=frame_no / FPS, jersey=bowl_code, F=F)
    # umpire at bowler's end (dark blazer, white hat) — off to the side
    draw_player(d, 92, PITCH_Y + 62, 1.0, (45, 48, 60), (230, 230, 235), "stand",
                t=frame_no / FPS)
    # batsman (helmet on)
    swing = ball_anim.batsman_swing() if ball_anim and not ball_anim.done else None
    draw_player(d, BAT_X, PITCH_Y + 42, 1.0, bat_col, (245, 245, 245),
                "bat", t=frame_no / FPS, bat_angle=swing if swing is not None else 2.4,
                helmet=True, jersey=bat_code, F=F)
    # stumps (batsman end; shatter on wicket)
    sh = ball_anim.shattered() if ball_anim else 0.0
    draw_stumps(d, STUMPS_X, PITCH_Y + 42, shattered=sh)
    # bowler-end stumps
    draw_stumps(d, 200, PITCH_Y + 40)
    # keeper
    draw_player(d, KEEPER_X, PITCH_Y + 44, 0.95, bowl_col, (30, 30, 40), "keep",
                t=frame_no / FPS, jersey=bowl_code, F=F)
    # fielders
    for i, (fx, fy) in enumerate(FIELDERS):
        dx, dy = ball_anim.fielder_chase(i) if ball_anim and not ball_anim.done else (0, 0)
        pose = "run" if (dx or dy) else "crouch"
        draw_player(d, fx + dx, fy + dy, 0.9, bowl_col, (30, 30, 40), pose,
                    t=frame_no / FPS, jersey=bowl_code, F=F)
    # appeal on wicket!
    if ball_anim and ball_anim.token == "W" and ball_anim.phase == PH_OUTCOME:
        if ball_anim.f > 10:
            draw_player(d, 300, PITCH_Y + 40, 1.0, bowl_col, (30, 30, 40),
                        "appeal", t=frame_no / FPS)

    # ball + trail
    if ball_anim and not ball_anim.done:
        pos = ball_anim._ball_pos()
        if pos:
            ball_anim.trail.append(pos)
            if len(ball_anim.trail) > 7:
                ball_anim.trail.pop(0)
            draw_ball(d, pos, ball_anim.trail[:-1])
        b = ball_anim.banner()
        if b and banner:
            draw_banner(d, F, b[0], b[1], b[2])
    return img


# ---------------- score panel (right side) ----------------
def render_panel(d, F, st, bat_col):
    x0 = FIELD_W
    d.rectangle([x0, 0, W, H], fill=NAVY)
    d.line([(x0, 0), (x0, H)], fill=RED, width=4)
    px = x0 + 24
    # header
    _rr(d, [px, 16, W - 20, 62], 10, RED)
    d.text((px + 52, 39), "LIVE", font=F["sm"], anchor="mm", fill=WHITE)
    d.text((px + 108, 30), "WORLD CRICKET", font=F["tiny"], anchor="lm", fill=WHITE)
    d.text((px + 108, 50), "UPDATES", font=F["tiny"], anchor="lm", fill=WHITE)
    y = 84
    team_full = TEAM_NAMES.get(st.get("team"), st.get("team") or "--")
    d.text((px, y), team_full, font=F["sm"], anchor="lm", fill=(170, 180, 195))
    y += 8
    score_txt = f"{st['runs']}/{st['wkts']}" if st.get("runs") else "--"
    d.text((px, y + 62), score_txt, font=F["huge"], anchor="lm", fill=WHITE)
    y += 128
    d.text((px, y), f"OVERS  {st.get('overs') or '--'}", font=F["sm"], anchor="lm", fill=GOLD)
    y += 40
    d.text((px, y), f"CRR  {st.get('crr') or '--'}", font=F["sm"], anchor="lm", fill=GOLD)
    y += 52
    d.line([(px, y), (W - 24, y)], fill=(70, 80, 100), width=2)
    y += 18
    # batters
    for b in st.get("batters", [])[:2]:
        nm = (b["name"] + ("*" if b["striker"] else "")).upper()
        if len(nm) > 20:
            nm = nm[:19] + "."
        d.text((px, y), nm, font=F["tiny"], anchor="lm", fill=WHITE)
        d.text((W - 32, y), f"{b['r']}({b['b']})", font=F["tiny"], anchor="rm", fill=GOLD)
        y += 34
    y += 6
    # bowler
    for bw in st.get("bowlers", [])[:1]:
        nm = (bw["name"] + ("*" if bw.get("cur") else "")).upper()
        if len(nm) > 20:
            nm = nm[:19] + "."
        d.text((px, y), "BOWL " + nm, font=F["tiny"], anchor="lm", fill=(170, 180, 195))
        d.text((W - 32, y), f"{bw['o']}-{bw['w']}", font=F["tiny"], anchor="rm", fill=GOLD)
        y += 34
    y += 10
    d.line([(px, y), (W - 24, y)], fill=(70, 80, 100), width=2)
    y += 18
    # win predictor
    d.text((px, y), "WIN PREDICTOR", font=F["tiny"], anchor="lm", fill=(170, 180, 195))
    y += 30
    try:
        pa, pb = int(st["win_a_pct"]), int(st["win_b_pct"])
    except Exception:
        pa, pb = 50, 50
    bx1 = W - 32
    d.rectangle([px, y, bx1, y + 22], fill=(50, 58, 80))
    wa = (bx1 - px) * pa // 100
    d.rectangle([px, y, px + wa, y + 22], fill=BLUE)
    d.rectangle([px + wa + 3, y, bx1, y + 22], fill=WIRED)
    y += 34
    d.text((px, y), f"{st.get('win_a') or ''} {pa}%", font=F["tiny_r"], anchor="lm", fill=WHITE)
    d.text((bx1, y), f"{pb}% {st.get('win_b') or ''}", font=F["tiny_r"], anchor="rm", fill=WHITE)
    y += 44
    # recent balls
    d.text((px, y), "RECENT BALLS", font=F["tiny"], anchor="lm", fill=(170, 180, 195))
    y += 34
    bx = px
    for num, grp in st.get("recent_overs", [])[-1:]:
        for tok in grp[-8:]:
            s2 = 32
            fill = (52, 62, 88)
            fg = (235, 240, 248)
            t2 = tok.strip()
            if t2 == "4":
                fill, fg = (30, 140, 60), WHITE
            elif t2 == "6":
                fill, fg = (150, 90, 10), WHITE
            elif t2.upper() == "W":
                fill, fg = RED, WHITE
            _rr(d, [bx, y, bx + s2, y + s2], 7, fill)
            d.text((bx + s2 / 2, y + s2 / 2), t2.upper(), font=F["tiny_r"],
                   anchor="mm", fill=fg)
            bx += s2 + 7
    # footer status
    sub = (st.get("subtitle") or st.get("status") or "")[:42]
    d.text((px, H - 30), sub, font=F["tiny_r"], anchor="lm", fill=(170, 180, 195))


# ---------------- ball event detection (score deltas) ----------------
def _parse_balls(overs_str):
    try:
        o = str(overs_str).strip()
        if "." in o:
            ov, b = o.split(".")
            return int(ov) * 6 + int(b)
        return int(o) * 6
    except Exception:
        return None


def _latest_token(recent_overs):
    try:
        return (recent_overs[-1][1][-1] or "").strip().lower()
    except Exception:
        return ""


def infer_tokens(prev, st):
    """Return list of ball tokens since prev state. [] if none/resync."""
    team = st.get("team")
    try:
        runs, wkts = int(st["runs"]), int(st["wkts"])
    except (TypeError, ValueError):
        return []
    balls = _parse_balls(st.get("overs"))
    if balls is None or prev is None:
        return []
    pt, pr, pw, pb = prev
    if team != pt or balls < pb - 6:
        return []  # new innings / resync
    db, dr, dw = balls - pb, runs - pr, wkts - pw
    if db < 0 or dr < 0 or dw < 0 or dw > 2 or db > 8 or dr > 14:
        return []
    if db == 0 and dr == 0 and dw == 0:
        return []
    hint = _latest_token(st.get("recent_overs"))
    toks = []
    if dw > 0:
        toks += ["W"] * dw
        # remaining balls unknown -> dots
        toks += ["0"] * max(0, db - dw)
    elif db == 0:
        toks.append("nb" if hint == "nb" else "wd")
    else:
        # distribute runs across balls: big hits first
        rem_r, rem_b = dr, db
        order = []
        while rem_b > 0:
            if rem_r >= 6 and rem_b == 1:
                order.append("6"); rem_r -= 6
            elif rem_r >= 4 and rem_r - 4 <= (rem_b - 1) * 6:
                # plausible boundary; use hint when it matches
                if hint in ("4", "6") and rem_b == 1:
                    order.append(hint); rem_r -= int(hint)
                else:
                    order.append("4"); rem_r -= 4
            elif rem_r > 0:
                take = min(rem_r, 3)
                order.append(str(take)); rem_r -= take
            else:
                order.append("0")
            rem_b -= 1
        toks = order
    # normalize
    out = []
    for t in toks:
        t = t.strip().lower()
        out.append({"w": "W"}.get(t, t if t in ("0", "1", "2", "3", "4", "6", "wd", "nb") else "0"))
    return out


# ---------------- animator ----------------
class MatchAnimator:
    def __init__(self, F):
        global _SCENE
        _SCENE = build_scene()
        self.F = F
        self.queue = []          # pending ball tokens
        self.current = None      # active BallAnim
        self.prev = None         # (team, runs, wkts, balls)
        self.st = None
        self.excite = 0.0

    def update(self, st):
        """Feed fresh score state; queue new ball animations."""
        self.st = st
        team = st.get("team")
        try:
            runs, wkts = int(st["runs"]), int(st["wkts"])
        except (TypeError, ValueError):
            return
        balls = _parse_balls(st.get("overs"))
        if balls is None:
            return
        if self.prev is None:
            self.prev = (team, runs, wkts, balls)
            return
        toks = infer_tokens(self.prev, st)
        pt, pr, pw, pb = self.prev
        # advance prev (resync-safe: infer_tokens already validated)
        if not (team != pt or balls < pb - 6):
            self.prev = (team, runs, wkts, balls)
        else:
            self.prev = (team, runs, wkts, balls)
            self.queue.clear()
            self.current = None
        for t in toks:
            if len(self.queue) < 12:
                self.queue.append(t)

    def render(self, frame_no):
        F = self.F
        st = self.st or {}
        # start next ball when idle
        if (self.current is None or self.current.done) and self.queue:
            self.current = BallAnim(self.queue.pop(0))
        if self.current and not self.current.done:
            self.current.step()
        team = st.get("team") or "IND"
        # batting team color vs bowling team color (dynamic per match)
        bat_col = TEAM_COLORS.get(team, (30, 90, 200))
        mt = (st.get("match_title") or "")
        bowl_col, bowl_code = (140, 30, 40), "OPP"
        for code, col in TEAM_COLORS.items():
            if code != team and code in mt.upper():
                bowl_col, bowl_code = col, code
                break
        img = Image.new("RGB", (W, H), NAVY)
        field = render_field(F, frame_no, self.current, bat_col, bowl_col,
                             bat_code=team, bowl_code=bowl_code)
        img.paste(field, (0, 0))
        d = ImageDraw.Draw(img)
        render_panel(d, F, st, bat_col)
        return img


def render_anim_frame(st, F, frame_no, animator=None):
    """Drop-in compatible with stream_v2's render_v2(st, F, frame_no)."""
    global _ANIM
    if animator is None:
        if "_ANIM" not in globals() or _ANIM is None:
            _ANIM = MatchAnimator(F)
        animator = _ANIM
    animator.update(st)
    return animator.render(frame_no)


_ANIM = None
