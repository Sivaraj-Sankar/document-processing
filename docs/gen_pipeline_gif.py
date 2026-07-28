#!/usr/bin/env python3
"""Generate docs/pipeline.gif — animated LangGraph fan-out diagram."""
import math
import os
import sys
from PIL import Image, ImageDraw, ImageFont

# ── Canvas ────────────────────────────────────────────────────────────────────
W, H = 720, 290

# ── Palette ───────────────────────────────────────────────────────────────────
BG         = (10,  17,  32)
NODE_BG    = (22,  32,  56)
NODE_BD    = (33,  51,  80)
TEXT_C     = (182, 204, 232)
MUTED_C    = (60,  85,  116)
ACCENT_DIM = (27,  52,  96)
FLOW_C     = (75,  157, 245)
EDGE_C     = (23,  46,  72)
ZONE_BD    = (38,  70,  105)
START_C    = (62,  196, 122)
END_C      = (232, 80,  80)
DOT_C      = (16,  26,  46)

# ── Node geometry ─────────────────────────────────────────────────────────────
def nd(x, y, w, h):
    return dict(x=x, y=y, w=w, h=h, cx=x + w // 2, cy=y + h // 2)

CLASSIF = nd(98,  116, 142, 52)
TAGGING = nd(336,  26, 132, 52)
FIELEXT = nd(336, 116, 132, 52)
SUMMARY = nd(336, 206, 132, 52)

# ── Edge paths (polylines, matching pipeline-graph.html SVG) ──────────────────
# fan-out junction at x=288, fan-in junction at x=518
EDGES = [
    {"pts": [(70, 142), (91, 142)],                               "offset": 0.0},
    {"pts": [(240, 142), (288, 142), (288,  52), (336,  52)],     "offset": 2.0},
    {"pts": [(240, 142), (336, 142)],                             "offset": 2.5},
    {"pts": [(240, 142), (288, 142), (288, 232), (336, 232)],     "offset": 3.0},
    {"pts": [(468,  52), (518,  52), (518, 142), (600, 142)],     "offset": 5.5},
    {"pts": [(468, 142), (600, 142)],                             "offset": 6.0},
    {"pts": [(468, 232), (518, 232), (518, 142), (600, 142)],     "offset": 6.5},
]

ARROWS    = [(98, 142), (336, 52), (336, 142), (336, 232), (600, 142)]
JUNCTIONS = [(288, 142), (518, 142)]

# ── Animation ─────────────────────────────────────────────────────────────────
DASH_ON    = 5
DASH_OFF   = 9
DASH_CYCLE = DASH_ON + DASH_OFF   # 14 px
N_FRAMES   = 30
FRAME_MS   = 70
PHASE_STEP = DASH_CYCLE / N_FRAMES


# ── Font loading ───────────────────────────────────────────────────────────────
def load_font(size):
    candidates = [
        ("/System/Library/Fonts/Menlo.ttc",     {"index": 0}),
        ("/System/Library/Fonts/SFNSMono.ttf",  {}),
        ("/System/Library/Fonts/Courier New.ttf", {}),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", {}),
        ("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", {}),
    ]
    for path, kwargs in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, **kwargs)
            except Exception:
                pass
    return ImageFont.load_default()


FONT_MD = load_font(11)
FONT_SM = load_font(9)
FONT_XS = load_font(8)


# ── Drawing helpers ────────────────────────────────────────────────────────────
def text_center(draw, text, cx, cy, font, fill):
    """Draw text horizontally and vertically centered at (cx, cy)."""
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1]), text, font=font, fill=fill)


def path_cumulative(pts):
    """Return list of (x, y, cum_dist) for a polyline."""
    result = [(float(pts[0][0]), float(pts[0][1]), 0.0)]
    total = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        total += math.hypot(dx, dy)
        result.append((float(pts[i][0]), float(pts[i][1]), total))
    return result


def point_at(pcp, dist):
    """Interpolate (x, y) at cumulative distance along path_cumulative result."""
    if dist <= 0:
        return (int(pcp[0][0]), int(pcp[0][1]))
    for i in range(1, len(pcp)):
        d0, d1 = pcp[i - 1][2], pcp[i][2]
        if d0 <= dist <= d1:
            t = (dist - d0) / (d1 - d0) if d1 > d0 else 0.0
            x = pcp[i - 1][0] + t * (pcp[i][0] - pcp[i - 1][0])
            y = pcp[i - 1][1] + t * (pcp[i][1] - pcp[i - 1][1])
            return (int(x), int(y))
    return (int(pcp[-1][0]), int(pcp[-1][1]))


def draw_polyline(draw, pts, color, width):
    for i in range(1, len(pts)):
        draw.line([pts[i - 1], pts[i]], fill=color, width=width)


