# -*- coding: utf-8 -*-
"""Правка: перенос, поворот, смена стороны, текст; откат по ошибке.

    python tests\\test_edit.py

Результат сохраняется в папку с пробелом и кириллицей — так проверяется,
что путь человека до Allegro не доходит.
"""
import os
import sys

from _common import DEMO_BRD, OUT, mtime, start

ak = start("test_edit")
t0 = mtime(DEMO_BRD)
dst_dir = os.path.join(OUT, "правка платы")
dst = os.path.join(dst_dir, "после правки.brd")
if os.path.exists(dst):
    os.remove(dst)

b0 = ak.dump(DEMO_BRD, figures=False)
c11, r9, u3 = b0.sym("C11"), b0.sym("R9"), b0.sym("U3")
want_rot = 90.0 if abs(r9["rot"] - 90.0) > 1e-6 else 0.0
want_side = "top" if u3["mirror"] else "bottom"

res = ak.place(DEMO_BRD, {"C11": (10.0, 20.0),
                          "R9": (None, None, want_rot),
                          "U3": (None, None, None, want_side)},
               save_to=dst)
print(res)

b = ak.dump(dst, figures=False)
r = ak.Report("перечитка правки")
r.close_to("C11 X", b.sym("C11")["xy"][0], 10.0, tol=1e-6)
r.close_to("C11 Y", b.sym("C11")["xy"][1], 20.0, tol=1e-6)
r.close_to("R9 угол", b.sym("R9")["rot"], want_rot, tol=1e-6)
r.equal("R9 на месте", b.sym("R9")["xy"], r9["xy"])
r.equal("U3 сторона", "bottom" if b.sym("U3")["mirror"] else "top",
        want_side)
r.equal("компонентов", len(b.comps), len(b0.comps))

# ошибка в середине правки: транзакция откатывается, файл не пишется
bad = os.path.join(dst_dir, "не должно быть.brd")
if os.path.exists(bad):
    os.remove(bad)
failed = False
try:
    ak.edit(DEMO_BRD, 'akPlace("C11" 30.0 30.0)\nakNoSuchFunction(1)', bad)
except ak.JobError as e:
    failed = "undefined function" in str(e)
r.truth("ошибка правки поймана с причиной", failed)
r.truth("после ошибки файл не создан", not os.path.exists(bad))

# существующий файл без overwrite не перезаписывается
refused = False
try:
    ak.place(DEMO_BRD, {"C11": (11.0, 21.0)}, save_to=dst)
except FileExistsError:
    refused = True
r.truth("без overwrite перезаписи нет", refused)
r.truth("оригинал не изменён", mtime(DEMO_BRD) == t0)
ok = r.done()

# текст на шелкографии
txt = os.path.join(dst_dir, "с текстом.brd")
if os.path.exists(txt):
    os.remove(txt)
ak.edit(DEMO_BRD, 'akText("ALKIT_TEST" 0.0 0.0 '
        '"BOARD GEOMETRY/SILKSCREEN_TOP")', txt)
bt = ak.run(txt, 'foreach(x axlDBGetDesign()->text '
            'when(x->text == "ALKIT_TEST" fprintf(akPort "found")))',
            outputs=["port.txt"]).check()
rt = ak.Report("текст на шелкографии")
rt.equal("текст найден перечиткой", bt.read("port.txt"), "found")
ok &= rt.done()
sys.exit(0 if ok else 1)
