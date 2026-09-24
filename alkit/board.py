# -*- coding: utf-8 -*-
"""Плата как данные: выгрузка из Allegro и правка.

    b = ak.dump(r"D:\\проект\\плата.brd")      # пакетно, над копией
    print(b.units, len(b.comps), len(b.nets))
    s = b.sym("DD1"); print(s["xy"], s["rot"], s["mirror"])

    ak.place(r"D:\\проект\\плата.brd", {"DD1": (40, 30, 90)},
             save_to=r"D:\\проект\\плата_v2.brd")

Единицы — единицы платы (b.units: millimeters, mils...). Набор их не
переводит: плата в милах остаётся в милах. Переводить при сравнении с
ожиданием — функцией to_mm().
"""
import io
import json
import os

from . import batch

UNIT_MM = {"millimeters": 1.0, "millimeter": 1.0, "mils": 0.0254,
           "inches": 25.4, "inch": 25.4, "microns": 0.001, "micron": 0.001,
           "centimeters": 10.0, "centimeter": 10.0}


class Board:
    """Результат выгрузки. Поля — списки словарей, как их записал SKILL."""

    def __init__(self):
        self.design = {}
        self.layers = []
        self.comps = []
        self.syms = []
        self.pins = []
        self.nets = []
        self.drcs = []
        self.segs = []
        self.vias = []
        self.shapes = []
        self.others = []
        self.complete = False       # дошла ли запись "end"
        self.bad_lines = 0

    @property
    def units(self):
        return self.design.get("units")

    def to_mm(self, v):
        """Значение в единицах платы -> мм."""
        return v * UNIT_MM[self.units]

    def sym(self, refdes):
        for s in self.syms:
            if s["refdes"] == refdes:
                return s
        return None

    def comp(self, refdes):
        for c in self.comps:
            if c["refdes"] == refdes:
                return c
        return None

    def pin_nets(self):
        """{(refdes, номер вывода): имя цепи или None}."""
        return {(p["refdes"], p["number"]): p["net"] for p in self.pins}

    def layer_names(self):
        return [l["name"] for l in sorted(self.layers,
                                          key=lambda l: l["index"])]

    def outline_bbox(self):
        """Габарит контура платы ((x1 y1) (x2 y2)) или None."""
        return self.design.get("outline")

    def __repr__(self):
        return ("<Board %s %s: %d комп., %d цепей, %d сегм., %d перех., "
                "%d полиг.>" % (self.design.get("name"), self.units,
                                len(self.comps), len(self.nets),
                                len(self.segs), len(self.vias),
                                len(self.shapes)))


_KIND = {"layer": "layers", "comp": "comps", "sym": "syms", "pin": "pins",
         "net": "nets", "drc": "drcs", "seg": "segs", "via": "vias",
         "shape": "shapes", "other": "others"}


def read_jsonl(path):
    """Разобрать выгрузку akDumpBoard. Строки читаются в cp1251."""
    b = Board()
    with io.open(path, encoding="cp1251", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                b.bad_lines += 1
                continue
            t = rec.pop("t", None)
            if t == "design":
                b.design = rec
            elif t == "end":
                b.complete = True
            elif t in _KIND:
                getattr(b, _KIND[t]).append(rec)
            else:
                b.others.append(rec)
    return b


def dump(board, figures=True, timeout=600):
    """Выгрузить плату пакетно. figures=False — без проводников и полигонов
    (быстро: компоненты, выводы, цепи, DRC)."""
    code = 'akDumpBoard(strcat(akOut "dump.jsonl") %s)' % (
        "t" if figures else "nil")
    r = batch.run(board, code, outputs=["dump.jsonl"], timeout=timeout)
    r.check()
    b = read_jsonl(r.path("dump.jsonl"))
    if not b.complete or b.bad_lines:
        raise batch.JobError("выгрузка неполная: end=%s, битых строк %d (%s)"
                             % (b.complete, b.bad_lines, r.dir))
    b.source = os.path.abspath(board)
    b.job = r
    return b


def edit(board, code, save_to, overwrite=False, timeout=600):
    """Выполнить правку (код SKILL) над копией и сохранить в save_to.

    Код идёт в транзакции: ошибка откатывает всё, файл не сохраняется.
    """
    r = batch.run(board, code, save_to=save_to, edit=True,
                  overwrite=overwrite, timeout=timeout)
    return r.check()


def _num(v):
    return "nil" if v is None else repr(float(v))


def place(board, placements, save_to, overwrite=False, timeout=600):
    """Расставить компоненты: {refdes: (x, y[, rot[, side]])}.

    x, y — абсолютная точка привязки символа, единицы платы; rot —
    абсолютный угол, градусы; side — "top"/"bottom". None — не менять.
    """
    lines = []
    for refdes, v in placements.items():
        v = list(v) + [None] * (4 - len(v))
        x, y, rot, side = v[:4]
        if side not in (None, "top", "bottom"):
            raise ValueError("side: top/bottom, а не %r" % side)
        lines.append('akPlace(%s %s %s %s %s)' % (
            json.dumps(refdes), _num(x), _num(y), _num(rot),
            "'" + side if side else "nil"))
    return edit(board, "\n".join(lines), save_to, overwrite=overwrite,
                timeout=timeout)
