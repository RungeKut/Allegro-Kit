---
id: 10-03
title: Схема .dsn читается штатным tclsh с orDb_Dll_Tcl64.dll без запуска Capture; обозначение корпуса — свойство Reference, а не GetReferenceDesignator
tags: [capture, orcad, dsn, tcl, схема, вхождения, иерархия]
applies_to: Cadence SPB 17.2-S066 (OrCAD Capture 17.2), tclsh 8.6 из tools/bin
status: проверено
verified: 2026-09-24 — плоская схема на 1 лист и иерархическая демо-схема на 21 лист, сверка с платами
source: эксперимент; образцы doc/orctclsample
---

# Схемы Capture через TCL

## Что происходит

Файл `.dsn` — составной OLE-документ; читать его надо API Capture. Для
этого **не нужен ни запущенный Capture, ни лицензия** (на этой машине
отказа ни разу не было): штатный `tools/bin/tclsh.exe` загружает
`orDb_Dll_Tcl64.dll` и открывает базу напрямую. Плоская схема на 1 лист
читается за 0.3 с, иерархическая на 21 лист — за 0.6 с.

## Как правильно

```tcl
load {C:/Cadence/SPB_17.2/tools/bin/orDb_Dll_Tcl64.dll} DboTclWriteBasic
set st  [DboState]
set ses [DboTclHelper_sCreateSession]
set des [$ses GetDesignAndSchematics [DboTclHelper_sMakeCString $path] $st]
set root [$des GetRootOccurrence $st]     ;# без него нет плоских цепей
```

Рабочая папка процесса — `tools/bin` (рядом зависимые DLL). Строки API —
объекты CString: `DboTclHelper_sMakeCString`, читать через
`DboTclHelper_sGetConstCharPtr`. Итераторы: `NewViewsIter` →
`DboViewToDboSchematic` → `NewPagesIter` → `NewPartInstsIter` →
`DboPartInstToDboPlacedInst` → `NewPinsIter` → `$pin GetNet` →
`GetNetName`. Плоские цепи — `NewFlatNetsIter`.

Готовая выгрузка в JSON Lines — `alkit/tcl/dsn_dump.tcl`, из Python —
`ak.read_dsn(path)`.

### Два источника обозначений — путать нельзя

| | экземпляр на листе (`part`) | вхождение (`occ`) |
|---|---|---|
| как получить | `NewPartInstsIter` по листам | рекурсивно `NewChildrenIter $::IterDefs_INSTS` от корня |
| обозначение в иерархии | «U?», «R?» — настоящих там нет | настоящее |
| цепи выводов | есть (цепи листа) | через вхождения портов не получены |

В иерархической схеме обозначения, номиналы и посадочные места брать из
вхождений (`GetEffectivePropStringValue` на вхождении), цепи выводов —
только для плоской схемы.

### Reference и Part Reference

`GetReferenceDesignator` возвращает **Part Reference** — обозначение
секции: «J6A», «DA1-1». Обозначение корпуса, как на плате, — свойство
**Reference**:

```tcl
set rf [DboTclHelper_sMakeCString]
$inst GetEffectivePropStringValue [DboTclHelper_sMakeCString "Reference"] $rf
```

## Как неправильно

* Взять `GetReferenceDesignator` за обозначение: у многосекционного
  элемента сверка со платой покажет «лишние J6A, J6B» и «нет J6».
* Сверять с платой количество экземпляров: секции дают несколько записей
  на один корпус, а элементы для моделирования (источники) и элементы без
  посадочного места на плату не попадают.
* Ждать от символа схемы все выводы корпуса: скрытые выводы питания,
  сдвоенные площадки корпуса («1_1» рядом с «1») и крепёжные площадки есть
  только на плате ([20-03](../20_ПРИЁМЫ/20-03_сверка_схемы_с_платой.md)).

## Чем подтверждено

24.09.2026. Демо-схема `share/orcad/examples/pcbdesign/pcbdemo1/DEMOJ.Dsn`:
по листам 383 экземпляра и 212 обозначений с «U?»; по вхождениям через
`GetReferenceDesignator` — 389 обозначений вида «J6A»; через `Reference` —
356, из них 351 совпали с платой, 5 лишних — источники для моделирования и
элементы без посадочного места. Плоская схема с двухсекционным элементом:
`GetReferenceDesignator` дал обозначения секций вида «DA1-1», «DA1-2»;
после перехода на `Reference` обозначения совпали с платой все.
