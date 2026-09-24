# -*- coding: utf-8 -*-
"""Отчёты Allegro без окна: report.exe над копией платы.

    s = ak.summary(path)       # {'DRC Errors': 3, 'Package Symbols': {...}}
    ak.drc(path)               # [{'Constraint Name': ..., ...}]
    ak.unconnected(path)       # неразведённых пар выводов
    ak.unplaced(path)          # неразмещённых компонентов
    text = ak.report(path, "bom")

Коды отчётов — report_codes() или knowledge/10_API/10-04. Отчёт идёт около
секунды. Числа отчёта — независимая от выгрузки SKILL сверка: DRC и
связность удобнее брать отсюда.
"""
import io
import os
import re
import shutil
import subprocess

from . import env


def _stage(board, kind):
    job = env.new_job_dir(kind)
    dst = os.path.join(job, "in.brd")
    shutil.copy(os.path.abspath(board), dst)
    return job, dst


def report(board, code, timeout=300):
    """Текст отчёта `code` (sum, drc, ucn, upc, bom, cmp, net...)."""
    job, brd = _stage(board, "report")
    out = os.path.join(job, "rep_%s.txt" % code)
    p = subprocess.run([env.tool("report"), "-v", code, brd, out], cwd=job,
                       capture_output=True, timeout=timeout)
    if not os.path.exists(out):
        raise RuntimeError("report -v %s не создал файл (код %s): %s"
                           % (code, p.returncode,
                              p.stdout.decode("cp1251", "replace")[-500:]))
    with io.open(out, encoding="cp1251", errors="replace") as f:
        return f.read()


def report_codes():
    """{код: название} из справки report.exe."""
    p = subprocess.run([env.tool("report"), "-help"], capture_output=True,
                       timeout=60)
    text = p.stdout.decode("cp1251", "replace")
    out = {}
    for line in text.split("Report List", 1)[-1].splitlines():
        m = re.match(r"^\s*(\S+)\s{2,}(.+?)\s*$", line)
        if m and m.group(1) not in ("Code", "----"):
            out[m.group(1)] = m.group(2)
    return out


def _num(s):
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s.strip()


def summary(board):
    """Сводка платы (отчёт sum) словарём.

    «DRC Errors: 3» -> {'DRC Errors': 3};
    «Layers:  Total(6)  Routing(2)» -> {'Layers': {'Total': 6, ...}};
    «Drawing Extents  XL(-450.000) ...» -> {'Drawing Extents': {'XL': ...}}.
    Три строки шапки (название, путь к копии, дата) пропускаются.
    """
    out = {}
    for line in report(board, "sum").splitlines()[3:]:
        pair_re = r"([A-Za-z_]+)\(([^)]*)\)"
        if ":" in line:
            key, val = line.split(":", 1)
        else:
            m = re.match(r"^\s*(.+?)\s+[A-Za-z_]+\(", line)
            if not m:
                continue
            key, val = m.group(1), line[m.end(1):]
        key = key.strip()
        pairs = re.findall(pair_re, val)
        if pairs:
            out[key] = {k: _num(v) for k, v in pairs}
        elif val.strip():
            out[key] = _num(val.strip())
    return out


def _csv_table(text, header_start):
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if l.startswith(header_start):
            head = [h.strip() for h in l.split(",")]
            rows = []
            for r in lines[i + 1:]:
                if not r.strip():
                    break
                # поля с запятыми внутри координат "(1.0 2.0)" не бьются:
                # координаты в отчёте разделены пробелом
                cells = [c.strip() for c in r.split(",")]
                rows.append(dict(zip(head, cells)))
            return rows
    return []


def drc(board):
    """Список нарушений DRC (отчёт drc). Пустой список — нарушений нет."""
    text = report(board, "drc")
    m = re.search(r"Total DRC Errors,(\d+)", text)
    rows = _csv_table(text, "Constraint Name")
    if m and int(m.group(1)) != len(rows):
        raise RuntimeError("отчёт DRC разобран неверно: итог %s, строк %d"
                           % (m.group(1), len(rows)))
    return rows


def unconnected(board):
    """Число неразведённых пар выводов (отчёт ucn)."""
    m = re.search(r"Total Unconnected Pin Pairs:\s*(\d+)",
                  report(board, "ucn"))
    if not m:
        raise RuntimeError("в отчёте ucn нет итоговой строки")
    return int(m.group(1))


def unplaced(board):
    """Число неразмещённых компонентов (отчёт upc)."""
    m = re.search(r"Total Unplaced Components:\s*(\d+)",
                  report(board, "upc"))
    if not m:
        raise RuntimeError("в отчёте upc нет итоговой строки")
    return int(m.group(1))
