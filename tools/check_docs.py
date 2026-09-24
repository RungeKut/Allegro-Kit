# -*- coding: utf-8 -*-
"""Проверка целостности базы знаний Allegro-Kit.

Выполняет раздел 9 файла knowledge/00_ПРАВИЛА.md:

  * у каждого файла базы есть шапка YAML с обязательными полями;
  * каждый файл присутствует в INDEX.md и наоборот;
  * нет двух файлов с одинаковым id;
  * id в шапке совпадает с именем файла;
  * записи со status: проверено имеют поле verified;
  * внутренние ссылки ведут на существующие файлы;
  * НИ ОДИН файл набора не упоминает изделие или посторонний проект;
  * на этой машине включён хук commit-msg, который проверяет текст коммита.

Стоп-слова берутся из двух файлов:
  tools/stoplist.txt        — общий, лежит в репозитории;
  tools/stoplist.local.txt  — приметы изделий этой машины, в .gitignore.
Названия изделий вписываются во ВТОРОЙ: публичный стоп-лист сам по себе
публикует то, что должен скрывать.

С ключом --project к стоп-словам добавляются имя папки проекта и имена
лежащих в ней файлов плат и схем.

Запуск:
    python tools/check_docs.py
    python tools/check_docs.py --project "D:\\путь\\к\\папке\\проекта"
"""
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWLEDGE = os.path.join(ROOT, "knowledge")
INDEX = os.path.join(KNOWLEDGE, "INDEX.md")

REQUIRED = ("id", "title", "status")
VALID_STATUS = ("проверено", "не проверено", "устарело", "действует")

STOPLISTS = (os.path.join(ROOT, "tools", "stoplist.txt"),
             os.path.join(ROOT, "tools", "stoplist.local.txt"))
SKIP = ("tools/stoplist.txt", "tools/stoplist.local.txt")
TEXT_EXT = (".md", ".py", ".ps1", ".txt", ".il", ".tcl", ".bat", ".cfg",
            ".toml", ".json", ".yml")
PROJECT_EXT = (".BRD", ".DSN", ".OPJ", ".SCH", ".DRA", ".PAD", ".DBK",
               ".PCB", ".MCM", ".SIP")
# слишком общие, чтобы быть приметой изделия
GENERIC = set("""board design project schematic test main build params kit
work temp data copy backup new old final
плата платы плате схема схемы проект проекта модуль блок версия копия
управления питания контроля""".split())


def read(path):
    return io.open(path, encoding="utf-8").read()


