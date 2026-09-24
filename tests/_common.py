# -*- coding: utf-8 -*-
"""Общее для сквозных проверок: пути к демо-паре Cadence и к выводу.

Проверки идут на демонстрационных файлах из поставки Cadence — своих плат
в репозитории нет. Файлы поставки не изменяются: alkit работает с копиями.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import alkit as ak   # noqa: E402

OUT = os.path.join(ROOT, "tests", "vyvod")
DEMO_DIR = os.path.join(ak.cdsroot(), "share", "orcad", "examples",
                        "pcbdesign", "pcbdemo1")
DEMO_BRD = os.path.join(DEMO_DIR, "allegro", "DEMOJ-complete.brd")
DEMO_DSN = os.path.join(DEMO_DIR, "DEMOJ.Dsn")

# Ожидания по демо-плате. Компоненты и цепи — из отчётов report.exe
# (sum: Package Symbols Total; net: строки после «Net Name»), то есть не из
# выгрузки SKILL, которую проверяем. Контур — эталон регрессии: записан с
# выгрузки на 17.2-S066 и ловит изменение поведения при смене версии.
DEMO_UNITS = "millimeters"
DEMO_COMPONENTS = 351
DEMO_NETS = 371
DEMO_OUTLINE = ((-25.4, -4.445), (100.33, 111.355))


def start(name):
    ak.utf8_console()
    os.makedirs(OUT, exist_ok=True)
    for p in (DEMO_BRD, DEMO_DSN):
        if not os.path.exists(p):
            print("нет демо-файла поставки: %s" % p)
            sys.exit(2)
    print("== %s   Allegro %s" % (name, ak.version()))
    return ak


def mtime(p):
    return os.path.getmtime(p)
