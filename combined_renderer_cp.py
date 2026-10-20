#!/usr/bin/env python3
"""Cricket Point-style clean live renderer: static 2D field + TV scoreboard.

Clean, uncluttered broadcast look modelled on the Cricket Point reference:
- Static 2D cricket ground (no moving animation) with fielders in fixed
  positions and "CRICKET PULSE" watermarked on the pitch
- scoreboard_v3 TV overlay: top team panels, center event banner,
  blue info strip, ball-by-ball strip, bottom player cards

API:
    CleanRenderer(F)       # F = anim_match.load_fonts()
    r.render(st, frame_no) # st = fetch_rich-style live state dict
                           # -> PIL.Image 1920x1080 RGB
"""

from PIL import Image, ImageDraw, ImageFont

import anim_match
import scoreboard_v3 as scoreboard_tv
from combined_renderer_v3 import tv_state_from_live

OUT_W, OUT_H = 1920, 1080


def _font(name, size):
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}.ttf", size)


_FIELD_BG = None


def clean_field():
    """Static clean 2D cricket ground, Cricket Point style.

    If a custom background photo (bg_custom.jpg next to this file) exists,
    it is used as the full-frame background instead (cover-fit, center-crop).
    """
    global _FIELD_BG
    if _FIELD_BG is not None:
        return _FIELD_BG.copy()
    W, H = OUT_W, OUT_H
    import os
    custom = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "bg_custom.jpg")
    if os.path.exists(custom):
        try:
            im = Image.open(custom).convert("RGB")
            scale = max(W / im.width, H / im.height)
            nw, nh = int(im.width * scale + 0.5), int(im.height * scale + 0.5)
            im = im.resize((nw, nh), Image.LANCZOS)
            x0 = (nw - W) // 2
            y0 = (nh - H) // 2
            im = im.crop((x0, y0, x0 + W, y0 + H))
            _FIELD_BG = im
            return im.copy()
        except Exception:
            pass
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    # outfield: rich green gradient
    for y in range(0, H):
        k = y / H
        d.line([(0, y), (W, y)],
               fill=(int(52 + 18 * k), int(148 + 26 * k), int(72 + 16 * k)))
    # mowing stripes (subtle vertical bands)
    for x in range(0, W, 320):
        d.rectangle([x, 0, x + 160, H], fill=(58, 158, 80))
    d = ImageDraw.Draw(img, "RGBA")
    # 30-yard circle
    cx, cy = W / 2, H * 0.62
    rx, ry = 620, 330
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
              outline=(255, 255, 255, 220), width=4)
    # boundary rope
    d.ellipse([cx - 880, cy - 470, cx + 880, cy + 470],
              outline=(245, 245, 245, 200), width=5)
    # pitch (center strip)
    pw, ph = 150, 420
    d.rectangle([cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2],
                fill=(196, 168, 118, 255))
    d.rectangle([cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2],
                outline=(255, 255, 255, 180), width=3)
    # crease lines
    d.line([(cx - pw / 2, cy - 60), (cx + pw / 2, cy - 60)],
           fill=(255, 255, 255, 220), width=3)
    d.line([(cx - pw / 2, cy + 60), (cx + pw / 2, cy + 60)],
           fill=(255, 255, 255, 220), width=3)
    # stumps (simple)
    for sx in (cx - 24, cx, cx + 24):
        d.rectangle([sx - 4, cy - ph / 2 - 34, sx + 4, cy - ph / 2],
                    fill=(240, 230, 200, 255))
        d.rectangle([sx - 4, cy + ph / 2, sx + 4, cy + ph / 2 + 34],
                    fill=(240, 230, 200, 255))
    # fielders: simple dark silhouettes spread around the ground
    import math
    for i in range(9):
        ang = 2 * math.pi * i / 9 + 0.35
        fx = cx + int(430 * math.cos(ang))
        fy = cy + int(230 * math.sin(ang)) - 30
        # skip fielders that would sit under the scoreboard strips/cards
        if fy < 330 or fy > 790:
            continue
        # body: circle head + rounded body
        d.ellipse([fx - 14, fy - 46, fx + 14, fy - 18], fill=(30, 34, 48, 255))
        d.rounded_rectangle([fx - 20, fy - 18, fx + 20, fy + 34], radius=12,
                            fill=(30, 34, 48, 255))
    # "CRICKET PULSE" on the outfield above the pitch (like CRICKET POINT)
    f_wm = _font("DejaVuSans-Bold", 96)
    txt = "CRICKET PULSE"
    tw = d.textlength(txt, font=f_wm)
    d.text(((W - tw) / 2, 360), txt, font=f_wm,
           fill=(255, 255, 255, 32))
    _FIELD_BG = img
    return img.copy()


class CleanRenderer:
    """Static-field Cricket Point-style renderer."""

    def __init__(self, F):
        self.F = F
        self._tv_fonts = scoreboard_tv.F()
        self._bg = clean_field()

    def render(self, st, frame_no):
        # event flash from recent ball token (FOUR!/SIX!/WICKET!)
        event = ""
        balls = st.get("recent_overs") or st.get("balls") or []
        flat = []
        if balls and isinstance(balls[0], (list, tuple)):
            for _, toks in balls:
                flat.extend(toks)
        else:
            flat = list(balls)
        if flat:
            last = str(flat[-1]).strip().upper()
            event = {"4": "FOUR!", "6": "SIX!", "W": "WICKET!"}.get(last, "")
        tv = tv_state_from_live(st, event)

        bg = self._bg.copy().convert("RGBA")
        ov = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        fonts = self._tv_fonts
        scoreboard_tv.draw_top_bar(od, fonts, tv)
        scoreboard_tv.draw_info_strip(od, fonts, tv)
        scoreboard_tv.draw_ball_strip(od, fonts, tv)
        scoreboard_tv.draw_player_cards(od, fonts, tv, base_img=ov)
        return Image.alpha_composite(bg, ov).convert("RGB")


def _demo():
    F = anim_match.load_fonts()
    r = CleanRenderer(F)
    st = {
        "match_title": "India vs West Indies, 5th T20I",
        "runs": 186, "wkts": 4, "overs": "16.3",
        "crr": "11.32", "rrr": "",
        "status": "IND NEED 42 RUNS IN 21 BALLS",
        "innings_target": 228,
        "recent_overs": [(17, ["1", "4"]), (16, ["6", "1", "W", "1", "4", "2"])],
        "batters": [
            {"name": "Abhishek Sharma", "r": 78, "b": 42, "fours": 8,
             "sixes": 4, "striker": True},
            {"name": "Tilak Varma", "r": 45, "b": 30, "fours": 4, "sixes": 2},
        ],
        "bowlers": [
            {"name": "Akeal Hosein", "o": "3.3", "m": 0, "r": 38, "w": 2,
             "cur": True},
        ],
        "partnership": {"runs": 67, "balls": 41},
        "last_wicket": {"name": "Suryakumar Yadav", "runs": 28},
        "next_batsman": "Hardik Pandya",
    }
    # tv_state_from_live expects these keys; patch extras
    img = r.render(st, 0)
    out = "/home/hatch/workspace/cricket/clean-cp-preview.png"
    img.save(out)
    print("saved", out)


if __name__ == "__main__":
    _demo()
