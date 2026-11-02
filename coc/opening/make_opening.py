"""Chain of Custody case-study opening (original homage to a cold-open narration style).
Usage: python3 make_opening.py <vo.m4a> <outdir>
Outputs opening-16x9.mp4 (1920x1080) and opening-4x5.mp4 (1080x1350), 25 fps, AAC 48 kHz mono.
"""
import sys, os, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, "/home/claude/tts")
import render_coc as rc  # reuse the brand fonts

VO, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
SR, FPS = 48000, 25

# Sentence cut points (silence midpoints in the Clipchamp take) and extra pauses for a measured delivery.
CUTS = [0.0, 6.20, 8.80, 11.96, 13.92]
SPEECH_END = [5.93, 8.52, 11.70, 13.51]   # end of speech inside each piece (source time)
LEAD, GAP, TAIL = 0.6, 0.7, 3.0
LINES = [
    "In supply chain assurance, every part,\nevery payment and every promise\npasses through a chain of custody.",
    "Most of the time, the chain holds.",
    "When it breaks, the official reports\ntell us how.",
    "These are the case studies.",
]

def run(cmd):
    subprocess.run(cmd, check=True)

# ---------- audio ----------
raw = os.path.join(OUT, "vo_raw.wav")
run(["ffmpeg", "-v", "error", "-y", "-i", VO, "-ac", "1", "-ar", str(SR), raw])
with wave.open(raw) as w:
    vo = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

pieces, starts, t = [], [], LEAD
for i in range(4):
    a, b = int(CUTS[i] * SR), int(CUTS[i + 1] * SR)
    seg = vo[a:b]
    starts.append(t)
    pieces.append(seg)
    t += len(seg) / SR + (GAP if i < 3 else 0)
d_last_speech = starts[3] + (SPEECH_END[3] - CUTS[3])   # moment the last word ends
CARD_T = d_last_speech + 0.15                            # hard cut to title card
TOTAL = CARD_T + TAIL

voice = np.zeros(int(TOTAL * SR), np.float32)
for s, seg in zip(starts, pieces):
    i = int(s * SR); voice[i:i + len(seg)] += seg

# Original sting: a low hit plus a padlock-style metallic clunk (synthesised, no third-party audio).
def sting(sr=SR):
    n = int(2.6 * sr); tt = np.arange(n) / sr
    low = 0.9 * np.sin(2 * np.pi * 52 * tt) * np.exp(-tt * 2.6)
    low += 0.35 * np.sin(2 * np.pi * 104 * tt) * np.exp(-tt * 4.0)
    rng = np.random.default_rng(7)
    thump = rng.normal(0, 1, n) * np.exp(-tt * 38) * 0.5
    thump = np.convolve(thump, np.ones(40) / 40, mode="same")          # low-passed noise
    clunk = np.zeros(n); off = int(0.045 * sr); tc = tt[: n - off]
    for f, a, dcy in [(612, .5, 22), (1187, .38, 30), (1893, .28, 38), (2741, .2, 46), (3960, .12, 60)]:
        clunk[off:] += a * np.sin(2 * np.pi * f * tc) * np.exp(-tc * dcy)
    click = np.zeros(n); click[off:off + 60] = rng.normal(0, 1, 60) * 0.6
    s = low + thump + 0.55 * clunk + click
    return (s / np.max(np.abs(s)) * 0.8).astype(np.float32)

st = sting(); i = int(CARD_T * SR)
mix = voice.copy(); mix[i:i + len(st)] += st[: len(mix) - i]
# soft low drone under the narration (very quiet), fading in and cut at the card
tt = np.arange(len(mix)) / SR
drone = 0.035 * (np.sin(2 * np.pi * 55 * tt) + 0.5 * np.sin(2 * np.pi * 82.4 * tt))
drone *= np.clip(tt / 2.0, 0, 1) * (tt < CARD_T)
mix += drone.astype(np.float32)
mix = mix / max(1.0, np.max(np.abs(mix)) / 0.95)
aud = os.path.join(OUT, "opening.wav")
with wave.open(aud, "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype(np.int16).tobytes())

# ---------- video ----------
WHITE, GREY = (242, 242, 242), (150, 150, 150)

def frame(W, H, tsec, scale):
    im = Image.new("RGB", (W, H), (0, 0, 0)); d = ImageDraw.Draw(im)
    if tsec >= CARD_T:
        f1 = rc.font("display", int(118 * scale), 600)
        f2 = rc.font("label", int(50 * scale), 500)
        cy = H // 2
        d.text((W / 2, cy - int(12 * scale)), "CHAIN OF CUSTODY", font=f1, fill=WHITE, anchor="mb")
        rw = int(360 * scale)
        d.rectangle(((W - rw) // 2, cy + int(14 * scale), (W + rw) // 2, cy + int(17 * scale)), fill=WHITE)
        d.text((W / 2, cy + int(44 * scale)), "C A S E   S T U D I E S", font=f2, fill=GREY, anchor="mt")
        return im
    # which sentence is showing, with fades
    k = None
    for j in range(4):
        end = starts[j + 1] - 0.05 if j < 3 else CARD_T
        if starts[j] - 0.15 <= tsec < end:
            k = j
    if k is None:
        return im
    end = starts[k + 1] - 0.05 if k < 3 else CARD_T
    a = min(1.0, (tsec - (starts[k] - 0.15)) / 0.45)
    if k < 3:
        a = min(a, max(0.0, (end - tsec) / 0.35))
    col = tuple(int(c * a) for c in WHITE)
    fb = rc.font("body", int(64 * scale), 400)
    lines = LINES[k].split("\n")
    lh = int(90 * scale)
    y0 = H // 2 - lh * len(lines) // 2
    for n, ln in enumerate(lines):
        wl = d.textlength(ln, font=fb)
        d.text(((W - wl) / 2, y0 + n * lh), ln, font=fb, fill=col)
    return im

def render(W, H, scale, name):
    fr_dir = os.path.join(OUT, f"fr_{name}"); os.makedirs(fr_dir, exist_ok=True)
    nfr = int(round(TOTAL * FPS))
    for n in range(nfr):
        frame(W, H, n / FPS, scale).save(os.path.join(fr_dir, f"{n:05d}.png"))
    out = os.path.join(OUT, f"opening-{name}.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(fr_dir, "%05d.png"), "-i", aud,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-ac", "1", "-shortest", out])
    return out

print("duration", round(TOTAL, 2), "card at", round(CARD_T, 2), "starts", [round(s, 2) for s in starts])
print(render(1920, 1080, 1.0, "16x9"))
print(render(1080, 1350, 0.82, "4x5"))
