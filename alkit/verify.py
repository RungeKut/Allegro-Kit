# -*- coding: utf-8 -*-
"""Проверка результата.

Главный принцип:

    ПЛАТА, КОТОРАЯ ОТКРЫЛАСЬ, — ЕЩЁ НЕ ПРАВИЛЬНАЯ ПЛАТА.

Скрипт, отработавший на молча открытой пустой плате; сдвиг в милах вместо
миллиметров; компонент, отражённый не на ту сторону; STEP без контура
платы — всё это даёт файл, который открывается. Ловится только сверкой с
независимым ожиданием.

Два уровня, нужны оба:
  числовой  — количества, координаты, DRC, связность, сверка со схемой
              (этот модуль);
  глазами   — картинка платы (модуль render).
"""


class Report:
    """Накопитель результатов проверки.

        r = Report("плата после расстановки")
        r.equal("компонентов", len(b.comps), 351)
        r.close_to("X DD1, мм", x, 40.0, tol=0.001)
        r.done()          # печатает и возвращает True/False
    """

    def __init__(self, name):
        self.name = name
        self.rows = []

    def _add(self, ok, what, got, expected, note=""):
        self.rows.append((bool(ok), what, got, expected, note))
        return bool(ok)

    def equal(self, what, got, expected):
        return self._add(got == expected, what, got, expected)

    def close_to(self, what, got, expected, tol=1e-6):
        if got is None or expected is None:
            return self._add(False, what, got, expected, "нет значения")
        d = abs(got - expected)
        return self._add(d <= tol, what, got, expected, "откл. %.4g" % d)

    def at_most(self, what, got, limit):
        return self._add(got is not None and got <= limit, what, got,
                         "<= %s" % limit)

    def truth(self, what, ok, note=""):
        return self._add(ok, what, "да" if ok else "нет", "да", note)

    def same_set(self, what, got, expected, show=8):
        """Сверка множеств с перечнем лишнего и недостающего."""
        got, expected = set(got), set(expected)
        extra = sorted(got - expected)
        lack = sorted(expected - got)
        note = ""
        if extra:
            note += "лишние: %s%s " % (", ".join(map(str, extra[:show])),
                                        " ..." if len(extra) > show else "")
        if lack:
            note += "нет: %s%s" % (", ".join(map(str, lack[:show])),
                                    " ..." if len(lack) > show else "")
        return self._add(not extra and not lack, what, len(got),
                         len(expected), note.strip())

    def skip(self, what, note=""):
        """Отметить проверку как НЕ ВЫПОЛНЕННУЮ: на итог не влияет, но
        печатается отдельно — непроверенное не должно выглядеть проверенным."""
        self.rows.append((None, what, "не проверено", "-", note))
        return None

    def note(self, what, text):
        """Сведение без оценки: на итог не влияет, печатается как ИНФО."""
        self.rows.append(("info", what, "-", "-", text))
        return None

    @property
    def ok(self):
        return all(r[0] for r in self.rows if r[0] in (True, False))

    @property
    def skipped(self):
        return [r[1] for r in self.rows if r[0] is None]

    def done(self, verbose=True):
        if verbose:
            print("\n%s" % self.name)
            for ok, what, got, expected, note in self.rows:
                if ok == "info":
                    print("  ИНФО  %-30s %s" % (what, note))
                    continue
                mark = "  ПРОПУСК" if ok is None else ("  OK  " if ok
                                                      else "  ОШИБКА")
                print("%s %-30s получено %-14s ожидалось %-14s %s"
                      % (mark, what, _fmt(got), _fmt(expected), note))
            tail = ""
            if self.skipped:
                tail = " (пропущено: %d)" % len(self.skipped)
            print("  итог: %s%s" % ("все проверки пройдены" if self.ok
                                    else "ЕСТЬ РАСХОЖДЕНИЯ", tail))
        return self.ok


def _fmt(v):
    if isinstance(v, float):
        return "%.6g" % v
    return str(v)


# ---------------------------------------------------------------------------

