# -*- coding: utf-8 -*-
"""Проверка текста коммита на упоминание проектируемого изделия.

Вторая половина правила из knowledge/40_СРЕДА/40-02: check_docs.py сверяет
файлы набора, а сообщение коммита не видит ни один из них.

Запускается хуком tools/hooks/commit-msg, который включает setup.ps1
(git config core.hooksPath tools/hooks). Вручную:

    python tools/check_msg.py .git/COMMIT_EDITMSG

Стоп-слова — tools/stoplist.txt и tools/stoplist.local.txt. Если в конфиге
репозитория задана папка проекта, к ним добавляются её имя и имена плат и
схем в ней:

    git config alkit.project "D:/путь/к/папке/проекта"
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from check_docs import project_words, stop_words   # noqa: E402


def git_config(name):
    try:
        out = subprocess.check_output(["git", "config", "--get", name],
                                      cwd=ROOT, stderr=subprocess.DEVNULL)
        return out.decode("utf-8", "replace").strip()
    except Exception:
        return ""


def main(argv):
    if not argv:
        print("check_msg.py: нужен путь к файлу с текстом коммита")
        return 2
    path = argv[0]
    if not os.path.exists(path):
        print("check_msg.py: нет файла %s" % path)
        return 2
    lines = [l for l in io.open(path, encoding="utf-8", errors="replace")
             .read().splitlines() if not l.lstrip().startswith("#")]
    text = "\n".join(lines).lower()

    words = stop_words() | project_words(git_config("alkit.project"))
    hits = sorted({w for w in words if w.lower() in text})
    if not hits:
        return 0
    print("")
    print("  КОММИТ ОТКЛОНЁН: в сообщении упомянуто изделие или посторонний проект")
    for w in hits:
        print("    - %r" % w)
    print("")
    print("  Набор — знание об инструменте, а не история его сборки, и репозиторий")
    print("  публичный. Перепишите сообщение без названия: «воспроизведено на")
    print("  шестислойной плате» вместо «воспроизведено на такой-то».")
    print("  Правило целиком: knowledge/40_СРЕДА/40-02, раздел «Подготовка коммита».")
    print("")
    return 1


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    sys.exit(main(sys.argv[1:]))
