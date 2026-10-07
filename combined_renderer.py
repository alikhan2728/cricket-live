#!/usr/bin/env python3
"""Combined stream renderer: 2D animated cricket field + TV broadcast overlay.

Final output: 1920x1080 frame with the LIVE animated field (bowler run-up,
ball flight, shots, fielders) full-bleed behind the TV scoreboard pieces
(top bar, info strip, ball-by-ball strip, player cards, event banners).

API:
    CombinedRenderer(F)      # F = anim_match.load_fonts()
    r.render(st, frame_no)   # st = fetch_rich-style live state dict
                             # frame_no = 10fps animation frame counter
                             # -> PIL.Image 1920x1080 RGB

    tv_state_from_live(st, event="")  # adapter: live state -> scoreboard_tv state
"""

from PIL import Image, ImageDraw

import anim_match
from anim_match import MatchAnimator, BallAnim, PH_OUTCOME
import scoreboard_tv

OUT_W, OUT_H = 1920, 1080
# field (900x720) is cropped to the visible band, then scaled straight to
# 1920x1080. Band keeps six-apex (~y130) and pitch action visible. Tunable.
FIELD_CROP_TOP_ORIG = 95
FIELD_CROP_H_ORIG = 506  # 1080 / (1920/900)

TEAM_CODES = ("PAK", "IND", "AUS", "ENG", "NZ", "SA", "SL", "BAN", "AFG",
              "WI", "ZIM", "IRE")


def tv_state_from_live(st, event=""):
    """Adapt a fetch_rich-style live state dict to scoreboard_tv.render_frame state."""
    batters = st.get("batters") or []
    batsmen = []
    for b in batters[:2]:
        batsmen.append({
            "name": b.get("name", ""),
            "runs": b.get("r", 0), "balls": b.get("b", 0),
            "fours": b.get("fours", 0), "sixes": b.get("sixes", 0),
            "striker": bool(b.get("striker")),
        })
    bowlers = st.get("bowlers") or []
    bw = next((x for x in bowlers if x.get("cur")), bowlers[0] if bowlers else {})
    bowler = {"name": bw.get("name", "Bowler"), "overs": str(bw.get("o", "0")),
              "maidens": bw.get("m", 0), "runs": bw.get("r", 0),
              "wkts": bw.get("w", 0)}
    team = (st.get("team") or "IND").upper()
    mt = (st.get("match_title") or "").upper()
    bowl_team = "OPP"
    for code in TEAM_CODES:
        if code != team and code in mt:
            bowl_team = code
            break
    return {
        "batting_team": team, "bowling_team": bowl_team,
        "score": st.get("runs", 0), "wickets": st.get("wkts", 0),
        "overs": str(st.get("overs", "0")), "opp_score": "",
        "balls": st.get("recent_overs") or [],
        "batsmen": batsmen, "bowler": bowler,
        "crr": st.get("crr", ""), "rrr": "",
        "target_text": st.get("status", ""), "reviews": "",
        "event": event,
    }


class CombinedRenderer:
    def __init__(self, F):
        self.F = F
        self.anim = MatchAnimator(F)  # drives the ball-by-ball animation
        self._tv_fonts = scoreboard_tv.F()

    def _field_frame(self, st, frame_no):
        """Render the animated field only (900x720), no score panel/banner."""
        a = self.anim
        a.update(st)
        if (a.current is None or a.current.done) and a.queue:
            a.current = BallAnim(a.queue.pop(0))
        if a.current and not a.current.done:
            a.current.step()
        team = (st.get("team") or "IND").upper()
        bat_col = anim_match.TEAM_COLORS.get(team, (30, 90, 200))
        mt = (st.get("match_title") or "")
        bowl_col, bowl_code = (140, 30, 40), "OPP"
        for code, col in anim_match.TEAM_COLORS.items():
            if code != team and code in mt.upper():
                bowl_col, bowl_code = col, code
                break
        field = anim_match.render_field(a.F, frame_no, a.current, bat_col,
                                        bowl_col, bat_code=team,
                                        bowl_code=bowl_code, banner=False)
        return field, a.current

    def render(self, st, frame_no):
        field, cur = self._field_frame(st, frame_no)

        # crop the visible band, then scale straight to 1920x1080
        band = field.crop((0, FIELD_CROP_TOP_ORIG, 900,
                           FIELD_CROP_TOP_ORIG + FIELD_CROP_H_ORIG))
        bg = band.resize((OUT_W, OUT_H), Image.BILINEAR).convert("RGBA")

        # TV event banner from the live ball animation
        event = ""
        if cur is not None and cur.phase == PH_OUTCOME:
            event = {"4": "FOUR!", "6": "SIX!", "W": "WICKET!"}.get(cur.token, "")
        tv = tv_state_from_live(st, event)

        ov = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        fonts = self._tv_fonts
        scoreboard_tv.draw_top_bar(od, fonts, tv)
        scoreboard_tv.draw_info_strip(od, fonts, tv)
        scoreboard_tv.draw_event_banner(od, fonts, tv)
        # ball strip on a translucent backing bar
        od.rounded_rectangle([40, 780, 1880, 876], radius=18,
                             fill=(10, 14, 28, 205),
                             outline=(70, 78, 100), width=2)
        scoreboard_tv.draw_ball_strip(od, fonts, tv, y=794)
        # player cards, translucent
        scoreboard_tv.draw_player_cards(od, fonts, tv, y0=888,
                                        body_fill=(24, 30, 50, 215))
        return Image.alpha_composite(bg, ov).convert("RGB")
