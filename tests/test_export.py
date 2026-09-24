# -*- coding: utf-8 -*-
"""Выходные файлы: Gerber, IPC-2581, STEP, PDF — с проверкой содержимого.

    python tests\\test_export.py
"""
import os
import sys

from _common import DEMO_BRD, DEMO_COMPONENTS, OUT, start

ak = start("test_export")
d = os.path.join(OUT, "экспорт")
r = ak.Report("экспорт демо-платы")

films = ak.films(DEMO_BRD)
g = ak.gerber(DEMO_BRD, os.path.join(d, "gerber"))
r.equal("плёнок Gerber = заданных в плате", len(g["films"]), len(films))

i = ak.ipc2581(DEMO_BRD, os.path.join(d, "плата.xml"))
r.truth("IPC-2581: компонентов не меньше, чем на плате",
        i["components"] >= DEMO_COMPONENTS, str(i["components"]))

st = ak.step(DEMO_BRD, os.path.join(d, "плата.stp"))
r.equal("STEP: контур не выброшен", st["outline_dropped"], 0)
r.truth("STEP: с компонентами (> 100 КБ)", st["bytes"] > 100000,
        "%d байт" % st["bytes"])

p = ak.pdf(DEMO_BRD, os.path.join(d, "плата.pdf"))
r.truth("PDF есть (> 100 КБ)", p["bytes"] > 100000, "%d байт" % p["bytes"])

# без ключей разделов IPC-2581 пуст — ловится проверкой содержимого
empty_caught = False
try:
    ak.ipc2581(DEMO_BRD, os.path.join(d, "пустой.xml"), flags=[])
except ak.ExportError:
    empty_caught = True
r.truth("пустой IPC-2581 распознан", empty_caught)
sys.exit(0 if r.done() else 1)
