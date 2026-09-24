# -*- coding: utf-8 -*-
"""alkit — Cadence Allegro и OrCAD Capture из Python.

Проверенное поведение, ловушки и приёмы — в knowledge/ (начинать с
knowledge/INDEX.md).

Быстрый старт:

    import alkit as ak

    ak.utf8_console()
    b = ak.dump(r"D:\\проект\\плата.brd")        # Allegro без окна, над копией
    print(b)                                     # компоненты, цепи, сегменты
    ak.png(b, r"D:\\проект\\верх.png", side="top")

    s = ak.read_dsn(r"D:\\проект\\схема.DSN")     # Capture не нужен
    ak.compare(s, b)                             # схема -> плата

    ak.place(r"D:\\проект\\плата.brd", {"DD1": (40, 30, 90, "top")},
             save_to=r"D:\\проект\\плата_v2.brd")

Три пути к Allegro:
  пакетный  — run(), dump(), place(): allegro -nographic над копией платы;
  живой     — Live(): команды в открытый Allegro через WM_COPYDATA;
  утилиты   — summary(), drc(), gerber(), ipc2581(), step(), pdf().

Единицы — единицы платы (Board.units); набор их не переводит.
"""

__version__ = "0.1.0"

from .env import (cdsroot, is_safe_path, kit_root, product_order, products,
                  tool, utf8_console, version, work_root)
from .batch import JobError, Result, run
from .board import Board, dump, edit, place, read_jsonl
from .live import AllegroBusy, Live, allegro_dialogs, windows
from .reports import (drc, report, report_codes, summary, unconnected,
                      unplaced)
from .export import ExportError, films, gerber, ipc2581, pdf, step
from .capture import Schematic, read_dsn
from .render import png
from .verify import Report, check_board, compare

__all__ = [
    # окружение
    "utf8_console", "cdsroot", "tool", "version", "products",
    "product_order", "work_root", "is_safe_path", "kit_root",
    # пакетный режим и плата
    "run", "Result", "JobError", "dump", "edit", "place", "read_jsonl",
    "Board",
    # живой режим
    "Live", "windows", "allegro_dialogs", "AllegroBusy",
    # отчёты
    "report", "report_codes", "summary", "drc", "unconnected", "unplaced",
    # выходные файлы
    "gerber", "films", "ipc2581", "step", "pdf", "ExportError",
    # схема
    "read_dsn", "Schematic",
    # проверка
    "png", "Report", "check_board", "compare",
]
