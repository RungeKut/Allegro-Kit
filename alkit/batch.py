# -*- coding: utf-8 -*-
"""Пакетный режим: Allegro без окна выполняет код SKILL над КОПИЕЙ платы.

    import alkit as ak
    r = ak.run(r"D:\\проект\\плата.brd",
               'fprintf(akPort "%d" length(axlDBGetDesign()->components))',
               outputs=["port.txt"])
    r.check()                   # исключение, если что-то пошло не так
    print(r.read("port.txt"))

Что делается внутри и почему (подробности — knowledge/10_API/10-01):

  * плата копируется в рабочую папку без пробелов и кириллицы под именем
    in.brd — на других путях Allegro 17.2 падает или открывает пустую плату
    (30-02). Оригинал не открывается вовсе, блокировок на нём не остаётся;
  * сценарий .scr кончается «exit» + «fillin no» — иначе при несохранённых
    правках Allegro вечно ждёт ответа на вопрос о сохранении (30-01);
  * код задания выполняется внутри errset: ошибки SKILL не останавливают
    сценарий и видны только в журнале (30-04);
  * akJob сверяет имя открытой платы с ожидаемым — ловит молча открытую
    пустую плату (30-02, 30-03);
  * лицензии перебираются по порядку: открытый GUI держит свою, и пакет
    получает «No licenses available» (30-06);
  * тайм-аут обязателен: зависший Allegro снимается, блокировка удаляется.

В коде задания доступны:
  akOut   — папка задания со слэшем на конце, для выходных файлов;
  akPort  — открытый порт файла port.txt в папке задания (для мелочей);
  все функции alkit.il (akDumpBoard, akPlace, akText, akFindSym...).
"""
import io
import os
import re
import shutil
import subprocess
import time

from . import env

JOURNAL = "allegro.jrl"


class JobError(RuntimeError):
    pass


class Result:
    """Итог задания. ok — истина только при подтверждённом успехе."""

    def __init__(self, job_dir):
        self.dir = job_dir
        self.ok = False
        self.status = None          # "OK" / "ERR" / None (не дошло до akJob)
        self.message = ""
        self.product = None
        self.returncode = None
        self.elapsed = 0.0
        self.stdout = ""
        self.journal = ""
        self.errors = []            # строки *Error* и \e из журнала
        self.opened = None          # путь, который Allegro сообщил открытым
        self.saved_to = None

    def path(self, name):
        return os.path.join(self.dir, name)

    def read(self, name, encoding="cp1251"):
        with io.open(self.path(name), encoding=encoding,
                     errors="replace") as f:
            return f.read()

    def check(self):
        """Бросить JobError с разбором, если задание не подтвердило успех."""
        if not self.ok:
            raise JobError(self.explain())
        return self

    def explain(self):
        lines = ["задание не выполнено (папка %s)" % self.dir,
                 "  статус: %s" % self.status,
                 "  сообщение: %s" % self.message.strip()]
        if self.product:
            lines.append("  лицензия: %s" % self.product)
        if self.returncode is not None:
            lines.append("  код возврата Allegro: %s" % self.returncode)
        if self.opened:
            lines.append("  открыт: %s" % self.opened)
        for e in self.errors[:10]:
            lines.append("  журнал: %s" % e)
        return "\n".join(lines)

    def __repr__(self):
        return "<Result ok=%s status=%s %.1fs %s>" % (
            self.ok, self.status, self.elapsed, self.dir)


# ---------------------------------------------------------------------------

def _q(s):
    """Строка SKILL в кавычках. Пути уже со слэшами."""
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def _script_version():
    v = env.version()                       # '17.2-S066'
    m = re.match(r"(\d+\.\d+)", v)
    return m.group(1) if m else "17.2"


def write_job(job_dir, code, edit, save_name, expect="in"):
    """Разложить в папку задания alkit.il, user.il, job.il."""
    shutil.copy(os.path.join(env.kit_root(), "alkit", "skill", "alkit.il"),
                os.path.join(job_dir, "alkit.il"))
    d = env.skill_path(job_dir)
    # Файлы SKILL читаются Allegro в кодировке системы (cp1251). Символ,
    # которого в ней нет, лучше поймать здесь, чем получить мусор в плате.
    with io.open(os.path.join(job_dir, "user.il"), "w",
                 encoding="cp1251") as f:
        f.write(code)
        f.write("\n")
    save = _q(d + "/" + save_name) if save_name else "nil"
    job = (
        'akOut = %s\n'
        'load(%s)\n'
        'akPort = outfile(%s "w")\n'
        'akJob(%s %s %s %s %s %s)\n'
        'close(akPort)\n'
    ) % (_q(d + "/"), _q(d + "/alkit.il"), _q(d + "/port.txt"),
         _q(d + "/user.il"), _q(d + "/status.txt"), _q(d + "/done"),
         _q(expect) if expect else "nil", "t" if edit else "nil", save)
    with io.open(os.path.join(job_dir, "job.il"), "w",
                 encoding="cp1251") as f:
        f.write(job)
    return os.path.join(job_dir, "job.il")


