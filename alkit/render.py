# -*- coding: utf-8 -*-
"""Картинка платы из выгрузки — проверка глазами.

    b = ak.dump(path)
    ak.png(b, r"C:\\проект\\верх.png", side="top")
    ak.png(b, r"C:\\проект\\низ.png", side="bottom")

Рисуется по данным выгрузки, а не снимком экрана: снимок окна Allegro
выходит с белым холстом, а при заблокированном экране не снимается вовсе
(knowledge/30_ГРАБЛИ/30-08). Зато картинка получается и в пакетном режиме.

Упрощения, о которых надо помнить при разглядывании:
  * дуги в контурах полигонов заменены хордами (у вершин есть радиус, но он
    не используется), дуги проводников — тоже отрезками;
  * площадки выводов — габаритом вывода (bbox), а не формой площадки;
  * вид снизу отражён по X — как если перевернуть плату.
Нужна библиотека Pillow (ставит tools/setup.ps1).
"""
import os

SIDES = ("top", "bottom", "all")

# цвета: (R, G, B, A)
C_BG = (16, 16, 16, 255)
C_OUTLINE = (255, 220, 0, 255)
C_TOP = (220, 60, 50, 255)
C_BOTTOM = (60, 120, 230, 255)
C_INNER = (70, 150, 70, 255)
C_SILK = (230, 230, 230, 255)
C_VIA = (170, 170, 170, 255)
C_PIN_SMD = (240, 170, 60, 255)
C_PIN_TH = (200, 200, 90, 255)
C_BODY = (120, 200, 200, 255)
C_TEXT = (255, 255, 255, 255)
C_DRC = (255, 0, 255, 255)

OUTLINE_LAYERS = ("BOARD GEOMETRY/OUTLINE", "BOARD GEOMETRY/DESIGN_OUTLINE")


def _font(size):
    from PIL import ImageFont
    for name in ("arial.ttf", "segoeui.ttf", "tahoma.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _etch_color(layer, order):
    name = layer.split("/", 1)[-1]
    if order and name == order[0]:
        return C_TOP
    if order and name == order[-1]:
        return C_BOTTOM
    return C_INNER


def png(board, out, side="top", width=1600, labels=True, drc=True,
        title=None):
    """Нарисовать плату в PNG. side: top / bottom / all. Возвращает путь."""
    from PIL import Image, ImageDraw
    if side not in SIDES:
        raise ValueError("side: %s" % ", ".join(SIDES))
    order = board.layer_names()
    top, bottom = (order[0], order[-1]) if order else ("TOP", "BOTTOM")

    box = board.outline_bbox() or board.design.get("extents")
    (x1, y1), (x2, y2) = box
    pad = 0.04 * max(x2 - x1, y2 - y1)
    x1, y1, x2, y2 = x1 - pad, y1 - pad, x2 + pad, y2 + pad
    k = width / float(x2 - x1)
    height = max(1, int((y2 - y1) * k))
    mirror = side == "bottom"

    def P(pt):
        x, y = pt[0], pt[1]
        px = (x2 - x) * k if mirror else (x - x1) * k
        return (px, (y2 - y) * k)

    def W(w):
        return max(1, int(round((w or 0) * k)))

    img = Image.new("RGBA", (width, height), C_BG)
    layer_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer_img)

    def want_etch(layer):
        name = layer.split("/", 1)[-1]
        if side == "all":
            return True
        return name == (top if side == "top" else bottom)

    # полигоны меди — полупрозрачно, чтобы под ними были видны проводники
    for s in board.shapes:
        lay = s.get("layer") or ""
        pts = [v[0] if isinstance(v[0], list) else v for v in (s.get("pts")
                                                              or [])]
        if len(pts) < 3:
            continue
        if lay.startswith("ETCH/") and want_etch(lay):
            c = _etch_color(lay, order)
            ld.polygon([P(p) for p in pts], fill=c[:3] + (70,), outline=c)
    img = Image.alpha_composite(img, layer_img)
    d = ImageDraw.Draw(img)

    silk = "SILKSCREEN_TOP" if side != "bottom" else "SILKSCREEN_BOTTOM"
    for s in board.segs:
        lay = s.get("layer") or ""
        (a, b) = s["se"]
        if lay.startswith("ETCH/"):
            if want_etch(lay):
                d.line([P(a), P(b)], fill=_etch_color(lay, order),
                       width=W(s.get("w")))
        elif lay.endswith("/" + silk):
            d.line([P(a), P(b)], fill=C_SILK, width=1)

    for v in board.vias:
        (bx1, by1), (bx2, by2) = v["bbox"]
        r = max(1, (bx2 - bx1) * k / 2)
        cx, cy = P(v["xy"])
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=C_VIA)

    for p in board.pins:
        (bx1, by1), (bx2, by2) = p["bbox"] or (p["xy"], p["xy"])
        sym = board.sym(p["refdes"])
        on_bottom = bool(sym and sym.get("mirror"))
        if side != "all" and not p.get("through") and \
                on_bottom != (side == "bottom"):
            continue
        a, b = P((bx1, by1)), P((bx2, by2))
        d.rectangle([min(a[0], b[0]), min(a[1], b[1]),
                     max(a[0], b[0]), max(a[1], b[1])],
                    outline=C_PIN_TH if p.get("through") else C_PIN_SMD)

    # контур платы — поверх всего
    for s in board.segs:
        if (s.get("layer") or "") in OUTLINE_LAYERS:
            (a, b) = s["se"]
            d.line([P(a), P(b)], fill=C_OUTLINE, width=2)
    for s in board.shapes:
        if (s.get("layer") or "") in OUTLINE_LAYERS:
            pts = [v[0] if isinstance(v[0], list) else v
                   for v in (s.get("pts") or [])]
            if len(pts) >= 2:
                d.line([P(p) for p in pts + pts[:1]], fill=C_OUTLINE,
                       width=2)

    if labels:
        f = _font(max(9, int(1.0 * k)))
        for s in board.syms:
            if not s.get("refdes") or s.get("type") != "PACKAGE":
                continue
            if side != "all" and bool(s.get("mirror")) != (side == "bottom"):
                continue
            cx, cy = P(s["xy"])
            d.text((cx, cy), s["refdes"], fill=C_TEXT, font=f, anchor="mm")

    if drc:
        for x in board.drcs:
            cx, cy = P(x["xy"])
            d.line([cx - 8, cy - 8, cx + 8, cy + 8], fill=C_DRC, width=2)
            d.line([cx - 8, cy + 8, cx + 8, cy - 8], fill=C_DRC, width=2)

    name = os.path.basename(getattr(board, "source", "") or "") or \
        board.design.get("name")
    head = title or "%s  %s  вид: %s" % (name, board.units, side)
    d.text((8, 8), head, fill=C_TEXT, font=_font(16))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.convert("RGB").save(out)
    return out
