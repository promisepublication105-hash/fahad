"""Renders a short product commercial from product photos + Bangla text.

Each scene shows one product photo as a floating "card" over a blurred,
colour-tinted copy of itself, with a slow push-in, and a Bangla caption that
slides up. Scenes cross-fade into each other and the ad ends on a brand card
(product name, tagline, call-to-action button).

Frames are drawn with Pillow (using the bundled Hind Siliguri font and the
RAQM layout engine, so Bangla conjuncts shape correctly) and piped straight
into ffmpeg, so no intermediate image files are written.
"""
import math
import os
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FPS = 30
XFADE = 0.45            # seconds of cross-fade between scenes
MIN_SCENE = 3.0         # seconds a scene lasts when it has no voiceover
END_CARD = 4.0          # seconds the closing brand card lasts (at least)
VOICE_DELAY = 0.35      # voice starts this long after its scene appears

ASPECTS = {
    "9:16": (1080, 1920),   # Reels / TikTok / Shorts / Stories
    "1:1": (1080, 1080),    # Feed post
    "16:9": (1920, 1080),   # YouTube / landscape
}

FONT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")
)

RGB = Tuple[int, int, int]


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONT_DIR, f"HindSiliguri-{weight}.ttf")
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)


def parse_color(value: str, default: RGB = (190, 92, 120)) -> RGB:
    v = (value or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except (ValueError, IndexError):
        return default


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _ease_out_back(x: float) -> float:
    x = max(0.0, min(1.0, x))
    c1 = 1.4
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def _cover(img: Image.Image, size: Tuple[int, int]) -> Image.Image:
    return ImageOps.fit(img, size, Image.LANCZOS, centering=(0.5, 0.5))


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
    lines: List[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            continue
        cur = words[0]
        for w in words[1:]:
            trial = f"{cur} {w}"
            if font.getlength(trial) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _fit_font(text: str, weight: str, start: int, min_size: int, max_w: int,
              max_lines: int) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
    """Largest font size (stepping down from `start`) at which `text` wraps to
    at most `max_lines` lines within `max_w`."""
    size = start
    while True:
        f = _font(weight, size)
        lines = _wrap(text, f, max_w)
        if len(lines) <= max_lines or size <= min_size:
            return f, _balance(text, f, lines, max_w)
        size -= 4


def _balance(text: str, font: ImageFont.FreeTypeFont, lines: List[str],
             max_w: int) -> List[str]:
    """Re-wrap to the narrowest width that keeps the same number of lines, so
    a caption doesn't end with a single orphaned word."""
    if len(lines) < 2:
        return lines
    lo, hi = max_w // 3, max_w
    best = lines
    while lo <= hi:
        mid = (lo + hi) // 2
        trial = _wrap(text, font, mid)
        if len(trial) <= len(lines):
            best, hi = trial, mid - 1
        else:
            lo = mid + 1
    return best


def _text_block(lines: List[str], font: ImageFont.FreeTypeFont, color: RGB,
                align: str = "center", shadow: bool = True,
                line_gap: float = 1.12) -> Image.Image:
    """Render lines to a tight RGBA image (with a soft drop shadow)."""
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * line_gap)
    widths = [int(math.ceil(font.getlength(l))) for l in lines] or [1]
    pad = max(12, font.size // 3)
    w = max(widths) + pad * 2
    h = lh * len(lines) + pad * 2
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    def draw_lines(img, fill, dy=0):
        d = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            lw = widths[i]
            if align == "center":
                x = (w - lw) / 2
            elif align == "left":
                x = pad
            else:
                x = w - pad - lw
            d.text((x, pad + i * lh + dy), line, font=font, fill=fill)

    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_lines(sh, (0, 0, 0, 170), dy=max(2, font.size // 22))
        sh = sh.filter(ImageFilter.GaussianBlur(max(3, font.size // 14)))
        layer.alpha_composite(sh)
    draw_lines(layer, color + (255,))
    return layer


def _rounded_card(img: Image.Image, max_w: int, max_h: int,
                  radius: int) -> Image.Image:
    """Fit `img` inside max_w x max_h, round its corners and give it a soft
    shadow. Returns RGBA with transparent padding around it."""
    img = img.convert("RGB")
    scale = min(max_w / img.width, max_h / img.height)
    cw, ch = max(1, int(img.width * scale)), max(1, int(img.height * scale))
    photo = img.resize((cw, ch), Image.LANCZOS)

    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), radius, fill=255)

    pad = max(30, radius)
    layer = Image.new("RGBA", (cw + pad * 2, ch + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("L", layer.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        (pad, pad + pad // 3, pad + cw, pad + ch + pad // 3), radius, fill=150
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(pad // 2))
    layer.paste((0, 0, 0, 255), (0, 0), shadow)
    # paste() replaced alpha with the shadow mask; restore proper alpha
    layer.putalpha(shadow)
    photo_rgba = photo.convert("RGBA")
    photo_rgba.putalpha(mask)
    layer.alpha_composite(photo_rgba, (pad, pad))
    return layer


def _place_scaled(canvas: Image.Image, layer: Image.Image, cx: float, cy: float,
                  s: float, opacity: float = 1.0) -> None:
    """Composite `layer` onto RGB `canvas`, scaled by `s` and centred on
    (cx, cy) with sub-pixel precision (avoids the jitter you get from
    resizing to whole-pixel sizes every frame)."""
    if opacity <= 0.01:
        return
    sw, sh = layer.width * s, layer.height * s
    x0, y0 = cx - sw / 2, cy - sh / 2
    px, py = math.floor(x0), math.floor(y0)
    fx, fy = x0 - px, y0 - py
    out_size = (int(math.ceil(sw + fx)) + 1, int(math.ceil(sh + fy)) + 1)
    inv = 1.0 / s
    out = layer.transform(
        out_size, Image.AFFINE, (inv, 0, -fx * inv, 0, inv, -fy * inv),
        resample=Image.BICUBIC,
    )
    alpha = out.getchannel("A")
    if opacity < 0.999:
        alpha = alpha.point(lambda v: int(v * opacity))
    canvas.paste(out.convert("RGB"), (px, py), alpha)


def _paste_fade(canvas: Image.Image, layer: Image.Image, x: int, y: int,
                opacity: float) -> None:
    if opacity <= 0.01:
        return
    alpha = layer.getchannel("A")
    if opacity < 0.999:
        alpha = alpha.point(lambda v: int(v * opacity))
    canvas.paste(layer.convert("RGB"), (int(x), int(y)), alpha)


# --------------------------------------------------------------------------
# layout per aspect ratio
# --------------------------------------------------------------------------

@dataclass
class Layout:
    W: int
    H: int
    card_box: Tuple[int, int, int, int]   # where the product photo sits
    text_box: Tuple[int, int, int, int]   # where captions sit
    text_align: str
    gradient: str                          # "bottom" or "right"


def _layout(aspect: str) -> Layout:
    W, H = ASPECTS.get(aspect, ASPECTS["9:16"])
    if aspect == "16:9":
        return Layout(W, H, (int(W * .05), int(H * .09), int(W * .50), int(H * .91)),
                      (int(W * .54), int(H * .12), int(W * .95), int(H * .88)),
                      "left", "right")
    if aspect == "1:1":
        return Layout(W, H, (int(W * .14), int(H * .05), int(W * .86), int(H * .62)),
                      (int(W * .06), int(H * .66), int(W * .94), int(H * .95)),
                      "center", "bottom")
    return Layout(W, H, (int(W * .08), int(H * .07), int(W * .92), int(H * .60)),
                  (int(W * .06), int(H * .64), int(W * .94), int(H * .93)),
                  "center", "bottom")


# --------------------------------------------------------------------------
# scenes
# --------------------------------------------------------------------------

@dataclass
class AdSpec:
    images: List[Image.Image]
    product_name: str
    lines: List[str]                 # one caption / voice line per scene
    tagline: str = ""
    cta: str = "এখনই অর্ডার করুন"
    contact: str = ""                # phone / page / website, shown on end card
    brand_color: RGB = (190, 92, 120)
    aspect: str = "9:16"
    voice_clips: List[Optional[object]] = field(default_factory=list)  # pydub segments
    end_voice: Optional[object] = None


class PhotoScene:
    def __init__(self, lay: Layout, img: Image.Image, caption: str,
                 title: Optional[str], brand: RGB, duration: float, index: int):
        self.duration = duration
        self.lay = lay
        W, H = lay.W, lay.H

        # background: blurred photo, tinted toward a dark brand colour,
        # oversized a bit so it can drift slowly
        self.bg_margin = int(max(W, H) * 0.04)
        big = _cover(img.convert("RGB"), (W + self.bg_margin * 2, H + self.bg_margin * 2))
        big = big.filter(ImageFilter.GaussianBlur(max(W, H) // 40))
        tint = Image.new("RGB", big.size, _mix(brand, (10, 10, 14), 0.55))
        big = Image.blend(big, tint, 0.45)
        grad = Image.new("L", big.size, 0)
        gd = ImageDraw.Draw(grad)
        if lay.gradient == "bottom":
            top = int(big.height * 0.50)
            for y in range(top, big.height):
                gd.line([(0, y), (big.width, y)],
                        fill=int(200 * ((y - top) / (big.height - top)) ** 1.2))
        else:
            left = int(big.width * 0.42)
            for x in range(left, big.width):
                gd.line([(x, 0), (x, big.height)],
                        fill=int(190 * ((x - left) / (big.width - left)) ** 1.1))
        big.paste((0, 0, 0), (0, 0), grad)
        self.bg = big

        # product card
        x0, y0, x1, y1 = lay.card_box
        self.card = _rounded_card(img, int((x1 - x0) * 0.9), int((y1 - y0) * 0.9),
                                  radius=max(24, W // 30))
        self.card_c = ((x0 + x1) / 2, (y0 + y1) / 2)
        self.drift = 1 if index % 2 == 0 else -1

        # caption (+ optional title above it)
        tx0, ty0, tx1, ty1 = lay.text_box
        tw, th = tx1 - tx0, ty1 - ty0
        base = W if lay.gradient == "bottom" else int(W * 0.55)
        k = 1.0
        while True:  # shrink text until it fits the caption area's height
            self.title_img = None
            if title:
                tf, tl = _fit_font(title, "Bold", int(base * 0.095 * k), 28, tw, 2)
                self.title_img = _text_block(tl, tf, (255, 255, 255), lay.text_align)
            cf, cl = _fit_font(caption, "Bold", int(base * 0.068 * k), 24, tw,
                               3 if title else 4)
            self.cap_img = _text_block(cl, cf, (255, 255, 255), lay.text_align)
            total_h = self.cap_img.height + (self.title_img.height if self.title_img else 0)
            if total_h <= th or k < 0.4:
                break
            k -= 0.06
        self.text_top = ty0 + max(0, (th - total_h) // 2)

    def _x_for(self, img: Image.Image) -> int:
        tx0, _, tx1, _ = self.lay.text_box
        if self.lay.text_align == "left":
            return tx0 - 12
        return tx0 + ((tx1 - tx0) - img.width) // 2

    def frame(self, t: float) -> Image.Image:
        W, H = self.lay.W, self.lay.H
        p = t / self.duration
        m = self.bg_margin
        ox = int(m + self.drift * m * 0.8 * (p - 0.5))
        canvas = self.bg.crop((ox, m, ox + W, m + H))

        enter = _ease_out(t / 0.7)
        s = 0.94 + 0.06 * enter + 0.045 * p
        cx = self.card_c[0] + self.drift * W * 0.012 * (p - 0.5)
        cy = self.card_c[1] + (1 - enter) * H * 0.02
        _place_scaled(canvas, self.card, cx, cy, s, opacity=min(1.0, 0.7 + enter))

        y = self.text_top
        if self.title_img is not None:
            k = _ease_out((t - 0.15) / 0.55)
            _paste_fade(canvas, self.title_img, self._x_for(self.title_img),
                        y + (1 - k) * 50, k)
            y += self.title_img.height
        k = _ease_out((t - 0.35) / 0.55)
        _paste_fade(canvas, self.cap_img, self._x_for(self.cap_img),
                    y + (1 - k) * 50, k)
        return canvas


class EndCard:
    def __init__(self, lay: Layout, img: Image.Image, spec: AdSpec, duration: float):
        self.duration = duration
        self.lay = lay
        W, H = lay.W, lay.H
        brand = spec.brand_color

        # vertical gradient background in the brand colour
        top, bottom = _mix(brand, (255, 255, 255), 0.12), _mix(brand, (8, 8, 12), 0.55)
        bg = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(bg)
        for y in range(H):
            d.line([(0, y), (W, y)], fill=_mix(top, bottom, y / H))
        # soft light behind the product
        glow = Image.new("L", (W, H), 0)
        gr = int(min(W, H) * 0.42)
        landscape = W > H
        gcx, gcy = (int(W * 0.28), H // 2) if landscape else (W // 2, int(H * (0.33 if H > W else 0.25)))
        ImageDraw.Draw(glow).ellipse((gcx - gr, gcy - gr, gcx + gr, gcy + gr), fill=110)
        glow = glow.filter(ImageFilter.GaussianBlur(gr // 2))
        bg.paste((255, 255, 255), (0, 0), glow)
        self.bg = bg

        if landscape:
            card_w, card_h = int(W * 0.40), int(H * 0.74)
            self.card_c = (gcx, gcy)
            col_x0, col_x1 = int(W * 0.54), int(W * 0.95)
        else:
            card_w, card_h = int(W * 0.62), int(H * (0.40 if H > W else 0.36))
            self.card_c = (gcx, gcy)
            col_x0, col_x1 = int(W * 0.07), int(W * 0.93)
        self.card = _rounded_card(img, card_w, card_h, radius=max(24, W // 30))

        self.card_h = card_h
        self.align, self.col_x0, self.col_x1 = ("left" if landscape else "center"), col_x0, col_x1
        avail = H * 0.9 if landscape else H - (gcy + card_h // 2 + 20) - H * 0.03
        k = 1.0
        while True:  # shrink the text column until it fits under the product
            stack_h = self._build_text(spec, brand, landscape, k)
            if stack_h <= avail or k < 0.4:
                break
            k -= 0.06
        if landscape:
            self.col_top = (H - stack_h) // 2
        else:
            card_bottom = gcy + card_h // 2 + 20
            self.col_top = card_bottom + max(0, (H - card_bottom - stack_h) // 2)

    def _build_text(self, spec: AdSpec, brand: RGB, landscape: bool, k: float) -> int:
        W = self.lay.W
        colw = self.col_x1 - self.col_x0
        base = int((W if not landscape else W * 0.55) * k)
        align = self.align
        nf, nl = _fit_font(spec.product_name, "Bold", int(base * 0.10), 30, colw, 2)
        self.name_img = _text_block(nl, nf, (255, 255, 255), align)
        self.tag_img = None
        if spec.tagline:
            tf, tl = _fit_font(spec.tagline, "SemiBold", int(base * 0.055), 22, colw, 2)
            self.tag_img = _text_block(tl, tf, (255, 255, 255), align)

        # CTA pill button
        cf = _font("Bold", int(base * 0.05))
        tw = int(cf.getlength(spec.cta))
        asc, desc = cf.getmetrics()
        bw, bh = tw + int(cf.size * 1.6), int((asc + desc) * 1.45)
        btn = Image.new("RGBA", (bw + 40, bh + 40), (0, 0, 0, 0))
        sh = Image.new("L", btn.size, 0)
        ImageDraw.Draw(sh).rounded_rectangle((20, 26, 20 + bw, 26 + bh), bh // 2, fill=120)
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        btn.putalpha(sh)
        bd = ImageDraw.Draw(btn)
        bd.rounded_rectangle((20, 20, 20 + bw, 20 + bh), bh // 2, fill=(255, 255, 255, 255))
        bd.text((20 + (bw - tw) / 2, 20 + (bh - (asc + desc)) / 2), spec.cta,
                font=cf, fill=_mix(brand, (0, 0, 0), 0.25) + (255,))
        self.btn = btn

        self.contact_img = None
        if spec.contact:
            ff, fl = _fit_font(spec.contact, "Regular", int(base * 0.04), 20, colw, 2)
            self.contact_img = _text_block(fl, ff, (255, 255, 255), align, shadow=False)

        # total height of the text column
        blocks = [b for b in (self.name_img, self.tag_img) if b is not None]
        stack_h = sum(b.height for b in blocks) + self.btn.height + 20
        if self.contact_img is not None:
            stack_h += self.contact_img.height
        return stack_h

    def _x(self, img: Image.Image) -> float:
        if self.align == "left":
            return self.col_x0 - 12
        return self.col_x0 + ((self.col_x1 - self.col_x0) - img.width) / 2

    def frame(self, t: float) -> Image.Image:
        canvas = self.bg.copy()
        k = _ease_out_back(t / 0.7)
        _place_scaled(canvas, self.card, self.card_c[0], self.card_c[1],
                      0.82 + 0.18 * k + 0.02 * (t / self.duration),
                      opacity=min(1.0, t / 0.3 + 0.2))
        y = self.col_top
        delay = 0.25
        for img in (self.name_img, self.tag_img):
            if img is None:
                continue
            e = _ease_out((t - delay) / 0.5)
            _paste_fade(canvas, img, self._x(img), y + (1 - e) * 40, e)
            y += img.height
            delay += 0.2
        y += 20
        e = _ease_out_back((t - delay) / 0.5)
        pulse = 1 + 0.03 * math.sin(max(0.0, t - delay - 0.5) * 2 * math.pi / 1.4)
        if e > 0:
            bx = self._x(self.btn) + self.btn.width / 2
            _place_scaled(canvas, self.btn, bx, y + self.btn.height / 2,
                          max(0.05, (0.6 + 0.4 * e) * pulse), opacity=min(1.0, e))
        y += self.btn.height
        if self.contact_img is not None:
            e = _ease_out((t - delay - 0.3) / 0.5)
            _paste_fade(canvas, self.contact_img, self._x(self.contact_img), y, e)
        return canvas


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------

def make_soft_music(duration_s: float, out_path: str) -> str:
    """Generate a gentle, royalty-free ambient pad (a slow four-chord swell)
    with ffmpeg, for when the user doesn't upload their own music."""
    # Cmaj7 - Am7 - Fmaj7 - G6, one chord every 4 s; each chord swells in and
    # out (sin envelope) so chord changes never click.
    chords = [
        (130.81, 261.63, 329.63, 392.00, 493.88),
        (110.00, 220.00, 261.63, 329.63, 392.00),
        (87.31, 174.61, 220.00, 261.63, 329.63),
        (98.00, 196.00, 246.94, 293.66, 329.63),
    ]
    k = "mod(floor(t/4),4)"

    def pick(i):
        f = [c[i] for c in chords]
        return f"if(eq({k},0),{f[0]},if(eq({k},1),{f[1]},if(eq({k},2),{f[2]},{f[3]})))"

    voices = []
    for i in range(5):
        amp = 0.30 if i == 0 else 0.16
        f = pick(i)
        voices.append(f"{amp}*sin(2*PI*{f}*t)")
        voices.append(f"{amp * 0.5}*sin(2*PI*{f}*1.004*t)")  # slight chorus
    env = "pow(sin(PI*mod(t,4)/4),1.5)"
    expr = f"0.32*{env}*({'+'.join(voices)})"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"aevalsrc='{expr}':s=44100:d={duration_s:.2f}",
         "-af", "lowpass=f=1800,aecho=0.8:0.7:120|240:0.35|0.2,"
                f"afade=t=in:d=1,afade=t=out:st={max(0.0, duration_s - 1.5):.2f}:d=1.5",
         "-ac", "2", out_path],
        check=True, capture_output=True,
    )
    return out_path


def build_audio(scene_starts: List[float], total_s: float, voices: List[Optional[object]],
                music_path: Optional[str], out_path: str) -> str:
    from pydub import AudioSegment, effects

    total_ms = int(total_s * 1000)
    track = AudioSegment.silent(duration=total_ms, frame_rate=44100).set_channels(2)
    has_voice = any(v is not None for v in voices)

    if music_path:
        music = AudioSegment.from_file(music_path).set_frame_rate(44100).set_channels(2)
        if len(music) > 0:
            while len(music) < total_ms:
                music += music
            music = music[:total_ms]
            music = effects.normalize(music) - (17 if has_voice else 6)
            music = music.fade_in(600).fade_out(1500)
            track = track.overlay(music)

    for start, clip in zip(scene_starts, voices):
        if clip is None:
            continue
        clip = effects.normalize(clip.set_frame_rate(44100).set_channels(2)) - 1
        track = track.overlay(clip, position=int((start + VOICE_DELAY) * 1000))

    track.export(out_path, format="wav")
    return out_path


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------

def render_ad(spec: AdSpec, out_path: str, work_dir: str, music_path: Optional[str],
              use_builtin_music: bool,
              on_progress: Optional[Callable[[float], None]] = None) -> str:
    lay = _layout(spec.aspect)
    if not spec.images:
        raise ValueError("At least one product photo is needed.")

    voices = list(spec.voice_clips) + [None] * (len(spec.lines) - len(spec.voice_clips))

    scenes = []
    for i, line in enumerate(spec.lines):
        img = spec.images[i % len(spec.images)]
        v = voices[i]
        dur = MIN_SCENE
        if v is not None:
            dur = max(MIN_SCENE, len(v) / 1000 + VOICE_DELAY + 0.7)
        title = spec.product_name if i == 0 else None
        scenes.append(PhotoScene(lay, img, line, title, spec.brand_color, dur, i))

    end_dur = END_CARD
    if spec.end_voice is not None:
        end_dur = max(END_CARD, len(spec.end_voice) / 1000 + VOICE_DELAY + 1.0)
    scenes.append(EndCard(lay, spec.images[0], spec, end_dur))
    voices = voices[:len(spec.lines)] + [spec.end_voice]

    starts, t = [], 0.0
    for sc in scenes:
        starts.append(t)
        t += sc.duration - XFADE
    total = starts[-1] + scenes[-1].duration
    n_frames = int(round(total * FPS))

    # audio first (fast), then stream video frames into ffmpeg with it
    music = music_path
    if not music and use_builtin_music:
        music = make_soft_music(total, os.path.join(work_dir, "music.wav"))
    audio_path = build_audio(starts, total, voices, music,
                             os.path.join(work_dir, "ad_audio.wav"))

    log_path = os.path.join(work_dir, "ffmpeg_render.log")
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(
            ["ffmpeg", "-y",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{lay.W}x{lay.H}",
             "-r", str(FPS), "-i", "-",
             "-i", audio_path,
             "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-shortest", "-movflags", "+faststart", out_path],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
        )
        try:
            for n in range(n_frames):
                ft = n / FPS
                active = [(i, sc) for i, sc in enumerate(scenes)
                          if starts[i] <= ft < starts[i] + sc.duration]
                if not active:
                    active = [(len(scenes) - 1, scenes[-1])]
                i, sc = active[0]
                frame = sc.frame(ft - starts[i])
                if len(active) > 1:
                    j, nxt = active[1]
                    mix = _ease_out((ft - starts[j]) / XFADE)
                    frame = Image.blend(frame, nxt.frame(ft - starts[j]), mix)
                proc.stdin.write(frame.tobytes())
                if on_progress and n % 15 == 0:
                    on_progress(n / n_frames)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        if proc.wait() != 0:
            with open(log_path, "rb") as f:
                tail = f.read()[-1500:].decode(errors="replace")
            raise RuntimeError(f"ffmpeg failed while encoding the ad:\n{tail}")
    return out_path
