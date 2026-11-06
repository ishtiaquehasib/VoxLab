"""Render Tutorial 01, 1920x1080@30fps, PIL frames -> ffmpeg rawvideo pipe.
Segments timed to real narration blocks (22.528s total, no padding):
  b1 0.00-4.12, b2 4.52-8.64, b3 9.04-12.60, b4 13.00-17.86, b5 18.26-22.53
No real UI screenshots: text step cards + logo, labelled Demo.
"""
import subprocess, textwrap
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
NAVY = (5, 8, 31)
CYAN, BLUE, PURPLE = (0, 212, 255), (72, 104, 216), (139, 92, 246)
WHITE, LIGHT = (255, 255, 255), (190, 205, 235)
LOGO = "/home/hatch/workspace/voice-studio/assets/voxlab-logo.png"
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJAVU_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BENGALI = "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf"

def font(path, size):
    return ImageFont.truetype(path, size)

def center(draw, y, text, f, color=WHITE):
    box = draw.textbbox((0, 0), text, font=f)
    w = box[2] - box[0]
    draw.text(((W - w) // 2, y), text, font=f, fill=color)
    return y + (box[3] - box[1]) + 20

def wrap_center(draw, y, text, f, max_w=1500, color=WHITE, line_gap=18):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if draw.textlength(trial, font=f) <= max_w:
            cur = trial
        else:
            lines.append(cur); cur = wd
    if cur:
        lines.append(cur)
    for line in lines:
        y = center(draw, y, line, f, color)
        y += line_gap
    return y

steps = [
    ("STEP 1  ·  OPEN CLONE", "Cloning your own voice in VoxLab\nis easy. First, go to Clone."),
    ("STEP 2  ·  UPLOAD OR RECORD", "Upload a clear 30-second voice\nsample, or record with your mic."),
    ("STEP 3  ·  TYPE AND SELECT", "Type the text you want spoken,\nand select your cloned voice."),
    ("STEP 4  ·  GENERATE AND DOWNLOAD", "Press Generate. Play it back,\nand download it if you like it."),
    ("VOXLAB CLONE  ·  DONE", "That is VoxLab Clone.\nNext tutorial: dictation."),
]
# (start, end) from real narration incl. 0.4s gaps
bounds = [(0.00, 4.12), (4.52, 8.64), (9.04, 12.60), (13.00, 17.86), (18.26, 22.53)]
total = 22.528
logo = Image.open(LOGO).convert("RGBA")
logo.thumbnail((220, 220))

def frame_for(t):
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    # gradient accent bar
    for x in range(W):
        r = int(CYAN[0] + (PURPLE[0] - CYAN[0]) * x / W)
        g = int(CYAN[1] + (PURPLE[1] - CYAN[1]) * x / W)
        b = int(CYAN[2] + (PURPLE[2] - CYAN[2]) * x / W)
        d.line([(x, 0), (x, 14)], fill=(r, g, b))
    img.paste(logo, ((W - 220) // 2, 70), logo)
    idx = next((i for i, (s, e) in enumerate(bounds) if s <= t < e), 4)
    head, body = steps[idx]
    y = 330
    y = center(d, y, "VoxLab", font(DEJAVU, 72), CYAN)
    y = center(d, y, head, font(DEJAVU, 44), LIGHT) + 30
    # body lines (explicit \n)
    for line in body.split("\n"):
        y = center(d, y, line, font(DEJAVU, 56))
    y += 40
    y = center(d, y, "নিজের কণ্ঠ ক্লোন করুন", font(BENGALI, 48), LIGHT) + 30
    y = center(d, y, "Demo — UI screenshots pending", font(DEJAVU_R, 32), (255, 200, 80))
    center(d, H - 110, "Use your own voice, or a voice you have permission to use.",
           font(DEJAVU_R, 30), LIGHT)
    # progress dots
    for i in range(5):
        cx = W // 2 - 100 + i * 50
        d.ellipse([cx - 12, H - 55, cx + 12, H - 31],
                  fill=CYAN if i == idx else (60, 70, 110))
    return img

cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
       "-r", str(FPS), "-i", "-", "-i",
       "/home/hatch/workspace/voice-studio/tutorials/tutorial-01-clone-narration.wav",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "24000",
       "-shortest",
       "/home/hatch/workspace/voice-studio/tutorials/tutorial-01-clone.mp4"]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
nframes = int(total * FPS)
for fi in range(nframes):
    t = fi / FPS
    proc.stdin.write(frame_for(t).tobytes())
proc.stdin.close()
out = proc.stdout.read().decode(errors="replace")
print(out[-2000:])
print("frames:", nframes, "rc:", proc.returncode)
