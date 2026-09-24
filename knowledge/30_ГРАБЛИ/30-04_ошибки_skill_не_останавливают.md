---
id: 30-04
title: Ошибка SKILL не останавливает сценарий и не меняет код возврата; errset вокруг load отдаёт только обёртку «error while loading file»
tags: [skill, ошибка, errset, load, журнал, код возврата]
applies_to: Allegro 17.2-S066, пакетный и живой режимы
status: проверено
verified: 2026-09-24 — нарочно неверные вызовы в сценарии и в коде задания
source: эксперимент
---

# Ошибки SKILL молчат

## Что происходит

Сценарий из четырёх строк `skill`: неизвестная функция, `car(1)`,
`printf`, запись в файл. Первые две дают в журнале

```
(00:00:04) *Error* eval: undefined function - akNoSuchFunction
(00:00:04) ERROR
(00:00:04) *Error* car: argument #1 should be a list …
```

— и сценарий **идёт дальше**: `printf` и запись файла выполнены, `exit`,
код возврата 0. В stdout пакетного режима те же ошибки идут с префиксом
`E- `.

Если код задания загружается через `errset(load(file) t)`, то
`errset.errset` содержит только обёртку:

```
("load" 0 t nil ("*Error* load: error while loading file - \"…/user.il\" at line 1"))
```

— настоящая причина (`undefined function - …`) лишь в журнале, строкой
выше.

## Как правильно

* Итог задания пишет сам код: `errset` вокруг всего кода, статус в файл,
  маркер завершения — в alkit это `akJob`. Код возврата Allegro не
  используется.
* При статусе ERR показывать и `errset.errset`, и строки `*Error*` журнала
  (`Result.message` в alkit собирает оба).
* Правка — в транзакции: при ошибке `axlDBTransactionRollback`, иначе
  половина правки останется в плате.

## Как неправильно

```python
p = subprocess.run([allegro, "-nographic", ..., "-s", scr, brd])
assert p.returncode == 0          # ничего не проверяет
```

## Чем подтверждено

24.09.2026: сценарий выше — файл после ошибок создан, код 0. Задание
`akNoSuch(1)` через `ak.run` — статус ERR, в `errset` обёртка `load`,
причина — в журнале.