def front_matter(text):
    """Разобрать шапку YAML (плоскую)."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    out = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([a-zA-Z_]+):\s*(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"')
    return out


def knowledge_files():
    out = []
    for dirpath, _dirnames, filenames in os.walk(KNOWLEDGE):
        for fn in sorted(filenames):
            if fn.endswith(".md") and fn != "INDEX.md":
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def rel(path):
    return os.path.relpath(path, KNOWLEDGE).replace("\\", "/")


def hook_enabled():
    """Включён ли хук commit-msg (core.hooksPath = tools/hooks)."""
    try:
        out = subprocess.check_output(
            ["git", "config", "--get", "core.hooksPath"],
            cwd=ROOT, stderr=subprocess.DEVNULL)
        return out.decode("utf-8", "replace").strip().replace("\\", "/") \
            == "tools/hooks"
    except Exception:
        return False


def repo_files():
    """Все текстовые файлы набора, кроме служебных и самих стоп-листов."""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", ".venv")]
        for fn in sorted(filenames):
            if not fn.lower().endswith(TEXT_EXT):
                continue
            full = os.path.join(dirpath, fn)
            r = os.path.relpath(full, ROOT).replace(os.sep, "/")
            if r in SKIP:
                continue
            out.append(full)
    return sorted(out)


def stop_words():
    """Стоп-слова из tools/stoplist.txt и tools/stoplist.local.txt."""
    out = set()
    for path in STOPLISTS:
        if not os.path.exists(path):
            continue
        for line in read(path).splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out.add(line)
    return out


def project_words(project_dir):
    """Приметы изделия из папки проекта: её имя и имена плат и схем."""
    if not project_dir or not os.path.isdir(project_dir):
        return set()
    names = [os.path.basename(os.path.abspath(project_dir))]
    for fn in os.listdir(project_dir):
        stem, ext = os.path.splitext(fn)
        if ext.upper() in PROJECT_EXT:
            names.append(stem)
    out = set()
    for name in names:
        for token in re.split(r"[^0-9A-Za-zА-Яа-яЁё]+", name):
            if len(token) >= 4 and token.lower() not in GENERIC:
                out.add(token)
    return out


def main(project_dir=None):
    problems = []
    files = knowledge_files()
    ids = {}

    print("База знаний: %s" % KNOWLEDGE)
    print("Файлов найдено: %d" % len(files))
    print("Проверка на стоп-слова: %d файлов набора\n" % len(repo_files()))

    for path in files:
        r = rel(path)
        fm = front_matter(read(path))
        if fm is None:
            problems.append("%s: нет шапки YAML" % r)
            continue
        for field in REQUIRED:
            if field not in fm:
                problems.append("%s: в шапке нет поля %s" % (r, field))
        status = fm.get("status", "")
        if status and status not in VALID_STATUS:
            problems.append("%s: неизвестный status %r (допустимы: %s)"
                            % (r, status, ", ".join(VALID_STATUS)))
        if status == "проверено" and not fm.get("verified"):
            problems.append("%s: status «проверено», но нет поля verified — "
                            "запись не имеет силы (правило 3)" % r)
        if status == "проверено" and not fm.get("applies_to"):
            problems.append("%s: нет applies_to — неизвестно, на какой "
                            "версии проверено (правило 3)" % r)
        fid = fm.get("id", "")
        if fid:
            if fid in ids:
                problems.append("%s: id %s уже занят файлом %s"
                                % (r, fid, ids[fid]))
            else:
                ids[fid] = r
            base = os.path.basename(path)
            if not base.startswith(fid + "_") and base != "00_ПРАВИЛА.md":
                problems.append("%s: id %s не совпадает с именем файла"
                                % (r, fid))

    if not os.path.exists(INDEX):
        problems.append("нет INDEX.md")
    else:
        index_text = read(INDEX)
        linked = {l.replace("\\", "/") for l in
                  re.findall(r"\]\(([^)]+\.md)\)", index_text)}
        for path in files:
            if rel(path) not in linked:
                problems.append("%s: файла нет в INDEX.md (правило 5)"
                                % rel(path))
        existing = {rel(p) for p in files}
        for l in sorted(linked):
            if l not in existing and not l.startswith(".."):
                problems.append("INDEX.md ссылается на несуществующий %s" % l)
        # строка таблицы должна иметь столько ячеек, сколько заголовок:
        # слияние однажды склеило в одну строку две записи
        width = None
        for n, line in enumerate(index_text.splitlines(), 1):
            if not line.startswith("|"):
                width = None
                continue
            cells = line.count("|")
            if width is None:
                width = cells
            elif cells != width:
                problems.append("INDEX.md, строка %d: %d ячеек вместо %d — "
                                "таблица испорчена" % (n, cells - 1,
                                                        width - 1))

    for path in files:
        base = os.path.dirname(path)
        for link in re.findall(r"\]\(([^)]+\.md)\)", read(path)):
            if link.startswith("http"):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(base,
                                                                link))):
                problems.append("%s: битая ссылка -> %s" % (rel(path), link))

    project = project_words(project_dir)
    if project:
        print("Приметы изделия из папки проекта: %s\n"
              % ", ".join(sorted(project)))
    words = stop_words() | project
    if not os.path.exists(STOPLISTS[1]):
        print("Замечание: нет tools/stoplist.local.txt — приметы изделий "
              "этой машины не проверяются.\n")
    for path in repo_files():
        text = read(path).lower()
        r = os.path.relpath(path, ROOT).replace(os.sep, "/")
        for word in sorted(words):
            if word.lower() in text:
                problems.append("%s: упоминание изделия или постороннего "
                                "проекта %r (правило 1)" % (r, word))

    if not hook_enabled():
        problems.append(
            "хук commit-msg не включён на этой машине — текст коммита никто "
            "не проверяет. Лечится: git config core.hooksPath tools/hooks "
            "(её же делает setup.ps1)")

    if problems:
        print("РАСХОЖДЕНИЯ (%d):" % len(problems))
        for p in problems:
            print("  - " + p)
    else:
        print("Расхождений нет.")
    print("\nЗанятые id: %s" % ", ".join(sorted(ids)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    argv = sys.argv[1:]
    proj = None
    if "--project" in argv:
        i = argv.index("--project")
        if i + 1 >= len(argv):
            print("--project требует путь к папке проекта")
            sys.exit(2)
        proj = argv[i + 1]
    sys.exit(main(proj))
