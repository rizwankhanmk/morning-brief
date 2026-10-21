#!/usr/bin/env python3
"""
Draws the six animated weather icons used in the brief header as GIFs.

    python3 assets/weather/make_icons.py

Original line-free, flat drawings in the brief's own palette. 96x96 px,
12 frames, 100 ms each, looping. Rendered at 4x and downsampled so edges
stay smooth. Requires Pillow.
"""
import math
import pathlib

from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parent
SCALE = 4
SIZE = 96
S = SIZE * SCALE
FRAMES = 12
DURATION = 100

WHITE = (255, 255, 255)
AMBER = (242, 176, 53)
CLOUD = (201, 201, 197)
CLOUD_DARK = (150, 150, 146)
BLUE = (0, 113, 227)
HAZE = (180, 179, 168)


def canvas():
    im = Image.new("RGB", (S, S), WHITE)
    return im, ImageDraw.Draw(im)


def sun(d, cx, cy, r, angle, rays=True, colour=AMBER, ray_len=None):
    ray_len = ray_len or r * 0.75
    if rays:
        for i in range(8):
            a = math.radians(angle + i * 45)
            x1 = cx + math.cos(a) * (r * 1.35)
            y1 = cy + math.sin(a) * (r * 1.35)
            x2 = cx + math.cos(a) * (r * 1.35 + ray_len)
            y2 = cy + math.sin(a) * (r * 1.35 + ray_len)
            d.line([(x1, y1), (x2, y2)], fill=colour, width=int(r * 0.28))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour)


def cloud(d, cx, cy, w, colour=CLOUD):
    # three lobes on a flat base
    h = w * 0.55
    base = [cx - w / 2, cy - h * 0.1, cx + w / 2, cy + h * 0.5]
    d.rounded_rectangle(base, radius=h * 0.3, fill=colour)
    d.ellipse([cx - w * 0.42, cy - h * 0.35, cx - w * 0.02, cy + h * 0.15], fill=colour)
    d.ellipse([cx - w * 0.18, cy - h * 0.75, cx + w * 0.28, cy + h * 0.1], fill=colour)
    d.ellipse([cx + w * 0.08, cy - h * 0.45, cx + w * 0.46, cy + h * 0.15], fill=colour)


def drop(d, x, y, r, colour=BLUE):
    d.ellipse([x - r, y - r, x + r, y + r], fill=colour)
    d.polygon([(x - r * 0.95, y - r * 0.3), (x + r * 0.95, y - r * 0.3), (x, y - r * 2.1)], fill=colour)


def bolt(d, cx, cy, h, colour=AMBER):
    w = h * 0.45
    pts = [
        (cx + w * 0.15, cy - h / 2), (cx - w * 0.45, cy + h * 0.08), (cx + w * 0.02, cy + h * 0.08),
        (cx - w * 0.2, cy + h / 2), (cx + w * 0.5, cy - h * 0.12), (cx + w * 0.04, cy - h * 0.12),
    ]
    d.polygon(pts, fill=colour)


def wave(d, y, phase, colour=HAZE, amp=None, width=None):
    amp = amp or S * 0.025
    width = width or int(S * 0.045)
    pts = []
    for i in range(0, S + 1, S // 48):
        x = i
        pts.append((x, y + math.sin((x / S) * 2 * math.pi * 1.5 + phase) * amp))
    d.line(pts, fill=colour, width=width, joint="curve")


def save(name, frames):
    small = [f.resize((SIZE, SIZE), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    small[0].save(OUT / f"{name}.gif", save_all=True, append_images=small[1:], duration=DURATION, loop=0, optimize=False)
    print("wrote", name + ".gif")


def make_sun():
    frames = []
    for f in range(FRAMES):
        im, d = canvas()
        pulse = 1 + 0.08 * math.sin(f / FRAMES * 2 * math.pi)
        sun(d, S / 2, S / 2, S * 0.2, angle=f * 45 / FRAMES, ray_len=S * 0.14 * pulse)
        frames.append(im)
    save("sun", frames)


def make_partly_cloudy():
    frames = []
    for f in range(FRAMES):
        im, d = canvas()
        sun(d, S * 0.36, S * 0.36, S * 0.16, angle=f * 45 / FRAMES, ray_len=S * 0.1)
        dx = math.sin(f / FRAMES * 2 * math.pi) * S * 0.03
        cloud(d, S * 0.58 + dx, S * 0.62, S * 0.62)
        frames.append(im)
    save("partly-cloudy", frames)


def make_cloudy():
    frames = []
    for f in range(FRAMES):
        im, d = canvas()
        dx = math.sin(f / FRAMES * 2 * math.pi) * S * 0.03
        cloud(d, S * 0.62 - dx, S * 0.4, S * 0.5, colour=CLOUD_DARK)
        cloud(d, S * 0.48 + dx, S * 0.6, S * 0.7)
        frames.append(im)
    save("cloudy", frames)


def make_rain():
    frames = []
    for f in range(FRAMES):
        im, d = canvas()
        cloud(d, S * 0.5, S * 0.4, S * 0.66)
        for i, x in enumerate((0.34, 0.5, 0.66)):
            t = ((f / FRAMES) + i * 0.33) % 1.0
            y = S * 0.62 + t * S * 0.3
            fade = 1.0 if t < 0.75 else 0.0
            if fade:
                drop(d, S * x, y, S * 0.045)
        frames.append(im)
    save("rain", frames)


def make_thunder():
    frames = []
    for f in range(FRAMES):
        im, d = canvas()
        cloud(d, S * 0.5, S * 0.38, S * 0.68, colour=CLOUD_DARK)
        if f in (2, 3, 4, 8, 9):
            bolt(d, S * 0.5, S * 0.7, S * 0.42)
        for i, x in enumerate((0.3, 0.7)):
            t = ((f / FRAMES) + i * 0.5) % 1.0
            if t < 0.7:
                drop(d, S * x, S * 0.62 + t * S * 0.28, S * 0.04)
        frames.append(im)
    save("thunder", frames)


def make_haze():
    frames = []
    for f in range(FRAMES):
        im, d = canvas()
        sun(d, S / 2, S * 0.4, S * 0.18, angle=0, rays=False, colour=(242, 196, 120))
        ph = f / FRAMES * 2 * math.pi
        wave(d, S * 0.6, ph)
        wave(d, S * 0.72, ph + 1.2)
        wave(d, S * 0.84, ph + 2.4)
        frames.append(im)
    save("haze", frames)


if __name__ == "__main__":
    make_sun()
    make_partly_cloudy()
    make_cloudy()
    make_rain()
    make_thunder()
    make_haze()
