# -*- coding: utf-8 -*-
"""Выходные файлы платы штатными утилитами, над копией платы.

    ak.gerber(path, r"C:\\выход\\gerber")           # все плёнки платы
    ak.ipc2581(path, r"C:\\выход\\плата.xml")
    ak.step(path, r"C:\\выход\\плата.stp")
    ak.pdf(path, r"C:\\выход\\плата.pdf")

Каждая функция возвращает словарь с путями, предупреждениями и журналом, и
сама проверяет, что файл не пустышка. Это не перестраховка: код возврата
утилит ничего не говорит о результате (knowledge/30_ГРАБЛИ/30-07):

  * ipc2581_out без ключей разделов пишет оболочку в 1.8 КБ без платы, с
    кодом 0 — поэтому здесь ключи всех разделов по умолчанию;
  * step_out выбрасывает незамкнутый контур платы с одними WARNING в
    журнале и кодом 0 — такие предупреждения поднимаются в "warnings", а
    с strict=True превращаются в исключение;
  * artwork возвращает 1 при любых предупреждениях, файлы при этом есть.
"""
import glob
import io
import os
import re
import shutil
import subprocess
import time

from . import env


class ExportError(RuntimeError):
    pass


def _stage(board, kind):
    job = env.new_job_dir(kind)
    brd = os.path.join(job, "in.brd")
    shutil.copy(os.path.abspath(board), brd)
    return job, brd


def _run(cmd, job, timeout):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=job, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout.decode("cp1251", "replace"), \
        time.time() - t0


def _read(path):
    if not os.path.exists(path):
        return ""
    with io.open(path, encoding="cp1251", errors="replace") as f:
        return f.read()


def _warnings(log):
    out = []
    lines = log.splitlines()
    for i, l in enumerate(lines):
        if "WARNING" in l or "ERROR" in l:
            tail = " ".join(x.strip() for x in lines[i + 1:i + 4]
                            if x.strip() and "WARNING" not in x)
            out.append((l.strip() + " " + tail).strip())
    return out


