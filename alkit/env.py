# -*- coding: utf-8 -*-
"""Окружение: где стоит Cadence, какая версия, какие лицензии, где работать.

Все пути ищутся, а не зашиваются: набор ходит по машинам с разными
установками. Порядок поиска корня Cadence:

    ALKIT_CDSROOT  ->  CDSROOT  ->  Sigrity_EDA_DIR  ->  C:\\Cadence\\SPB_*

Рабочая папка заданий нарочно лежит на пути БЕЗ пробелов и кириллицы:
Allegro 17.2 в пакетном режиме на таком пути то падает, то молча открывает
пустую плату (knowledge/30_ГРАБЛИ/30-02). Поэтому любая плата перед работой
копируется сюда, а результат копируется обратно средствами Python.
"""
import glob
import io
import os
import re
import shutil
import subprocess
import sys
import time

# Уровни продукта Allegro, проверенные в пакетном режиме со SKILL. Имя —
# это имя лицензии из license_cache (см. products()). Порядок — порядок
# попыток: если первая лицензия занята (например, открытым GUI), берётся
# следующая. knowledge/30_ГРАБЛИ/30-06.
PRODUCTS_TESTED = ("Allegro_performance", "Allegro_Venture_PCB_Designer")


def utf8_console():
    """Перевести stdout/stderr в UTF-8, иначе print с кириллицей падает."""
    for name in ("stdout", "stderr"):
        s = getattr(sys, name)
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            setattr(sys, name, io.TextIOWrapper(s.buffer, encoding="utf-8",
                                                errors="replace"))


def cdsroot():
    """Корень установки Cadence SPB (в нём tools/bin/allegro.exe)."""
    for var in ("ALKIT_CDSROOT", "CDSROOT", "Sigrity_EDA_DIR"):
        v = os.environ.get(var)
        if v and os.path.exists(os.path.join(v, "tools", "bin",
                                             "allegro.exe")):
            return os.path.normpath(v)
    found = sorted(glob.glob(r"C:\Cadence\SPB_*\tools\bin\allegro.exe"))
    if found:
        return os.path.dirname(os.path.dirname(os.path.dirname(found[-1])))
    raise RuntimeError("Cadence SPB не найден. Задайте ALKIT_CDSROOT — "
                       "папку, в которой лежит tools\\bin\\allegro.exe.")


def tool(name):
    """Полный путь к программе из tools/bin (allegro, report, tclsh...)."""
    p = os.path.join(cdsroot(), "tools", "bin", name)
    if not p.lower().endswith(".exe"):
        p += ".exe"
    if not os.path.exists(p):
        raise RuntimeError("нет программы %s" % p)
    return p


def version():
    """Версия Allegro строкой, например '17.2-S066'. Без запуска GUI."""
    out = subprocess.run([tool("allegro"), "-version"], capture_output=True,
                         timeout=60).stdout.decode("cp1251", "replace")
    m = re.search(r"allegro\s+(\S+)", out)
    return m.group(1) if m else out.strip()


def pcbenv():
    """Папка pcbenv пользователя: там allegro.ini и кэш лицензий."""
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    return os.path.join(home, "pcbenv")


def products():
    """Лицензии Allegro, доступные этому пользователю: {имя: True/False}.

    Читается кэш, который Allegro пишет при старте
    (pcbenv/license_cache_allegro_*.txt). Кэш отражает прошлый запуск, а не
    текущую занятость: занятую лицензию покажет только сам запуск.
    """
    out = {}
    for f in sorted(glob.glob(os.path.join(pcbenv(),
                                           "license_cache_allegro_*.txt"))):
        for line in io.open(f, encoding="cp1251", errors="replace"):
            parts = line.split()
            if len(parts) == 2 and not line.startswith("#"):
                out[parts[0]] = parts[1].upper() == "YES"
    return out


def product_order():
    """Порядок попыток лицензий для пакетного режима.

    ALKIT_PRODUCT (через запятую) — если задан, только он. Иначе проверенные
    уровни из PRODUCTS_TESTED, которые есть в кэше лицензий; если кэша нет —
    PRODUCTS_TESTED как есть.
    """
    env = os.environ.get("ALKIT_PRODUCT")
    if env:
        return [p.strip() for p in env.split(",") if p.strip()]
    have = products()
    if not have:
        return list(PRODUCTS_TESTED)
    order = [p for p in PRODUCTS_TESTED if have.get(p)]
    return order or list(PRODUCTS_TESTED)


# ---------------------------------------------------------------------------
# рабочая папка
# ---------------------------------------------------------------------------

def is_safe_path(path):
    """Путь, на котором Allegro 17.2 работает: только ASCII и без пробелов."""
    try:
        path.encode("ascii")
    except UnicodeEncodeError:
        return False
    return " " not in path


def work_root():
    """Корень рабочих папок заданий.

    ALKIT_WORK, иначе %LOCALAPPDATA%\\Temp\\alkit, если путь безопасен,
    иначе %SystemDrive%\\alkit_work. Путь короткий нарочно: команда живого
    режима ограничена ~250 байтами (knowledge/30_ГРАБЛИ/30-05).
    """
    cands = []
    if os.environ.get("ALKIT_WORK"):
        cands.append(os.environ["ALKIT_WORK"])
    la = os.environ.get("LOCALAPPDATA")
    if la:
        cands.append(os.path.join(la, "Temp", "alkit"))
    cands.append(os.path.join(os.environ.get("SystemDrive", "C:") + "\\",
                              "alkit_work"))
    for c in cands:
        c = os.path.normpath(c)
        if is_safe_path(c):
            os.makedirs(c, exist_ok=True)
            return c
    raise RuntimeError("не нашлось рабочей папки без пробелов и кириллицы; "
                       "задайте ALKIT_WORK")


_JOB = re.compile(r"^[a-z]+-\d{8}-\d{6}-\d{3}$")


def new_job_dir(kind="job", keep=40):
    """Свежая папка задания. Старые папки заданий сверх keep удаляются —
    по времени изменения, только созданные этой функцией, и никогда
    только что созданная."""
    root = work_root()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for i in range(1000):
        d = os.path.join(root, "%s-%s-%03d" % (kind, stamp, i))
        if not os.path.exists(d):
            os.makedirs(d)
            break
    jobs = [os.path.join(root, x) for x in os.listdir(root) if _JOB.match(x)]
    jobs = [j for j in jobs if os.path.isdir(j) and
            os.path.normcase(j) != os.path.normcase(d)]
    jobs.sort(key=os.path.getmtime)
    for j in jobs[:max(0, len(jobs) - keep)]:
        shutil.rmtree(j, ignore_errors=True)
    return d


def skill_path(path):
    """Путь для строки SKILL: прямые слэши, без экранирования."""
    return os.path.abspath(path).replace("\\", "/")


def kit_root():
    """Корень набора (папка, где лежат alkit/, knowledge/, skill/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
