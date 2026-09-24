# -*- coding: utf-8 -*-
"""Живой режим: команды в ОТКРЫТЫЙ Allegro через WM_COPYDATA.

    lv = ak.Live()                    # найти главное окно Allegro
    print(lv.design)                  # имя открытой платы
    r = lv.run('fprintf(akPort "%d" length(axlDBGetDesign()->components))')
    print(r.read("port.txt"))
    lv.send("zoom fit")               # любая команда строки Allegro

Канал описан у Cadence (share/pcb/examples/wm_copydata/allegro_sendcmd.c) и
проверен на 17.2. Его свойства определяют всё устройство модуля
(knowledge/10_API/10-02, 30_ГРАБЛИ/30-05):

  * обратной связи нет: SendMessage возвращает 1, выполнилась команда или
    нет. Поэтому результат идёт через файлы: код задания пишет status.txt и
    маркер done, модуль их ждёт;
  * строка длиннее ~250 байт МОЛЧА теряется — send() проверяет длину, а
    run() шлёт только короткое skill load("<папка>/job.il");
  * текст 8-битный: кодируется в cp1251, кириллица в путях проходит;
  * пока в Allegro открыт модальный диалог, SendMessage не возвращается
    вовсе — поэтому SendMessageTimeout, и таймаут означает «Allegro занят»;
  * окно ищется по заголовку «Продукт: плата.brd», а не по подстроке
    «Allegro»: так же называется и диалог, и пример Cadence в него попадает.

Правка в живом режиме идёт в транзакции (edit=True): ошибка откатывает
изменения. Сохранять плату — решение человека; модуль её не сохраняет и
Allegro не закрывает: «exit» в GUI открывает диалог, на который канал
ответить не может.
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import time

from . import batch, env

MAGIC = 0x26297811
WM_COPYDATA = 0x004A
SMTO_ABORTIFHUNG = 0x0002
MAX_CMD = 250          # байт вместе с завершающим нулём; 259 уже теряется

_user32 = ctypes.windll.user32
_TITLE = re.compile(r"^(?P<product>[^:]+):\s+(?P<design>[^\s].*?"
                    r"\.(?:brd|dra|mcm|sip|pad))\b", re.I)


class _CDS(ctypes.Structure):
    _fields_ = [("dwData", ctypes.c_size_t), ("cbData", wt.DWORD),
                ("lpData", ctypes.c_void_p)]


class AllegroBusy(RuntimeError):
    pass


def windows():
    """Главные окна Allegro: [(hwnd, продукт, плата, pid, заголовок)]."""
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if not _user32.IsWindowVisible(h):
            return True
        n = _user32.GetWindowTextLengthW(h)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(h, buf, n + 1)
        m = _TITLE.match(buf.value)
        if m:
            pid = wt.DWORD()
            _user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            out.append((h, m.group("product").strip(), m.group("design"),
                        pid.value, buf.value))
        return True

    _user32.EnumWindows(cb, 0)
    return out


def _process_image(pid):
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value
        return ""
    finally:
        k32.CloseHandle(h)


def allegro_dialogs():
    """Видимые окна процессов allegro.exe, не являющиеся главным окном с
    платой: [(hwnd, pid, заголовок)].

    Нужна, когда Live() создать нельзя: Allegro при запуске висит на
    вопросе (например, об обновлении формата старой платы), и окна
    «Продукт: плата.brd» ещё нет (knowledge/30_ГРАБЛИ/30-09).
    """
    out = []
    names = {}

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if not _user32.IsWindowVisible(h):
            return True
        n = _user32.GetWindowTextLengthW(h)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(h, buf, n + 1)
        pid = wt.DWORD()
        _user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value not in names:
            names[pid.value] = os.path.basename(
                _process_image(pid.value)).lower()
        if names[pid.value] == "allegro.exe" and \
                not _TITLE.match(buf.value) and \
                not re.match(r"^\S.*\d+\.\d+ \(S\d+\)$", buf.value):
            out.append((h, pid.value, buf.value))
        return True

    _user32.EnumWindows(cb, 0)
    return out


class Live:
    """Подключение к запущенному Allegro."""

    def __init__(self, hwnd=None, design=None):
        wins = windows()
        if hwnd is not None:
            wins = [w for w in wins if w[0] == hwnd]
        if design is not None:
            wins = [w for w in wins if w[2].lower() == design.lower()]
        if not wins:
            raise RuntimeError("не найдено окно Allegro с открытой платой "
                               "(заголовок «Продукт: плата.brd»)")
        if len(wins) > 1:
            raise RuntimeError("окон Allegro несколько, уточните design=: %s"
                               % ", ".join(w[2] for w in wins))
        self.hwnd, self.product, self.design, self.pid, self.title = wins[0]

    def alive(self):
        return bool(_user32.IsWindow(self.hwnd))

    def send(self, cmd, timeout_ms=5000):
        """Отправить одну строку команд Allegro (как в его командной строке).

        Выполнение не подтверждается — только доставка.
        """
        data = cmd.encode("cp1251") + b"\0"
        if len(data) > MAX_CMD:
            raise ValueError("команда %d байт длиннее %d: Allegro её молча "
                             "потеряет. Вынесите код в файл и шлите "
                             "skill load(...)" % (len(data), MAX_CMD))
        buf = ctypes.create_string_buffer(data)
        cds = _CDS(MAGIC, len(data), ctypes.cast(buf, ctypes.c_void_p))
        res = ctypes.c_size_t()
        f = _user32.SendMessageTimeoutW
        f.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p, wt.UINT,
                      wt.UINT, ctypes.POINTER(ctypes.c_size_t)]
        f.restype = ctypes.c_ssize_t
        ok = f(self.hwnd, WM_COPYDATA, 0, ctypes.byref(cds),
               SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(res))
        if not ok:
            raise AllegroBusy("Allegro не принял команду за %d мс: открыт "
                              "модальный диалог или идёт долгая операция"
                              % timeout_ms)
        return res.value

    def run(self, code, edit=False, outputs=(), timeout=120):
        """Выполнить код SKILL в открытом Allegro, дождаться итога.

        edit=True — в транзакции (ошибка откатывает правку). Возвращает
        batch.Result; ok=True только при записанном OK и всех outputs.
        """
        job_dir = env.new_job_dir("live")
        batch.write_job(job_dir, code, edit, None, expect=None)
        cmd = 'skill load("%s")' % env.skill_path(
            os.path.join(job_dir, "job.il"))
        res = batch.Result(job_dir)
        res.product = self.product
        t0 = time.time()
        self.send(cmd)
        done = res.path("done")
        while not os.path.exists(done):
            if time.time() - t0 > timeout:
                res.message = ("нет ответа за %d с: команда потерялась, "
                               "Allegro занят или код завис" % timeout)
                res.elapsed = time.time() - t0
                return res
            time.sleep(0.1)
        time.sleep(0.05)
        res.elapsed = time.time() - t0
        text = res.read("status.txt")
        res.status = text.split("\n", 1)[0].strip()
        res.message = text.split("\n", 1)[1] if "\n" in text else ""
        missing = [o for o in outputs if not os.path.exists(res.path(o))]
        if missing:
            res.message += "\nнет выходных файлов: %s" % ", ".join(missing)
        res.ok = res.status == "OK" and not missing
        return res

    # --- модальные диалоги -------------------------------------------------

    def dialogs(self):
        """Видимые окна процесса Allegro, кроме главного: [(hwnd, заголовок)].

        Непустой список почти всегда значит модальный вопрос, который
        блокирует канал: обновление формата старой платы, «сохранить
        изменения?» и т. п. (knowledge/30_ГРАБЛИ/30-05).
        """
        out = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cb(h, _):
            pid = wt.DWORD()
            _user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value == self.pid and h != self.hwnd and \
                    _user32.IsWindowVisible(h):
                n = _user32.GetWindowTextLengthW(h)
                buf = ctypes.create_unicode_buffer(n + 1)
                _user32.GetWindowTextW(h, buf, n + 1)
                if buf.value:
                    out.append((h, buf.value))
            return True

        _user32.EnumWindows(cb, 0)
        return out

    @staticmethod
    def snapshot(hwnd, path):
        """Снимок окна в PNG (PrintWindow). Для диалогов — чтобы прочитать
        вопрос. Холст платы так не снимается: выходит белым."""
        from PIL import Image
        gdi32 = ctypes.windll.gdi32
        r = wt.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        hdc = _user32.GetWindowDC(hwnd)
        mdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(mdc, bmp)
        _user32.PrintWindow(hwnd, mdc, 2)

        class BIH(ctypes.Structure):
            _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG),
                        ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                        ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                        ("biSizeImage", wt.DWORD),
                        ("biXPelsPerMeter", wt.LONG),
                        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                        ("biClrImportant", wt.DWORD)]
        bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        _user32.ReleaseDC(hwnd, hdc)
        Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).save(path)
        return path

    @staticmethod
    def press_default(hwnd):
        """Нажать в диалоге кнопку по умолчанию (Enter адресно в окно, без
        эмуляции ввода на весь стол). Сначала ПРОЧИТАТЬ диалог: snapshot()."""
        _user32.PostMessageW(hwnd, 0x0100, 0x0D, 0x001C0001)   # WM_KEYDOWN
        _user32.PostMessageW(hwnd, 0x0101, 0x0D, 0xC01C0001)   # WM_KEYUP

    def dump(self, figures=True, timeout=300):
        """Выгрузить открытую плату (как board.dump, но из GUI)."""
        from .board import read_jsonl
        r = self.run('akDumpBoard(strcat(akOut "dump.jsonl") %s)'
                     % ("t" if figures else "nil"),
                     outputs=["dump.jsonl"], timeout=timeout)
        r.check()
        b = read_jsonl(r.path("dump.jsonl"))
        b.source = self.design
        b.job = r
        return b

    def __repr__(self):
        return "<Live %s: %s hwnd=0x%x>" % (self.product, self.design,
                                            self.hwnd)
