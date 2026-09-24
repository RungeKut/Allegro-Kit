; alkit.il — SKILL-часть набора Allegro-Kit.
;
; Загружается перед каждым заданием — и в пакетном режиме (allegro -nographic),
; и в живом (WM_COPYDATA в запущенный Allegro). Все имена начинаются с ak,
; чтобы не столкнуться с чужими функциями, загруженными из allegro.ilinit.
;
; Вывод — JSON Lines: одна запись на строку, {"t":"тип", ...}. Строки пишутся
; в кодировке Allegro (cp1251 на русской Windows); Python читает их так же.
;
; Проверенное поведение и ловушки — knowledge/ (начинать с INDEX.md).

; ---------------------------------------------------------------------------
; JSON
; ---------------------------------------------------------------------------

procedure(akJStr(s)
  ; строка JSON с экранированием; не строка — через печатное представление
  let((out c n i)
    unless(stringp(s) s = sprintf(nil "%L" s))
    if(!(index(s "\"") || index(s "\\") || index(s "\n") || index(s "\t"))
    then
      strcat("\"" s "\"")
    else
      out = "\""
      n = strlen(s)
      for(i 1 n
        c = substring(s i 1)
        cond(
          ((c == "\"") out = strcat(out "\\\""))
          ((c == "\\") out = strcat(out "\\\\"))
          ((c == "\n") out = strcat(out "\\n"))
          ((c == "\t") out = strcat(out "\\t"))
          (t out = strcat(out c))))
      strcat(out "\""))))