def _kill(proc):
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, timeout=30)
    except Exception:
        proc.kill()


def _parse_journal(res):
    p = res.path(JOURNAL)
    if not os.path.exists(p):
        return
    res.journal = res.read(JOURNAL)
    for line in res.journal.splitlines():
        m = re.search(r"Design opened:\s*(.+)$", line)
        if m:
            res.opened = m.group(1).strip()
        if "*Error*" in line or line.startswith("\\e "):
            res.errors.append(line.strip())


def run(board, code, save_to=None, edit=None, outputs=(), timeout=300,
        products=None, overwrite=False):
    """Выполнить код SKILL над копией платы в Allegro без окна.

    board    — путь к .brd (любой, хоть с кириллицей: копируется);
    code     — текст SKILL; выполняется после загрузки alkit.il;
    save_to  — куда сохранить изменённую плату (.brd). None — не сохранять.
               Существующий файл без overwrite=True не перезаписывается:
               оригинал правится только явным решением;
    edit     — завернуть код в транзакцию (по умолчанию — если есть save_to);
    outputs  — имена файлов, которые код обязан создать в akOut; нет хоть
               одного — задание считается неудавшимся;
    timeout  — секунд на весь запуск Allegro;
    products — лицензии по порядку (по умолчанию env.product_order()).

    Возвращает Result; ok=True только если akJob записал OK, открыта была
    именно копия, все outputs на месте и сохранение (если просили) удалось.
    """
    board = os.path.abspath(board)
    if not os.path.isfile(board):
        raise FileNotFoundError(board)
    if save_to:
        save_to = os.path.abspath(save_to)
        if os.path.exists(save_to) and not overwrite:
            raise FileExistsError(
                "%s уже есть; перезапись только с overwrite=True" % save_to)
    if edit is None:
        edit = bool(save_to)

    job_dir = env.new_job_dir("batch")
    shutil.copy(board, os.path.join(job_dir, "in.brd"))
    write_job(job_dir, code, edit, "out" if save_to else None)
    d = env.skill_path(job_dir)
    with io.open(os.path.join(job_dir, "job.scr"), "w",
                 encoding="cp1251") as f:
        f.write("version %s\n" % _script_version())
        f.write("skill load(%s)\n" % _q(d + "/job.il"))
        f.write("exit\n")
        f.write("fillin no\n")

    res = Result(job_dir)
    t0 = time.time()
    for product in (products or env.product_order()):
        for junk in (JOURNAL, "status.txt", "done", "in.brd.lck"):
            if os.path.exists(res.path(junk)):
                os.remove(res.path(junk))
        res.product = product
        cmd = [env.tool("allegro"), "-nographic", "-product", product,
               "-p", job_dir, "-s", os.path.join(job_dir, "job.scr"),
               os.path.join(job_dir, "in.brd")]
        proc = subprocess.Popen(cmd, cwd=job_dir, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        try:
            out, _ = proc.communicate(timeout=timeout)
            res.returncode = proc.returncode
        except subprocess.TimeoutExpired:
            _kill(proc)
            out, _ = proc.communicate()
            res.returncode = "тайм-аут %d с" % timeout
        res.stdout = (out or b"").decode("cp1251", "replace")
        if "No licenses available" in res.stdout:
            res.message = "лицензия %s занята или недоступна" % product
            continue
        break
    res.elapsed = time.time() - t0
    if os.path.exists(res.path("in.brd.lck")):
        os.remove(res.path("in.brd.lck"))

    _parse_journal(res)
    if os.path.exists(res.path("status.txt")) and \
            os.path.exists(res.path("done")):
        text = res.read("status.txt")
        res.status = text.split("\n", 1)[0].strip()
        res.message = text.split("\n", 1)[1] if "\n" in text else ""
    elif not res.message:
        res.message = ("akJob не отработал: Allegro упал, завис или не "
                       "открыл плату; смотрите журнал")
    if res.status == "ERR" and res.errors:
        # errset отдаёт только обёртку «error while loading file ... at
        # line N»; настоящая причина лежит строкой выше в журнале
        res.message += "\n" + "\n".join(res.errors)

    ok = res.status == "OK"
    if ok and not (res.opened or "").replace("\\", "/").lower().endswith(
            "/in.brd"):
        ok = False
        res.message += "\nжурнал не подтвердил открытие копии платы"
    missing = [o for o in outputs if not os.path.exists(res.path(o))]
    if ok and missing:
        ok = False
        res.message += "\nнет выходных файлов: %s" % ", ".join(missing)
    if ok and save_to:
        out_brd = res.path("out.brd")
        if not os.path.exists(out_brd):
            ok = False
            res.message += "\nAllegro не записал out.brd"
        else:
            os.makedirs(os.path.dirname(save_to), exist_ok=True)
            shutil.copy(out_brd, save_to)
            res.saved_to = save_to
    res.ok = ok
    return res
