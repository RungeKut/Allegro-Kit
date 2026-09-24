# dsn_dump.tcl — выгрузка схемы OrCAD Capture (.dsn) в JSON Lines.
#
# Запуск (делает alkit.capture):
#     <cdsroot>/tools/bin/tclsh.exe dsn_dump.tcl <in.dsn> <out.jsonl>
# рабочая папка — <cdsroot>/tools/bin (рядом лежат зависимые DLL).
#
# Capture запускать не нужно: база схемы читается библиотекой
# orDb_Dll_Tcl64.dll напрямую (knowledge/10_API/10-03).
#
# Записи:
#   {"t":"design","name":...}
#   {"t":"page","schematic":...,"page":...}
#   {"t":"part","refdes":...,"partref":...,"value":...,"footprint":...,
#    "page":...,"pins":[[номер,имя,цепь],...]}
#   {"t":"occ","refdes":...,"partref":...,"value":...,"footprint":...,
#    "path":...,"depth":N} — вхождение элемента (истинные refdes в иерархии;
#    refdes — обозначение корпуса «J6», partref — секции «J6A»)
#   {"t":"flatnet","name":...}
#   {"t":"end"}

set dsn [lindex $argv 0]
set outp [lindex $argv 1]
set cds [file normalize [file join [file dirname [info nameofexecutable]] .. ..]]
load [file join $cds tools bin orDb_Dll_Tcl64.dll] DboTclWriteBasic

set out [open $outp w]
fconfigure $out -encoding utf-8 -translation lf

proc js {s} {
    return "\"[string map {\\ \\\\ \" \\\" \n \\n \r \\r \t \\t} $s]\""
}
proc cs {c} { return [DboTclHelper_sGetConstCharPtr $c] }
proc rec {kind pairs} {
    global out
    set parts [list "\"t\":[js $kind]"]
    foreach {k v} $pairs { lappend parts "[js $k]:$v" }
    puts $out "\{[join $parts ,]\}"
}

set st [DboState]
set ses [DboTclHelper_sCreateSession]
set des [$ses GetDesignAndSchematics [DboTclHelper_sMakeCString $dsn] $st]
if {$des == "NULL" || [$st Failed]} {
    rec error [list msg [js "не открывается $dsn"]]
    close $out
    exit 2
}
# плоские цепи появляются только после GetRootOccurrence
set root [$des GetRootOccurrence $st]
set nm [DboTclHelper_sMakeCString]
$des GetName $nm
rec design [list name [js [cs $nm]]]

set sIter [$des NewViewsIter $st $::IterDefs_SCHEMATICS]
set sch [$sIter NextView $st]
while {$sch != "NULL"} {
    set sch [DboViewToDboSchematic $sch]
    $sch GetName $nm
    set sname [cs $nm]
    set pIter [$sch NewPagesIter $st]
    set pg [$pIter NextPage $st]
    while {$pg != "NULL"} {
        $pg GetName $nm
        set pname [cs $nm]
        rec page [list schematic [js $sname] page [js $pname]]
        set iIter [$pg NewPartInstsIter $st]
        set inst [$iIter NextPartInst $st]
        while {$inst != "NULL"} {
            set pl [DboPartInstToDboPlacedInst $inst]
            if {$pl != "NULL"} {
                # GetReferenceDesignator — Part Reference («DA1-1» у секции);
                # обозначение корпуса, как на плате, — свойство Reference
                set pr [DboTclHelper_sMakeCString]
                $pl GetReferenceDesignator $pr
                set rd [DboTclHelper_sMakeCString]
                $pl GetEffectivePropStringValue \
                    [DboTclHelper_sMakeCString "Reference"] $rd
                set val [DboTclHelper_sMakeCString]
                $pl GetPartValue $val
                set fp [DboTclHelper_sMakeCString]
                $pl GetEffectivePropStringValue \
                    [DboTclHelper_sMakeCString "PCB Footprint"] $fp
                set pins {}
                set pinIter [$pl NewPinsIter $st]
                set pin [$pinIter NextPin $st]
                while {$pin != "NULL"} {
                    set pnum [DboTclHelper_sMakeCString]
                    $pin GetPinNumber $pnum
                    set pnam [DboTclHelper_sMakeCString]
                    $pin GetPinName $pnam
                    set net [$pin GetNet $st]
                    set netn null
                    if {$net != "NULL"} {
                        set nn [DboTclHelper_sMakeCString]
                        $net GetNetName $nn
                        set netn [js [cs $nn]]
                    }
                    lappend pins "\[[js [cs $pnum]],[js [cs $pnam]],$netn\]"
                    set pin [$pinIter NextPin $st]
                }
                delete_DboPartInstPinsIter $pinIter
                rec part [list refdes [js [cs $rd]] partref [js [cs $pr]] \
                    value [js [cs $val]] \
                    footprint [js [cs $fp]] page [js $pname] \
                    pins "\[[join $pins ,]\]"]
            }
            set inst [$iIter NextPartInst $st]
        }
        delete_DboPagePartInstsIter $iIter
        set pg [$pIter NextPage $st]
    }
    delete_DboSchematicPagesIter $pIter
    set sch [$sIter NextView $st]
}
delete_DboLibViewsIter $sIter

# Вхождения. В иерархической схеме позиционные обозначения, номиналы и
# посадочные места живут во вхождениях, а на листах блоков стоят «U?», «R?».
# Лист дерева вхождений — элемент (или его секция); depth > 0 — элемент
# внутри иерархического блока.
proc walk {occ depth} {
    set st [DboState]
    set it [$occ NewChildrenIter $st $::IterDefs_INSTS]
    set ch [$it NextOccurrence $st]
    while {$ch != "NULL"} {
        set io [DboOccurrenceToDboInstOccurrence $ch]
        set sub [$io NewChildrenIter $st $::IterDefs_INSTS]
        set has [expr {[$sub NextOccurrence $st] != "NULL"}]
        delete_DboOccurrenceChildrenIter $sub
        if {$has} {
            walk $io [expr {$depth + 1}]
        } else {
            set rd [DboTclHelper_sMakeCString]
            $io GetReferenceDesignator $rd
            set v [DboTclHelper_sMakeCString]
            $io GetEffectivePropStringValue [DboTclHelper_sMakeCString "Value"] $v
            set f [DboTclHelper_sMakeCString]
            $io GetEffectivePropStringValue \
                [DboTclHelper_sMakeCString "PCB Footprint"] $f
            # GetReferenceDesignator отдаёт Part Reference — у секции это
            # «J6A»; обозначение корпуса, как на плате, — свойство Reference
            set rf [DboTclHelper_sMakeCString]
            $io GetEffectivePropStringValue \
                [DboTclHelper_sMakeCString "Reference"] $rf
            set pn [DboTclHelper_sMakeCString]
            $io GetPathName $pn
            rec occ [list refdes [js [cs $rf]] partref [js [cs $rd]] \
                value [js [cs $v]] footprint [js [cs $f]] \
                path [js [cs $pn]] depth $depth]
        }
        set ch [$it NextOccurrence $st]
    }
    delete_DboOccurrenceChildrenIter $it
}
walk $root 0

set fIter [$des NewFlatNetsIter $st]
set fn [$fIter NextFlatNet $st]
while {$fn != "NULL"} {
    $fn GetName $nm
    rec flatnet [list name [js [cs $nm]]]
    set fn [$fIter NextFlatNet $st]
}
delete_DboDesignFlatNetsIter $fIter

rec end {}
close $out
$ses RemoveDesign $des
DboTclHelper_sDeleteSession $ses
exit 0
