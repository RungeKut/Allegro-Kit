# -*- coding: utf-8 -*-
"""Плата: пакетная выгрузка, отчёты, сверка двух источников, картинка.

    python tests\\test_board.py

Проверяет: allegro -nographic над копией, akDumpBoard (все виды записей),
report.exe (sum, drc, ucn, upc), совпадение DRC из двух источников,
render.png, неизменность оригинала.
"""
import os
import sys

from _common import (DEMO_BRD, DEMO_COMPONENTS, DEMO_NETS, DEMO_OUTLINE,
                     DEMO_UNITS, OUT, mtime, start)

ak = start("test_board")
t0 = mtime(DEMO_BRD)

b = ak.dump(DEMO_BRD)
print(b, "за %.1f с" % b.job.elapsed)

ok = ak.check_board(b, "выгрузка демо-платы",
                    expect_components=DEMO_COMPONENTS,
                    expect_nets=DEMO_NETS, expect_units=DEMO_UNITS,
                    expect_outline=DEMO_OUTLINE)

s = ak.summary(DEMO_BRD)
r = ak.Report("выгрузка против отчётов")
r.equal("символов корпусов (sum)",
        s["Package Symbols"]["Total"],
        len([x for x in b.syms if x["type"] == "PACKAGE"]))
r.equal("нарушений DRC: sum / выгрузка", s["DRC Errors"], len(b.drcs))
r.equal("нарушений DRC: drc / выгрузка", len(ak.drc(DEMO_BRD)), len(b.drcs))
r.equal("неразмещённых (upc)", ak.unplaced(DEMO_BRD),
        len([c for c in b.comps if not c["placed"]]))
net = ak.report(DEMO_BRD, "net").splitlines()
head = [n for n, l in enumerate(net) if l.startswith("Net Name")][0]
r.equal("цепей (net) / выгрузка",
        len([l for l in net[head + 1:] if l.strip()]), len(b.nets))
r.truth("есть проводники, переходные, полигоны",
        b.segs and b.vias and b.shapes,
        "%d / %d / %d" % (len(b.segs), len(b.vias), len(b.shapes)))
r.truth("контур платы выгружен",
        any((x.get("layer") or "").startswith("BOARD GEOMETRY/")
            and "OUTLINE" in x["layer"] for x in b.shapes + b.segs))
r.truth("оригинал не изменён", mtime(DEMO_BRD) == t0)
ok &= r.done()

for side in ("top", "bottom"):
    p = ak.png(b, os.path.join(OUT, "плата_%s.png" % side), side=side)
    print("картинка:", p, "— посмотрите на неё")

sys.exit(0 if ok else 1)
