# -*- coding: utf-8 -*-
"""Живой режим — РУЧНАЯ проверка: нужен открытый Allegro с платой.

    1. Скопировать демо-плату в любую папку и открыть её в Allegro
       (на вопрос об обновлении формата ответить «Да»).
    2. python tests\\test_live.py

Проверяет: поиск окна, выгрузку, правку в транзакции, откат по ошибке,
отказ длинной команды. Плату НЕ сохраняет — закройте Allegro без
сохранения.
"""
import sys

from _common import start

ak = start("test_live")
lv = ak.Live()
print(lv, "диалоги:", lv.dialogs())

b = lv.dump(figures=False)
print(b)
s = b.sym("C11")
x0, y0 = s["xy"]
r = ak.Report("живой режим")
r.truth("выгрузка есть", len(b.comps) > 0, "%d компонентов" % len(b.comps))

lv.run('akPlace("C11" %r %r)' % (x0 + 1.0, y0 + 1.0), edit=True).check()
b2 = lv.dump(figures=False)
r.close_to("C11 сдвинут по X", b2.sym("C11")["xy"][0], x0 + 1.0, tol=1e-6)

bad = lv.run('akPlace("C11" 0.0 0.0)\nakNoSuchFunction(1)', edit=True)
b3 = lv.dump(figures=False)
r.truth("ошибка поймана", not bad.ok)
r.equal("откат: C11 не ушёл в (0 0)", b3.sym("C11")["xy"],
        b2.sym("C11")["xy"])

lv.run('akPlace("C11" %r %r)' % (x0, y0), edit=True).check()
refused = False
try:
    lv.send("skill load(\"%s\")" % ("x" * 300))
except ValueError:
    refused = True
r.truth("длинная команда отвергнута до отправки", refused)
lv.send("zoom fit")
sys.exit(0 if r.done() else 1)
