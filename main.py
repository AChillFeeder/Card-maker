import base64
import threading
from html import escape
from pathlib import Path
from string import Template

from flask import Flask, Response, jsonify, render_template, request

from playwright.sync_api import (
    sync_playwright,
)

# ---------- Config ----------
MAX_CONCURRENCY = int(__import__("os").environ.get("MAX_CONCURRENCY", "4"))
DEFAULT_W, DEFAULT_H, DEFAULT_DPR = 384, 576, 3
DEFAULT_TIMEOUT = 15_000
# ----------------------------

_sem = threading.Semaphore(MAX_CONCURRENCY)
_sync_lock = threading.Lock()
app = Flask(__name__, template_folder="templates", static_folder="static")

BASE_DIR = Path(__file__).resolve().parent
CARD_TEMPLATE_DIR = BASE_DIR / "card_template"
CARD_HTML_PATH = CARD_TEMPLATE_DIR / "card.html"
CARD_CSS_PATH = CARD_TEMPLATE_DIR / "card.css"

PLAYSTYLE_ICONS = {
    "rushdown": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M12 2 3 12l9 10 9-10-9-10zm0 4.8L17.2 12 12 17.2 6.8 12 12 6.8z"/></svg>',
    "zoning": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M4 18h16l-8-12-8 12zm3.2-2 4.8-7.2 4.8 7.2H7.2z"/></svg>',
    "mixups": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M12 3c-2.5 2.9-6.2 4.4-6.2 8.4 0 3.2 2.6 5.8 6.2 5.8s6.2-2.6 6.2-5.8C18.2 6.7 14.5 5.2 12 3zm.2 5.2c1.1 1.2 2 2.5 2 3.7 0 1.5-1.1 2.6-2.2 2.6s-2.2-1.1-2.2-2.6c0-1.2.9-2.5 2.4-3.7zM8 19c2.2 1.5 5.8 1.5 8 0-.7 1.8-2.4 3-4 3s-3.3-1.2-4-3z"/></svg>',
    "grappler": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M12 4a8 8 0 1 0 8 8h-2a6 6 0 1 1-6-6V4zm0 4a4 4 0 1 0 4 4h-2a2 2 0 1 1-2-2V8zm9-6-5 5 1.4 1.4L22.4 3 21 2z"/></svg>',
    "mix": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M12 6.3C10.3 3.8 6.7 3.4 4.7 5.6c-1.8 2-1.4 5.2.9 7.5L12 20l6.4-6.9c2.3-2.3 2.7-5.5.9-7.5-2-2.2-5.6-1.8-7.3.7z"/></svg>',
}
DEFAULT_ICON_KEY = "rushdown"


def _hex_to_rgba(value: str, alpha: float) -> str:
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return f"rgba(250, 188, 80, {alpha})"
    try:
        r = int(raw[0:2], 16)
        g = int(raw[2:4], 16)
        b = int(raw[4:6], 16)
    except ValueError:
        return f"rgba(250, 188, 80, {alpha})"
    return f"rgba({r}, {g}, {b}, {alpha})"


def _clean_text(value: str | None, fallback: str, max_len: int, allow_empty: bool = False) -> str:
    if value is None:
        text = fallback
    else:
        text = value.strip()
        if not text:
            if allow_empty:
                return ""
            text = fallback
    return escape(text[:max_len])


def _render_sync(
    width: int,
    height: int,
    dpr: float,
    fmt: str,
    transparent: bool,
    document: str,
) -> bytes:
    """Perform the Playwright render using a fresh browser for the call."""
    with _sync_lock:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--font-render-hinting=medium",
                    "--enable-font-antialiasing",
                ],
            )
            context = None
            try:
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=dpr,
                )
                page = context.new_page()
                page.set_default_timeout(DEFAULT_TIMEOUT)
                page.emulate_media(media="screen")

                page.set_content(document, wait_until="networkidle")

                try:
                    page.evaluate("async () => { if (document.fonts) await document.fonts.ready; }")
                except Exception:
                    pass

                if fmt == "pdf":
                    return page.pdf(
                        width=f"{width}px",
                        height=f"{height}px",
                        print_background=True,
                        page_ranges="1",
                    )

                clip = {"x": 0, "y": 0, "width": width, "height": height}
                return page.screenshot(
                    type=fmt,
                    quality=95 if fmt == "jpeg" else None,
                    omit_background=transparent,
                    clip=clip,
                )
            finally:
                if context is not None:
                    context.close()
                browser.close()


