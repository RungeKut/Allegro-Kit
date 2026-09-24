# Установка Allegro-Kit на машине.
#
# Запускать из любого места после клонирования репозитория:
#     powershell -ExecutionPolicy Bypass -File tools\setup.ps1
#
# Что делает:
#   1. находит корень набора (папка на уровень выше этого скрипта);
#   2. создаёт junction ~\.claude\skills\allegro -> <корень>\skill,
#      чтобы скилл подхватывался Claude Code из любого каталога;
#   3. прописывает переменную ALKIT_HOME в профиль пользователя;
#   4. включает хук commit-msg, который не пропускает в сообщение коммита
#      название проектируемого изделия, и заводит пустой локальный стоп-лист;
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
$skills = Join-Path $env:USERPROFILE ".claude\skills"
if (-not (Test-Path $skills)) {
    New-Item -ItemType Directory -Path $skills -Force | Out-Null
}
$link = Join-Path $skills "allegro"
$target = Join-Path $root "skill"

if (Test-Path $link) {
    $item = Get-Item $link -Force
    $current = $null
    if ($item.LinkType) { $current = $item.Target | Select-Object -First 1 }
    if ($current -eq $target) {
        Write-Host "OK   junction уже указывает куда нужно"
    } else {
        Write-Host "     junction ведёт в другое место ($current) — пересоздаю"
        if ($item.LinkType) {
            cmd /c rmdir "$link" | Out-Null
        } else {
            throw "$link — обычная папка, а не ссылка. Уберите её вручную и повторите."
        }
        cmd /c mklink /J "$link" "$target" | Out-Null
        Write-Host "OK   junction создан"
    }
} else {
    cmd /c mklink /J "$link" "$target" | Out-Null
    Write-Host "OK   junction создан: $link -> $target"
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
} else {
    Write-Host "НЕТ  git не найден — хук commit-msg не включён"
}
$local = Join-Path $root "tools\stoplist.local.txt"
if (-not (Test-Path $local)) {
    $text = "# Приметы изделий этой машины: названия, обозначения, номера.`r`n" +
            "# Файл в .gitignore и в репозиторий не попадает.`r`n"
    [IO.File]::WriteAllText($local, $text, (New-Object Text.UTF8Encoding $false))
    Write-Host "OK   заведён tools\stoplist.local.txt — впишите туда изделие"
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
Write-Host "Готово. Перезапустите Claude Code, чтобы он увидел скилл /allegro."
