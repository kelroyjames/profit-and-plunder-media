"""Blink Test Shorts generator.

Builds 1080x1920 odd-one-out Shorts: letter/number or emoji grids, a 5-second
timer, ticking audio, an answer reveal and a "new test tomorrow" end frame.
Single puzzle (~8s) or three levels in one Short (~15s).
"""
import json, math, random, subprocess, sys, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
NAVY = (11, 21, 56)
NAVY2 = (20, 34, 84)
WHITE = (255, 255, 255)
GOLD = (255, 214, 10)
MUTED = (150, 165, 210)
RED = (255, 77, 77)
GREEN = (52, 211, 153)

FONT_B = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
FONT_XB = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
FONT_M = "/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf"
EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

_fc = {}
def font(path, size):
    k = (path, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]

def centered(d, y, text, f, fill):
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill)

# ---------- glyph tiles ----------
_ec = {}
def emoji_tile(ch, size):
    k = (ch, size)
    if k not in _ec:
        f = ImageFont.truetype(EMOJI, 109)
        im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((80, 80), ch, font=f, embedded_color=True, anchor="mm")
        bb = im.getbbox()
        im = im.crop(bb)
        s = size / max(im.size)
        _ec[k] = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    return _ec[k]

def text_tile(txt, size, colour=WHITE):
    f = font(FONT_B, size)
    im = Image.new("RGBA", (int(size * 3.2), int(size * 1.5)), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((im.width / 2, im.height / 2), txt, font=f, fill=colour, anchor="mm")
    return im

# ---------- puzzle layout ----------
def layout(p, area=(60, 520, 1020, 1480)):
    """Return list of (cx, cy, glyph) and odd index."""
    cols, rows = p["cols"], p["rows"]
    x0, y0, x1, y1 = area
    cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
    rng = random.Random(p.get("seed", 1))
    odd = rng.randrange(cols * rows)
    # keep odd away from the very edge so it is fair on phones
    while (odd % cols) in (0,) and cols > 3 and rng.random() < 0.5:
        odd = rng.randrange(cols * rows)
    cells = []
    for i in range(cols * rows):
        r, c = divmod(i, cols)
        cells.append((x0 + cw * (c + 0.5), y0 + ch * (r + 0.5), p["odd"] if i == odd else p["base"]))
    return cells, odd, min(cw, ch)

def draw_grid(img, p, cells, cell, highlight=None, dim=False):
    kind = p["kind"]
    size = int(cell * (0.78 if kind == "emoji" else p.get("scale", 0.72)))
    for i, (cx, cy, g) in enumerate(cells):
        if kind == "emoji":
            t = emoji_tile(g, size)
        else:
            col = WHITE
            t = text_tile(g, size, col)
        if dim and i != highlight:
            t = t.copy()
            a = t.split()[-1].point(lambda v: int(v * 0.22))
            t.putalpha(a)
        img.alpha_composite(t, (int(cx - t.width / 2), int(cy - t.height / 2)))
    if highlight is not None:
        cx, cy, _ = cells[highlight]
        d = ImageDraw.Draw(img)
        r = cell * 0.55
        for k in range(10):
            d.ellipse([cx - r - k, cy - r - k, cx + r + k, cy + r + k], outline=GOLD)

# ---------- frame chrome ----------
def chrome(img, number, hook, level_label=None):
    d = ImageDraw.Draw(img)
    # top bar
    d.text((60, 70), "BLINK TEST", font=font(FONT_XB, 46), fill=GOLD)
    tag = f"#{number}"
    tw = d.textlength(tag, font=font(FONT_XB, 46))
    d.rounded_rectangle([W - 60 - tw - 36, 58, W - 60, 128], radius=34, fill=NAVY2)
    d.text((W - 60 - tw - 18, 70), tag, font=font(FONT_XB, 46), fill=WHITE)
    # hook
    lines = hook.split("\n")
    y = 200
    for ln in lines:
        f = font(FONT_XB, 92 if len(ln) < 18 else 76)
        centered(d, y, ln, f, WHITE)
        y += f.size + 18
    if level_label:
        f = font(FONT_XB, 48)
        w = d.textlength(level_label, font=f)
        d.rounded_rectangle([(W - w) / 2 - 30, 430, (W + w) / 2 + 30, 498], radius=34, fill=GOLD)
        d.text(((W - w) / 2, 437), level_label, font=f, fill=NAVY)

def timer(img, frac_left, secs_left):
    d = ImageDraw.Draw(img)
    x0, x1, y = 90, W - 90, 1560
    d.rounded_rectangle([x0, y, x1, y + 34], radius=17, fill=NAVY2)
    col = GREEN if frac_left > 0.5 else (GOLD if frac_left > 0.2 else RED)
    if frac_left > 0:
        d.rounded_rectangle([x0, y, x0 + (x1 - x0) * frac_left, y + 34], radius=17, fill=col)
    centered(d, 1620, str(max(1, math.ceil(secs_left))), font(FONT_XB, 120), col)

def footer(img, text, sub=None):
    d = ImageDraw.Draw(img)
    centered(d, 1600, text, font(FONT_XB, 70), GOLD)
    if sub:
        centered(d, 1700, sub, font(FONT_M, 50), WHITE)

def base():
    img = Image.new("RGBA", (W, H), NAVY + (255,))
    return img

# ---------- audio ----------
SR = 44100
def tone(f, dur, vol=0.35, decay=30):
    t = np.arange(int(SR * dur)) / SR
    return vol * np.sin(2 * np.pi * f * t) * np.exp(-decay * t)

def build_audio(events, total, path):
    buf = np.zeros(int(SR * total) + SR)
    for t0, kind in events:
        if kind == "tick":
            s = tone(1800, 0.06, 0.25, 80) + tone(900, 0.06, 0.15, 80)
        elif kind == "tock":
            s = tone(1300, 0.06, 0.25, 80)
        elif kind == "ding":
            s = tone(1318.5, 0.9, 0.35, 4) + tone(1975.5, 0.9, 0.2, 5)
        elif kind == "whoosh":
            n = int(SR * 0.35)
            s = np.random.default_rng(1).normal(0, 0.12, n) * np.hanning(n)
        i = int(t0 * SR)
        buf[i:i + len(s)] += s[: len(buf) - i]
    buf = np.clip(buf[: int(SR * total)], -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((buf * 32767).astype(np.int16).tobytes())

# ---------- video assembly ----------
def render(spec, out_dir):
    """spec: {id, number, hook, levels:[puzzle...], solve:5}"""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    frames, events, t = [], [], 0.0
    solve = spec.get("solve", 5.0)
    multi = len(spec["levels"]) > 1
    if multi:
        solve = spec.get("solve", 3.5)
    labels = ["LEVEL 1 · EASY", "LEVEL 2 · HARD", "LEVEL 3 · IMPOSSIBLE"]
    reveal_dur = 1.3 if not multi else 1.0
    answers = []
    for li, p in enumerate(spec["levels"]):
        cells, odd, cell = layout(p)
        answers.append({"row": odd // p["cols"] + 1, "col": odd % p["cols"] + 1, "odd": p["odd"], "base": p["base"]})
        hook = spec["hook"] if not multi else spec["hook"]
        lab = labels[li] if multi else None
        static = base(); chrome(static, spec["number"], hook, lab); draw_grid(static, p, cells, cell)
        if li > 0 or True:
            events.append((t, "whoosh"))
        n = int(solve * FPS)
        for k in range(n):
            el = k / FPS
            left = solve - el
            if k % FPS == 0:
                events.append((t + el, "tick" if (k // FPS) % 2 == 0 else "tock"))
            f = static.copy(); timer(f, left / solve, left); frames.append(f)
        t += solve
        events.append((t, "ding"))
        rv = base(); chrome(rv, spec["number"], hook, lab); draw_grid(rv, p, cells, cell, highlight=odd, dim=True)
        footer(rv, "DID YOU FIND IT?", f"Row {odd // p['cols'] + 1}, column {odd % p['cols'] + 1}")
        for k in range(int(reveal_dur * FPS)):
            frames.append(rv)
        t += reveal_dur
    # end card
    end = base(); d = ImageDraw.Draw(end)
    centered(d, 560, "BLINK TEST", font(FONT_XB, 110), GOLD)
    centered(d, 700, f"#{spec['number']}", font(FONT_XB, 160), WHITE)
    centered(d, 960, "New test every day", font(FONT_B, 72), WHITE)
    centered(d, 1060, "Comment your time below", font(FONT_M, 60), MUTED)
    d.rounded_rectangle([200, 1240, 880, 1380], radius=70, fill=RED)
    centered(d, 1272, "SUBSCRIBE", font(FONT_XB, 78), WHITE)
    end_dur = 1.7
    for k in range(int(end_dur * FPS)):
        frames.append(end)
    t += end_dur

    wav = out_dir / f"{spec['id']}.wav"
    build_audio(events, t, wav)
    mp4 = out_dir / f"{spec['id']}.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(mp4)]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    last = None; lastb = None
    for f in frames:
        if f is not last:
            lastb = f.convert("RGB").tobytes(); last = f
        pr.stdin.write(lastb)
    pr.stdin.close(); pr.wait()
    # preview stills: puzzle and reveal of first level
    frames[int(1 * FPS)].convert("RGB").save(out_dir / f"{spec['id']}_q.png")
    frames[int(solve * FPS) + 5].convert("RGB").save(out_dir / f"{spec['id']}_a.png")
    wav.unlink()
    return {"file": str(mp4), "duration": round(t, 2), "answers": answers}

if __name__ == "__main__":
    specs = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    res = {}
    for s in specs:
        res[s["id"]] = render(s, out)
        print(s["id"], res[s["id"]]["duration"], res[s["id"]]["answers"])
    json.dump(res, open(Path(out) / "results.json", "w"), indent=1)