def _put(src, dst):
    dst = os.path.abspath(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(src, dst)
    return dst


# ---------------------------------------------------------------------------

IPC_ALL = ["-b", "-l", "-R", "-n", "-p", "-t", "-c", "-O", "-I", "-S", "-k"]


def ipc2581(board, out, units="MILLIMETER", flags=None, timeout=900,
            min_components=1):
    """IPC-2581 (ревизия B). flags — ключи разделов, по умолчанию все
    основные (BOM, стек, сверловка, цепи, корпуса, медь, маски, падстеки).

    Проверка: в файле есть компоненты (<Component) — не меньше
    min_components; иначе ExportError.
    """
    job, brd = _stage(board, "ipc")
    args = [env.tool("ipc2581_out"), "-u", units] + \
        list(IPC_ALL if flags is None else flags) + ["-o", "out", brd]
    rc, stdout, dt = _run(args, job, timeout)
    xml = os.path.join(job, "out.xml")
    if not os.path.exists(xml):
        raise ExportError("ipc2581_out не создал файл (код %s): %s"
                          % (rc, stdout[-400:]))
    text = _read(xml)
    n = text.count("<Component ")
    if n < min_components:
        raise ExportError("IPC-2581 без компонентов (%d): проверьте ключи "
                          "разделов; журнал %s" % (n, job))
    return {"path": _put(xml, out), "components": n, "bytes": len(text),
            "returncode": rc, "seconds": dt,
            "log": _read(os.path.join(job, "ipc2581_out.log")), "job": job}


def step(board, out, units="MILLIMETER", with_parts=True, strict=False,
         extra=(), timeout=900):
    """STEP (AP214). with_parts — компоненты с назначенными STEP-моделями
    и без них (коробками). extra — дополнительные ключи step_out.

    В "warnings" — все WARNING журнала; "outline_dropped" — сколько
    элементов контура платы выброшено как незамкнутые. strict=True делает
    из выброшенного контура исключение.
    """
    job, brd = _stage(board, "step")
    args = [env.tool("step_out"), "-u", units]
    if with_parts:
        args += ["-m", "-n"]
    args += list(extra) + ["-o", "out.stp", brd]
    rc, stdout, dt = _run(args, job, timeout)
    stp = os.path.join(job, "out.stp")
    log = _read(os.path.join(job, "step_out.log"))
    if not os.path.exists(stp):
        raise ExportError("step_out не создал файл (код %s): %s"
                          % (rc, stdout[-400:]))
    dropped = log.count("Discarding unconnected item on Board Geometry")
    if strict and dropped:
        raise ExportError("контур платы не замкнут: step_out выбросил %d "
                          "элементов контура (журнал %s)" % (dropped, job))
    return {"path": _put(stp, out), "bytes": os.path.getsize(stp),
            "warnings": _warnings(log), "outline_dropped": dropped,
            "returncode": rc, "seconds": dt, "log": log, "job": job}


def pdf(board, out, extra=(), timeout=900):
    """PDF всех плёнок платы одним файлом (pdf_out).

    pdf_out приклеивает к имени глобальные приставки плёнок платы
    («JOBNAME-out-ISSUEA.pdf» вместо «out.pdf»), поэтому настоящий путь
    берётся из строки «Output file:» его вывода.
    """
    job, brd = _stage(board, "pdf")
    rc, stdout, dt = _run([env.tool("pdf_out"), brd] + list(extra) +
                          ["-o", "out.pdf"], job, timeout)
    m = re.search(r"Output file:\s*(.+?\.pdf)\s*$", stdout, re.M | re.I)
    p = os.path.normpath(m.group(1)) if m else os.path.join(job, "out.pdf")
    if not os.path.exists(p) or os.path.getsize(p) < 1000:
        raise ExportError("pdf_out не создал PDF (код %s): %s"
                          % (rc, stdout[-400:]))
    return {"path": _put(p, out), "bytes": os.path.getsize(p),
            "returncode": rc, "seconds": dt,
            "log": _read(os.path.join(job, "pdf_out.log")), "job": job}


def films(board):
    """Плёнки Gerber, заданные в плате (artwork -l)."""
    job, brd = _stage(board, "films")
    rc, stdout, dt = _run([env.tool("artwork"), "-l", brd], job, 120)
    return [l.strip() for l in stdout.splitlines() if l.strip()]


def gerber(board, out_dir, films_=None, timeout=900):
    """Gerber по плёнкам, заданным в плате (Manufacture > Artwork).

    films_ — список плёнок; None — все. Код 1 у artwork означает
    предупреждения, а не провал: провалом считается отсутствие файла хотя
    бы одной плёнки.
    """
    job, brd = _stage(board, "gerber")
    want = films_ or films(board)
    if not want:
        raise ExportError("в плате не задано ни одной плёнки Gerber")
    args = [env.tool("artwork")]
    for f in films_ or []:
        args += ["-f", f]
    rc, stdout, dt = _run(args + [brd], job, timeout)
    arts = sorted(glob.glob(os.path.join(job, "*.art")))
    got = {}
    for f in want:
        pat = re.compile(r"(^|[-_])%s([-_.]|$)" % re.escape(f), re.I)
        hits = [a for a in arts if pat.search(os.path.basename(a))]
        if hits:
            got[f] = hits[0]
    missing = [f for f in want if f not in got]
    if missing:
        raise ExportError("нет файлов плёнок: %s (журнал %s)"
                          % (", ".join(missing), job))
    os.makedirs(out_dir, exist_ok=True)
    paths = [_put(a, os.path.join(out_dir, os.path.basename(a)))
             for a in arts]
    log = _read(os.path.join(job, "photoplot.log"))
    return {"paths": paths, "films": got, "returncode": rc, "seconds": dt,
            "warnings": _warnings(log), "log": log, "job": job}