def check_board(board, name="плата", expect_components=None,
                expect_nets=None, max_drc=None, expect_units=None,
                expect_outline=None, tol=0.001, verbose=True):
    """Сверка выгрузки платы с ожиданием. None — пункт не проверять.

    expect_outline — ((x1 y1) (x2 y2)) контура в единицах платы.
    Незапрошенные пункты не печатаются: отчёт перечисляет только то, что
    проверено на самом деле.
    """
    r = Report(name)
    r.truth("выгрузка полная", board.complete and not board.bad_lines,
            "битых строк %d" % board.bad_lines)
    if expect_units is not None:
        r.equal("единицы", board.units, expect_units)
    if expect_components is not None:
        r.equal("компонентов", len(board.comps), expect_components)
    if expect_nets is not None:
        r.equal("цепей", len(board.nets), expect_nets)
    if max_drc is not None:
        r.at_most("нарушений DRC", len(board.drcs), max_drc)
    if expect_outline is not None:
        got = board.outline_bbox()
        if got is None:
            r._add(False, "контур платы", None, expect_outline, "нет контура")
        else:
            d = max(abs(a - b) for pa, pb in zip(got, expect_outline)
                    for a, b in zip(pa, pb))
            r._add(d <= tol, "контур платы", got, expect_outline,
                   "макс. откл. %.4g" % d)
    return r.done(verbose)


def _groups(pin_nets):
    """Разбиение выводов на цепи: множество frozenset((refdes, pin)).

    Сравниваются группы, а не имена: Allegro переводит имена цепей в верхний
    регистр, а безымянные цепи схемы (N01234) на плате могут называться
    иначе. Совпадение групп — это и есть совпадение связности.
    """
    by = {}
    for key, net in pin_nets.items():
        if net:
            by.setdefault(net.upper(), set()).add(key)
    return {frozenset(v) for v in by.values() if len(v) > 1}


def compare(sch, board, name="схема -> плата", ignore=(), verbose=True):
    """Сверка схемы Capture с платой Allegro.

    1) множества позиционных обозначений;
    2) посадочные места (PCB Footprint схемы против символа на плате,
       без учёта регистра);
    3) связность: разбиение выводов на цепи — только для плоской схемы.

    ignore — обозначения, которых на плате быть не должно (источники для
    моделирования, элементы без корпуса). Элементы схемы без посадочного
    места подсказываются в отчёте отдельно: чаще всего это они.
    """
    r = Report(name)
    ignore = set(ignore)
    sch_c = {k: v for k, v in sch.components().items() if k not in ignore}
    brd_refs = {c["refdes"] for c in board.comps}
    r.same_set("позиционные обозначения", set(sch_c), brd_refs)
    nofp = sorted(k for k in set(sch_c) - brd_refs
                  if not sch_c[k]["footprint"])
    if nofp:
        r.rows[-1] = r.rows[-1][:4] + (
            r.rows[-1][4] + "; из лишних без посадочного места: "
            + ", ".join(nofp),)

    sym_by_ref = {s["refdes"]: s["name"] for s in board.syms if s["refdes"]}
    bad = []
    for ref, c in sorted(sch_c.items()):
        if ref in sym_by_ref and c["footprint"] and \
                c["footprint"].upper() != sym_by_ref[ref].upper():
            bad.append("%s: %s / %s" % (ref, c["footprint"], sym_by_ref[ref]))
    r.truth("посадочные места совпадают", not bad,
            "; ".join(bad[:5]) + (" ..." if len(bad) > 5 else ""))

    if sch.hierarchical:
        r.skip("связность выводов",
               "схема иерархическая, цепи через вхождения не выгружаются")
        return r.done(verbose)

    # Сравниваются только выводы, известные обеим сторонам. У корпуса на
    # плате бывают выводы, которых нет в символе схемы: сдвоенные площадки
    # («1_1» рядом с «1»), крепёжные площадки, скрытые выводы питания
    # Capture. Их связь задаёт не схема, и в разбиение они не входят —
    # но перечисляются отдельной строкой, чтобы их было видно.
    common = set(sch_c) & brd_refs
    sp = {k: v for k, v in sch.pin_nets().items() if k[0] in common}
    bp = {k: v for k, v in board.pin_nets().items() if k[0] in common}
    both = set(sp) & set(bp)
    gs = _groups({k: sp[k] for k in both})
    gb = _groups({k: bp[k] for k in both})
    r._add(gs == gb, "связность (группы выводов)", len(gb), len(gs),
           "" if gs == gb else "различаются %d групп"
           % len(gs.symmetric_difference(gb)))
    only_b = sorted("%s.%s=%s" % (k[0], k[1], v) for k, v in bp.items()
                    if k not in sp and v)
    only_s = sorted("%s.%s=%s" % (k[0], k[1], v) for k, v in sp.items()
                    if k not in bp and v)
    if only_b:
        r.note("выводы с цепью только на плате",
               "%d: %s%s" % (len(only_b), ", ".join(only_b[:6]),
                             " ..." if len(only_b) > 6 else ""))
    if only_s:
        r._add(False, "выводы с цепью только в схеме", len(only_s), 0,
               ", ".join(only_s[:6]) + (" ..." if len(only_s) > 6 else ""))
    return r.done(verbose)
