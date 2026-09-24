# -*- coding: utf-8 -*-
"""Схема OrCAD Capture (.dsn) как данные — без запуска Capture.

    s = ak.read_dsn(r"D:\\проект\\схема.DSN")
    print(s)                                   # листы, элементы, цепи
    s.components()["DD1"]                      # {'value':..., 'footprint':...}
    s.pin_nets()[("DD1", "5")]                 # цепь вывода (плоская схема)

База схемы читается штатным tclsh.exe из tools/bin с библиотекой
orDb_Dll_Tcl64.dll (knowledge/10_API/10-03). Файл, как и плата, сначала
копируется в рабочую папку без пробелов и кириллицы.

Два источника в выгрузке, и путать их нельзя:

  * part — экземпляры на листах. В ИЕРАРХИЧЕСКОЙ схеме на листе блока стоят
    «U?», «R?»: настоящие обозначения там не хранятся. Зато у экземпляра
    есть выводы с цепями листа;
  * occ — вхождения. Истинные обозначения, номиналы, посадочные места для
    любой схемы. Цепи выводов через вхождения пока не выгружаются.

Поэтому components() всегда берётся из вхождений, а pin_nets() работает
только для плоской схемы и на иерархической бросает исключение, а не
отдаёт неверные имена цепей.

Многосекционный элемент даёт несколько записей с одним refdes — по одной
на секцию: сверять с платой надо множества refdes, а не количества.
"""
import io
import json
import os
import shutil
import subprocess

from . import env


class Schematic:
    def __init__(self):
        self.design = {}
        self.pages = []
        self.parts = []
        self.occs = []
        self.flatnets = []
        self.complete = False
        self.bad_lines = 0

    @property
    def hierarchical(self):
        return any(o.get("depth", 0) > 0 for o in self.occs)

    def components(self):
        """{refdes: {"value", "footprint", "sections"}} по вхождениям."""
        out = {}
        for o in self.occs:
            c = out.setdefault(o["refdes"], {"value": o["value"],
                                             "footprint": o["footprint"],
                                             "sections": 0})
            c["sections"] += 1
        return out

    def refdes(self):
        """Множество позиционных обозначений (секции склеены)."""
        return set(self.components())

    def part(self, refdes):
        """Экземпляры на листах с этим refdes (все секции)."""
        return [p for p in self.parts if p["refdes"] == refdes]

    def pin_nets(self):
        """{(refdes, номер вывода): имя цепи или None}. Только плоская схема."""
        if self.hierarchical:
            raise NotImplementedError(
                "схема иерархическая: цепи выводов на листах блоков — "
                "локальные, а выгрузка цепей через вхождения не сделана "
                "(knowledge/10_API/10-03)")
        out = {}
        for p in self.parts:
            for num, _name, net in p["pins"]:
                out[(p["refdes"], num)] = net
        return out

    def footprints(self):
        """{refdes: PCB Footprint} по вхождениям."""
        return {r: c["footprint"] for r, c in self.components().items()}

    def __repr__(self):
        return ("<Schematic %s: %d стр., %d вхождений (%d refdes), %d цепей%s>"
                % (os.path.basename(getattr(self, "source", "") or "")
                   or self.design.get("name"), len(self.pages),
                   len(self.occs), len(self.refdes()), len(self.flatnets),
                   ", иерархическая" if self.hierarchical else ""))


def read_dsn(path, timeout=300):
    """Прочитать .dsn. Возвращает Schematic; неполная выгрузка — исключение."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    job = env.new_job_dir("dsn")
    src = os.path.join(job, "in.dsn")
    shutil.copy(path, src)
    out = os.path.join(job, "dsn.jsonl")
    script = os.path.join(env.kit_root(), "alkit", "tcl", "dsn_dump.tcl")
    shutil.copy(script, os.path.join(job, "dsn_dump.tcl"))
    bindir = os.path.join(env.cdsroot(), "tools", "bin")
    p = subprocess.run([env.tool("tclsh"),
                        os.path.join(job, "dsn_dump.tcl"), src, out],
                       cwd=bindir, capture_output=True, timeout=timeout)
    log = (p.stdout + p.stderr).decode("cp1251", "replace")
    if not os.path.exists(out):
        raise RuntimeError("tclsh не выгрузил схему (код %s): %s"
                           % (p.returncode, log[-800:]))
    s = Schematic()
    kinds = {"page": s.pages, "part": s.parts, "occ": s.occs}
    with io.open(out, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                s.bad_lines += 1
                continue
            t = r.pop("t")
            if t == "design":
                s.design = r
            elif t in kinds:
                kinds[t].append(r)
            elif t == "flatnet":
                s.flatnets.append(r["name"])
            elif t == "end":
                s.complete = True
            elif t == "error":
                raise RuntimeError("схема: %s" % r.get("msg"))
    if not s.complete or s.bad_lines:
        raise RuntimeError("выгрузка схемы неполная (end=%s, битых строк %d),"
                           " код tclsh %s: %s" % (s.complete, s.bad_lines,
                                                  p.returncode, log[-800:]))
    s.source = path
    s.job = job
    return s
