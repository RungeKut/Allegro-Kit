# -*- coding: utf-8 -*-
"""Схема: чтение .dsn без Capture и сверка с платой.

    python tests\\test_capture.py

Демо-схема иерархическая: проверяются вхождения (обозначения корпусов, а
не секций) и то, что сверка связности честно ПРОПУЩЕНА, а не «пройдена».
"""
import os
import sys

from _common import DEMO_BRD, DEMO_COMPONENTS, DEMO_DSN, start

ak = start("test_capture")
s = ak.read_dsn(DEMO_DSN)
print(s)
b = ak.dump(DEMO_BRD, figures=False)

r = ak.Report("чтение схемы")
r.truth("схема иерархическая", s.hierarchical)
r.truth("нет обозначений секций (J6A) среди refdes",
        "J6" in s.refdes() and "J6A" not in s.refdes())
r.truth("нет «U?» среди refdes", not any("?" in x for x in s.refdes()))
r.truth("рядом с копией нет DSNlck",
        not any(f.lower().endswith("dsnlck") for f in os.listdir(s.job)))
extra = s.refdes() - {c["refdes"] for c in b.comps}
# Эталон регрессии (17.2-S066): в демо-схеме пять обозначений, которых нет
# на демо-плате, — источники V1, V2 и три элемента, не перенесённые на
# плату составителями демо. Это свойство демо-данных, а не ошибка чтения.
r.equal("лишние обозначения схемы", sorted(extra),
        ["R20", "R22", "TX1", "V1", "V2"])
ok = r.done()

# сверка: при ignore лишних обозначения совпадают, связность — ПРОПУСК
ok_cmp = ak.compare(s, b, ignore=extra)
r2 = ak.Report("итог сверки")
r2.truth("сверка сошлась при ignore лишних", ok_cmp)
r2.equal("общих обозначений", len(s.refdes() & {c["refdes"]
                                                 for c in b.comps}),
         DEMO_COMPONENTS)
ok &= r2.done()
sys.exit(0 if ok else 1)