def draw_dashes(draw, pts, phase, color, width=2):
    """Draw animated dashes along a polyline at a given phase offset."""
    pcp = path_cumulative(pts)
    total = pcp[-1][2]
    d = -(phase % DASH_CYCLE)
    while d < total:
        d0 = max(d, 0.0)
        d1 = min(d + DASH_ON, total)
        if d1 > d0:
            p1 = point_at(pcp, d0)
            p2 = point_at(pcp, d1)
            if p1 != p2:
                draw.line([p1, p2], fill=color, width=width)
        d += DASH_CYCLE


def draw_arrowhead(draw, tip_x, tip_y, size=7):
    """Right-pointing filled arrowhead, tip at (tip_x, tip_y)."""
    draw.polygon([
        (tip_x - size, tip_y - size // 2),
        (tip_x, tip_y),
        (tip_x - size, tip_y + size // 2),
    ], fill=FLOW_C)


def draw_terminal(draw, cx, cy, r, ring_color, label, font):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT_DIM, outline=ring_color, width=2)
    text_center(draw, label, cx, cy, font, ring_color)


def draw_node(draw, n, name, sub):
    xy = [n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"]]
    draw.rounded_rectangle(xy, radius=7, fill=NODE_BG, outline=NODE_BD, width=2)
    text_center(draw, name, n["cx"], n["cy"] - 8, FONT_MD, TEXT_C)
    text_center(draw, sub,  n["cx"], n["cy"] + 9, FONT_SM, MUTED_C)


def draw_zone(draw):
    """Dashed border around the parallel node zone."""
    x0, y0, x1, y1 = 322, 16, 482, 272
    dash, gap = 3, 5
    for x in range(x0, x1, dash + gap):
        draw.line([(x, y0), (min(x + dash, x1), y0)], fill=ZONE_BD, width=1)
        draw.line([(x, y1), (min(x + dash, x1), y1)], fill=ZONE_BD, width=1)
    for y in range(y0, y1, dash + gap):
        draw.line([(x0, y), (x0, min(y + dash, y1))], fill=ZONE_BD, width=1)
        draw.line([(x1, y), (x1, min(y + dash, y1))], fill=ZONE_BD, width=1)
    text_center(draw, "PARALLEL", (x0 + x1) // 2, 10, FONT_XS, MUTED_C)


# ── Frame builder ──────────────────────────────────────────────────────────────
def build_frame(global_phase):
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Dot grid background
    for gx in range(0, W, 28):
        for gy in range(0, H, 28):
            draw.point((gx, gy), fill=DOT_C)

    # Parallel zone dashed border
    draw_zone(draw)

    # Static edge tracks
    for e in EDGES:
        draw_polyline(draw, e["pts"], EDGE_C, width=2)

    # Animated flow dashes
    for e in EDGES:
        phase = (global_phase + e["offset"]) % DASH_CYCLE
        draw_dashes(draw, e["pts"], phase, FLOW_C, width=2)

    # Junction dots
    for jx, jy in JUNCTIONS:
        r = 4
        draw.ellipse([jx - r, jy - r, jx + r, jy + r], fill=FLOW_C)

    # Arrowheads
    for ax, ay in ARROWS:
        draw_arrowhead(draw, ax, ay, size=7)

    # Terminal nodes
    draw_terminal(draw, 48,  142, 22, START_C, "START", FONT_XS)
    draw_terminal(draw, 622, 142, 22, END_C,   "END",   FONT_XS)

    # Agent nodes
    draw_node(draw, CLASSIF, "classification",  "ClassificationAgent")
    draw_node(draw, TAGGING, "tagging",          "TaggingAgent")
    draw_node(draw, FIELEXT, "field_extraction", "FieldExtractionAgent")
    draw_node(draw, SUMMARY, "summary",          "SummaryAgent")

    # Step labels
    text_center(draw, "step 1", CLASSIF["cx"], CLASSIF["y"] - 10, FONT_XS, MUTED_C)
    text_center(draw, "step 2", 402,            TAGGING["y"]  - 10, FONT_XS, MUTED_C)

    # Footnote
    text_center(
        draw,
        "fan-out · classification → tagging / field_extraction / summary (parallel)",
        W // 2, H - 9, FONT_XS, MUTED_C,
    )

    return img


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline.gif")

    print(f"Generating {N_FRAMES} frames at {W}×{H}…", flush=True)
    frames = [build_frame(f * PHASE_STEP) for f in range(N_FRAMES)]

    print(f"Saving → {out_path}", flush=True)
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=FRAME_MS,
        optimize=True,
    )
    size_kb = os.path.getsize(out_path) // 1024
    print(f"Done — {size_kb} KB", flush=True)