procedure(akJ(v)
  ; любое значение SKILL -> текст JSON
  cond(
    ((null v) "null")
    ((eq v t) "true")
    ((stringp v) akJStr(v))
    ((fixp v) sprintf(nil "%d" v))
    ((floatp v) sprintf(nil "%.6f" v))
    ((symbolp v) akJStr(get_pname(v)))
    ((listp v) strcat("[" buildString(mapcar('akJ v) ",") "]"))
    (t akJStr(sprintf(nil "%L" v)))))

procedure(akRec(port kind pairs)
  ; одна запись JSON Lines: pairs — список (ключ значение)
  fprintf(port "{\"t\":%s" akJStr(kind))
  foreach(kv pairs
    fprintf(port ",%s:%s" akJStr(car(kv)) akJ(cadr(kv))))
  fprintf(port "}\n"))

; ---------------------------------------------------------------------------
; мелочи
; ---------------------------------------------------------------------------

procedure(akNetName(fig)
  ; имя цепи фигуры. У фигур на пустой цепи net — строка "", а не объект:
  ; прямое fig->net->name на ней падает.
  let((n)
    n = fig->net
    if(n && !stringp(n) then n->name else nil)))

procedure(akFindSym(refdes)
  car(setof(s axlDBGetDesign()->symbols s->refdes == refdes)))

; ---------------------------------------------------------------------------
; выгрузка платы
; ---------------------------------------------------------------------------

procedure(akShapePts(o)
  ; вершины внешнего контура полигона (как отдаёт axlPolyFromDB)
  let((r)
    r = errset(axlPolyFromDB(o))
    when(r && car(r) && car(car(r))
      car(car(r))->vertices)))

procedure(akDumpSeg(p s owner)
  akRec(p "seg" list(
    list("layer" s->layer || owner->layer)
    list("etch" s->isEtch)
    list("net" akNetName(owner))
    list("w" s->width)
    list("se" s->startEnd)
    list("arc" when(s->objType == "arc" list(s->xy s->isClockwise))))))

procedure(akDumpFig(p o)
  let((ty)
    ty = o->objType
    cond(
      ((ty == "path")
        foreach(s o->segments akDumpSeg(p s o)))
      ((ty == "line" || ty == "arc")
        akDumpSeg(p o o))
      ((ty == "via")
        akRec(p "via" list(
          list("xy" o->xy)
          list("net" akNetName(o))
          list("pad" when(o->definition o->definition->name))
          list("bbox" o->bBox))))
      ((ty == "shape")
        akRec(p "shape" list(
          list("kind" ty)
          list("layer" o->layer)
          list("net" akNetName(o))
          list("fill" if(o->fill t nil))
          list("bbox" o->bBox)
          list("pts" akShapePts(o)))))
      ((ty == "polygon")
        ; незаполненный многоугольник — так бывает задан контур платы.
        ; ->vertices у него nil (проверено), зато есть ->segments и
        ; axlPolyFromDB. Сегменты пишутся ещё и отдельно: по ним рисуется
        ; и проверяется контур.
        akRec(p "shape" list(
          list("kind" ty)
          list("layer" o->layer)
          list("net" akNetName(o))
          list("fill" nil)
          list("bbox" o->bBox)
          list("pts" o->vertices || akShapePts(o))))
        foreach(s o->segments akDumpSeg(p s o)))
      (t
        akRec(p "other" list(
          list("type" ty) list("layer" o->layer) list("bbox" o->bBox)))))))

procedure(akDumpFigures(p)
  ; все проводники, линии, переходные и полигоны на всех слоях.
  ; Выбор через фильтр поиска видит только видимые слои, поэтому видимость
  ; на время включается целиком и потом возвращается как была.
  let((vis objs)
    vis = axlVisibleGet()
    axlVisibleDesign(t)
    axlClearSelSet()
    axlSetFindFilter(?enabled list("noall" "clines" "lines" "vias" "shapes")
                     ?onButtons list("noall" "clines" "lines" "vias" "shapes"))
    axlAddSelectAll()
    objs = axlGetSelSet()
    axlClearSelSet()
    foreach(o objs akDumpFig(p o))
    when(vis axlVisibleSet(vis))
    length(objs)))

procedure(akDumpBoard(path @optional (figures t))
  ; Полная выгрузка открытой платы в JSON Lines.
  ; Координаты и размеры — в единицах платы (запись design, поле units).
  let((p d dp n)
    p = outfile(path "w")
    unless(p error("akDumpBoard: не открывается файл %s" path))
    d = axlDBGetDesign()
    dp = axlGetParam("paramDesign")
    akRec(p "design" list(
      list("name" axlCurrentDesign())
      list("units" dp->units)
      list("accuracy" dp->accuracy)
      list("extents" dp->bBox)
      list("outline" when(d->designOutline d->designOutline->bBox))
      list("drcState" d->drcState)))
    n = 0
    foreach(l axlGetParam("paramLayerGroup:ETCH")->groupMembers
      akRec(p "layer" list(list("name" l) list("index" n)))
      n++)
    foreach(c d->components
      akRec(p "comp" list(
        list("refdes" c->name)
        list("device" c->deviceType)
        list("package" c->package)
        list("class" c->class)
        list("value" c->prop->VALUE)
        list("placed" if(c->symbol t nil)))))
    foreach(s d->symbols
      akRec(p "sym" list(
        list("refdes" s->refdes)
        list("name" s->name)
        list("type" s->type)
        list("xy" s->xy)
        list("rot" s->rotation)
        list("mirror" s->isMirrored)
        list("bbox" s->bBox)))
      foreach(pin s->pins
        akRec(p "pin" list(
          list("refdes" s->refdes)
          list("number" pin->number)
          list("xy" pin->xy)
          list("net" akNetName(pin))
          list("pad" pin->name)
          list("through" pin->isThrough)
          list("bbox" pin->bBox)))))
    foreach(net d->nets
      akRec(p "net" list(
        list("name" net->name)
        list("unconnected" net->unconnected)
        list("unplaced" net->unplaced)
        list("branches" net->nBranches))))
    foreach(x d->drcs
      akRec(p "drc" list(
        list("name" x->name) list("type" x->type) list("xy" x->xy)
        list("actual" x->actual) list("expected" x->expected))))
    when(figures akDumpFigures(p))
    akRec(p "end" list(list("ok" t)))
    close(p)
    t))

; ---------------------------------------------------------------------------
; правка
; ---------------------------------------------------------------------------

procedure(akPlace(refdes x y @optional rot mirror)
  ; Поставить компонент: (x y) — абсолютная точка привязки символа, единицы
  ; платы (nil — координату не менять); rot — абсолютный угол, градусы
  ; (nil — не трогать); mirror — 'top/'bottom (nil — не трогать).
  ; Порядок: сторона, перенос, поворот. Возвращает символ после правки.
  let((s r want)
    s = akFindSym(refdes)
    unless(s error("akPlace: нет символа %s" refdes))
    unless(x x = car(s->xy))
    unless(y y = cadr(s->xy))
    when(mirror
      want = (mirror == 'bottom)
      when(want != (s->isMirrored && t)
        r = axlTransformObject(s ?mirror t ?origin s->xy)
        unless(r error("akPlace: отражение %s отвергнуто" refdes))
        s = akFindSym(refdes)))
    when(abs(x - car(s->xy)) > 1e-9 || abs(y - cadr(s->xy)) > 1e-9
      r = axlTransformObject(s ?move list(x - car(s->xy) y - cadr(s->xy)))
      unless(r error("akPlace: перенос %s отвергнут" refdes))
      s = akFindSym(refdes))
    when(rot && abs(float(rot) - s->rotation) > 1e-6
      r = axlTransformObject(s ?angle float(rot) - s->rotation ?origin s->xy)
      unless(r error("akPlace: поворот %s отвергнут" refdes))
      s = akFindSym(refdes))
    s))

procedure(akText(text x y layer @optional (block "1") (rot 0.0) (justify "LEFT"))
  ; Текст на слое вида "BOARD GEOMETRY/SILKSCREEN_TOP". Возвращает dbid.
  let((r)
    r = axlDBCreateText(text list(float(x) float(y))
          make_axlTextOrientation(?textBlock block ?rotation float(rot)
                                  ?mirrored nil ?justify justify)
          layer nil)
    unless(r && car(r) error("akText: текст %L не создан" text))
    car(car(r))))

; ---------------------------------------------------------------------------
; задание
; ---------------------------------------------------------------------------

procedure(akJob(userPath statusPath donePath expectDesign editMode savePath)
  ; Выполнить код задания и записать итог.
  ;   expectDesign — имя платы, которая обязана быть открыта (nil — любая).
  ;     Allegro, не сумев открыть файл, молча начинает новую пустую плату,
  ;     и код задания отработал бы на ней: knowledge/30_ГРАБЛИ/30-02.
  ;   editMode — завернуть код в транзакцию: ошибка откатывает всю правку.
  ;   savePath — после успешной правки сохранить плату сюда (без .brd).
  ; Ошибки SKILL не останавливают сценарий Allegro, поэтому ловятся здесь
  ; через errset, а не по журналу.
  let((st r mark saved)
    st = outfile(statusPath "w")
    cond(
      ((expectDesign && axlCurrentDesign() != expectDesign)
        fprintf(st "ERR\nоткрыта не та плата: %L вместо %L\n"
                axlCurrentDesign() expectDesign))
      (t
        when(editMode mark = axlDBTransactionStart())
        r = errset(load(userPath) t)
        cond(
          (r
            when(mark axlDBTransactionCommit(mark))
            when(savePath
              saved = axlSaveDesign(?design savePath ?noConfirm t))
            if(savePath && !saved
            then fprintf(st "ERR\nсохранение не удалось: %s\n" savePath)
            else fprintf(st "OK\n%L\n" saved)))
          (t
            when(mark axlDBTransactionRollback(mark))
            fprintf(st "ERR\n%L\n" errset.errset)))))
    close(st)
    close(outfile(donePath "w"))
    t))
