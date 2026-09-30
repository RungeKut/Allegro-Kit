# Установка Allegro-Kit на машине.
#
# Запускать из любого места после клонирования репозитория:
#     powershell -ExecutionPolicy Bypass -File tools\setup.ps1
#
# Что делает:
#   1. находит корень набора (папка на уровень выше этого скрипта);
#   2. создаёт junction ~\.claude\skills\allegro -> <корень>\skill и
#      ~\.kimi-code\skills\allegro -> <корень>\skill, чтобы скилл
#      подхватывался Claude Code и Kimi Code из любого каталога;
#   3. прописывает переменную ALKIT_HOME в профиль пользователя;
#   4. включает хук commit-msg, который не пропускает в сообщение коммита
#      название проектируемого изделия, заводит локальный стоп-лист
#      tools\stoplist.txt (он в .gitignore) и напоминает об авторе коммитов;
#   5. проверяет Python (64-bit) и ставит Pillow — для картинок платы;
#   6. ищет Cadence SPB и печатает версию Allegro.
#
# Прав администратора не требует: junction (mklink /J) создаётся без них.
# Файл сохранён в UTF-8 С BOM: без него Windows PowerShell 5.1 читает
# кириллицу в ANSI и скрипт падает на первой же русской строке.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Write-Host "Корень набора: $root"

if (-not (Test-Path (Join-Path $root "alkit"))) {
    throw "В $root нет папки alkit — скрипт запущен не из репозитория."
}

# --- 1. junction для скилла ------------------------------------------------
# Один и тот же <корень>\skill подключается к обоим агентам: Claude Code
# ищет скиллы в ~\.claude\skills, Kimi Code — в ~\.kimi-code\skills.
$target = Join-Path $root "skill"
foreach ($skills in @(
    (Join-Path $env:USERPROFILE ".claude\skills"),
    (Join-Path $env:USERPROFILE ".kimi-code\skills"))) {
    if (-not (Test-Path $skills)) {
        New-Item -ItemType Directory -Path $skills -Force | Out-Null
    }
    $link = Join-Path $skills "allegro"

    if (Test-Path $link) {
        $item = Get-Item $link -Force
        $current = $null
        if ($item.LinkType) { $current = $item.Target | Select-Object -First 1 }
        if ($current -eq $target) {
            Write-Host "OK   junction уже указывает куда нужно: $link"
        } else {
            Write-Host "     junction $link ведёт в другое место ($current) — пересоздаю"
            if ($item.LinkType) {
                cmd /c rmdir "$link" | Out-Null
            } else {
                throw "$link — обычная папка, а не ссылка. Уберите её вручную и повторите."
            }
            cmd /c mklink /J "$link" "$target" | Out-Null
            Write-Host "OK   junction создан: $link -> $target"
        }
    } else {
        cmd /c mklink /J "$link" "$target" | Out-Null
        Write-Host "OK   junction создан: $link -> $target"
    }
}

# --- 2. ALKIT_HOME ---------------------------------------------------------
[Environment]::SetEnvironmentVariable("ALKIT_HOME", $root, "User")
$env:ALKIT_HOME = $root
Write-Host "OK   ALKIT_HOME = $root (в новых консолях подхватится сам)"

# --- 3. хук на текст коммита и локальный стоп-лист -------------------------
if (Get-Command git -ErrorAction SilentlyContinue) {
    Push-Location $root
    git config core.hooksPath tools/hooks
    Pop-Location
    Write-Host "OK   core.hooksPath = tools/hooks (проверка текста коммита)"
    Write-Host "     папку текущего проекта можно добавить к стоп-словам:"
    Write-Host "     git config alkit.project '<путь к папке проекта>'"
    # Автор коммитов — публичный и только для этого клона: иначе git возьмёт
    # глобальные рабочие имя и адрес и опубликует их (40-02).
    Push-Location $root
    $author = git config --local --get user.email
    Pop-Location
    if ($author) {
        Write-Host "OK   автор коммитов этого клона: $author"
    } else {
        Write-Host "НЕТ  автор коммитов не задан — уйдут глобальные (рабочие) имя и адрес."
        Write-Host "     git config user.name  '<публичное имя>'"
        Write-Host "     git config user.email '<публичный адрес>'"
    }
} else {
    Write-Host "НЕТ  git не найден — хук commit-msg не включён"
}
# Стоп-лист локальный: лежащий в репозитории сам публиковал бы названия,
# которые должен скрывать. Без BOM — Python читает его как UTF-8.
$stop = Join-Path $root "tools\stoplist.txt"
if (-not (Test-Path $stop)) {
    $text = "# Стоп-слова: названия и приметы изделий этой машины.`r`n" +
            "# Файл ЛОКАЛЬНЫЙ: он в .gitignore и в репозиторий не попадает.`r`n" +
            "# Строка = подстрока, регистр не важен; # — комментарий.`r`n"
    [IO.File]::WriteAllText($stop, $text, (New-Object Text.UTF8Encoding $false))
    Write-Host "OK   заведён tools\stoplist.txt — впишите туда изделие до первого коммита"
} else {
    Write-Host "OK   tools\stoplist.txt на месте (локальный, в .gitignore)"
}

# --- 4. Python -------------------------------------------------------------
$py = $null
foreach ($c in @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe")) {
    if (Test-Path $c) { $py = $c; break }
}
if (-not $py) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py) {
    Write-Host "НЕТ  Python не найден."
    Write-Host "     winget install --id Python.Python.3.13 --scope user --silent"
    exit 1
}
Write-Host "OK   Python: $py"
$arch = & $py -c "import platform; print(platform.architecture()[0])"
if ($arch -ne "64bit") {
    Write-Host "НЕТ  Python $arch — нужен 64bit."
    exit 1
}

# stderr нативной программы при Stop в PowerShell 5.1 становится
# терминирующей ошибкой — на время проверки снимаем Stop
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $py -c "import PIL" 2>&1 | Out-Null
$hasPil = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prev
if (-not $hasPil) {
    Write-Host "     Pillow не установлен — ставлю"
    & $py -m pip install --quiet Pillow
}
Write-Host "OK   Pillow на месте"

# --- 5. Cadence ------------------------------------------------------------
$ErrorActionPreference = "Continue"
& $py -c "import sys; sys.path.insert(0, r'$root'); import alkit as ak; ak.utf8_console(); print('OK   alkit', ak.__version__); print('OK   Cadence:', ak.cdsroot()); print('OK   Allegro', ak.version()); print('     лицензии по порядку:', ', '.join(ak.product_order()))"
if ($LASTEXITCODE -ne 0) {
    Write-Host "НЕТ  Cadence SPB не найден: задайте ALKIT_CDSROOT"
}
$ErrorActionPreference = $prev

Write-Host ""
Write-Host "Готово. Перезапустите Claude Code и Kimi Code, чтобы они увидели скилл (/allegro и /skill:allegro)."
