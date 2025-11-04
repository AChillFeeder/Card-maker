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
DEFAULT_MAIN_SCALE = 92
DEFAULT_BG_SCALE = 100
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
    "rushdown": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-sword-icon lucide-sword"><path d="m11 19-6-6"/><path d="m5 21-2-2"/><path d="m8 16-4 4"/><path d="M9.5 17.5 21 6V3h-3L6.5 14.5"/></svg>',
    "zoning": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 3a9 9 0 1 0 9 9 9 9 0 0 0-9-9Zm0 2a7 7 0 1 1-7 7 7 7 0 0 1 7-7Zm0 3a4 4 0 1 0 4 4 4 4 0 0 0-4-4Zm0 2.5a1.5 1.5 0 1 1-1.5 1.5A1.5 1.5 0 0 1 12 10.5Z"/></svg>',
    "mixups": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-right-left-icon lucide-arrow-right-left"><path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/></svg>',
    "grappler": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-biceps-flexed-icon lucide-biceps-flexed"><path d="M12.409 13.017A5 5 0 0 1 22 15c0 3.866-4 7-9 7-4.077 0-8.153-.82-10.371-2.462-.426-.316-.631-.832-.62-1.362C2.118 12.723 2.627 2 10 2a3 3 0 0 1 3 3 2 2 0 0 1-2 2c-1.105 0-1.64-.444-2-1"/><path d="M15 14a5 5 0 0 0-7.584 2"/><path d="M9.964 6.825C8.019 7.977 9.5 13 8 15"/></svg>',
    "allrounder": '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-star-icon lucide-star"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/></svg>',
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
    main_scale = int(form.get("mainScale", DEFAULT_MAIN_SCALE))
    main_offset_x = int(form.get("mainOffsetX", 0))
    main_offset_y = int(form.get("mainOffsetY", 0))
    bg_scale = int(form.get("bgScale", DEFAULT_BG_SCALE))
    bg_offset_x = int(form.get("bgOffsetX", 0))
    bg_offset_y = int(form.get("bgOffsetY", 0))

    bg_file = files.get("bgFile")
    main_file = files.get("mainFile")

    if not bg_file or not main_file:
        return jsonify({"error": "Les images d'arrière-plan et du personnage sont toutes les deux requises."}), 400

    bg_url = _as_data_url(bg_file)
    main_url = _as_data_url(main_file)

    frame_pad = max(5, min(96, int(border_width * 1.6)))
    card_radius = max(0, radius)
    accent_soft = _hex_to_rgba(border_color, 0.32)
    main_scale_value = max(10, min(300, main_scale)) / 100
    bg_scale_value = max(10, min(400, bg_scale)) / 100
    bg_offset_x = max(-500, min(500, bg_offset_x))
    bg_offset_y = max(-500, min(500, bg_offset_y))

    player_name = _clean_text(form.get("playerName"), "Invité", 40)
    team_name = _clean_text(form.get("teamName"), "Équipe", 28, allow_empty=True)
    champion_name = _clean_text(form.get("favoriteChampion"), "Champion", 32)
    playstyle_label = _clean_text(form.get("playstyle"), "Aggresseur", 16)
    side_tag = _clean_text(form.get("sideTag"), "Saison Arcade 2025", 48, allow_empty=True)
    badge_text = _clean_text(form.get("badgeText"), "ARC", 20, allow_empty=True)
    rating_text = _clean_text(form.get("cardRank"), "100", 8, allow_empty=True)
    corner_label = _clean_text(form.get("cornerLabel"), "FGC", 6, allow_empty=True)

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
        --bg-scale-dyn:{bg_scale_value};
        --bg-offset-x-dyn:{bg_offset_x}px;
        --bg-offset-y-dyn:{bg_offset_y}px;
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