def _as_data_url(storage) -> str | None:
    if not storage:
        return None
    data = storage.read()
    storage.seek(0)  # reset so Flask can reuse the stream if needed
    mime = storage.mimetype or "image/png"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/api/render-card", methods=["POST"])
def render_card():
    form = request.form
    files = request.files

    width = int(form.get("width", DEFAULT_W))
    height = int(form.get("height", DEFAULT_H))
    dpr = float(form.get("dpr", DEFAULT_DPR))
    fmt = (form.get("format") or "png").lower()
    transparent = form.get("transparent") in {"on", "true", "1"}
    border_color = form.get("borderColor", "#d4af37")
    border_width = int(form.get("borderWidth", 12))
    radius = int(form.get("radius", 28))
    bg_blur = int(form.get("bgBlur", 4))
    main_scale = int(form.get("mainScale", 92))
    main_offset_x = int(form.get("mainOffsetX", 0))
    main_offset_y = int(form.get("mainOffsetY", 0))

    bg_file = files.get("bgFile")
    main_file = files.get("mainFile")

    if not bg_file or not main_file:
        return jsonify({"error": "Both background and main images are required."}), 400

    bg_url = _as_data_url(bg_file)
    main_url = _as_data_url(main_file)

    frame_pad = border_width
    card_radius = radius
    accent_soft = _hex_to_rgba(border_color, 0.9)
    main_scale_value = max(10, min(300, main_scale)) / 100

    player_name = _clean_text(form.get("playerName"), "Faker", 40)
    team_name = _clean_text(form.get("teamName"), "T1", 28, allow_empty=True)
    champion_name = _clean_text(form.get("favoriteChampion"), "Neeko", 32)
    playstyle_label = _clean_text(form.get("playstyle"), "Mid", 16)
    side_tag = _clean_text(form.get("sideTag"), "2023 LCK SUMMER 24", 48, allow_empty=True)
    badge_text = _clean_text(form.get("badgeText"), "23 SUM", 20, allow_empty=True)
    rating_text = _clean_text(form.get("cardRank"), "114", 8, allow_empty=True)
    corner_label = _clean_text(form.get("cornerLabel"), "", 6, allow_empty=True)

    icon_key = (form.get("playstyleIcon") or DEFAULT_ICON_KEY).lower()
    icon_svg = PLAYSTYLE_ICONS.get(icon_key, PLAYSTYLE_ICONS[DEFAULT_ICON_KEY])

    side_tag_block = f'<div class="side-tag">{side_tag}</div>' if side_tag else ""

    try:
        template_html = CARD_HTML_PATH.read_text(encoding="utf-8")
        template_css = CARD_CSS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        missing = Path(exc.filename).name if exc.filename else "unknown file"
        return jsonify({"error": f"Card template asset missing: {missing}"}), 500

    card_html = Template(template_html).safe_substitute({
        "BACKGROUND_URL": bg_url,
        "MAIN_URL": main_url,
        "RATING_TEXT": rating_text,
        "CORNER_TEXT": corner_label,
        "SIDE_TAG_BLOCK": side_tag_block,
        "TEAM_NAME": team_name,
        "PLAYER_NAME": player_name,
        "CHAMPION_NAME": champion_name,
        "PLAYSTYLE_ICON": icon_svg,
        "PLAYSTYLE_LABEL": playstyle_label,
        "BADGE_TEXT": badge_text,
    })

    dynamic_vars = f"""
    <style id="card-dynamic-vars">
      .card-root {{
        --card-width-dyn:{width}px;
        --card-height-dyn:{height}px;
        --frame-pad-dyn:{frame_pad}px;
        --card-radius-dyn:{card_radius}px;
        --accent-color-dyn:{border_color};
        --accent-soft-dyn:{accent_soft};
        --bg-blur-dyn:{bg_blur}px;
        --main-scale-dyn:{main_scale_value};
        --offset-x-dyn:{main_offset_x}px;
        --offset-y-dyn:{main_offset_y}px;
      }}
    </style>
    """

    inline_doc = card_html.replace(
        '<link rel="stylesheet" href="card.css">',
        f"<style>{template_css}</style>{dynamic_vars}",
        1
    )

    media = "application/pdf" if fmt == "pdf" else f"image/{fmt}"

    with _sem:
        data = _render_sync(
            width,
            height,
            dpr,
            fmt,
            transparent,
            inline_doc,
        )

    return Response(data, mimetype=media)


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"ok": True})


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    return Response(status=204)
