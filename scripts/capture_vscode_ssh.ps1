# VSCode Remote-SSH 단계별 스크린샷 캡쳐 (denvia-prod-01)
#
# 클린 user-data-dir로 새 VSCode를 띄우되 즉시 최대화 → 뒤쪽 사용자 작업 화면이
# 절대 노출되지 않도록 함. 각 단계 캡쳐 → outputs/vscode_ssh/NN_*.png
#
# 실행: powershell -ExecutionPolicy Bypass -File scripts/capture_vscode_ssh.ps1

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
}
"@

$ROOT = "D:\projects\Dental Chatbot"
$OUT  = "$ROOT\outputs\vscode_ssh"
$TMP  = "$env:TEMP\vscode_capture_profile_v2"
$CODE = "C:\Users\daubs\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd"

if (Test-Path $TMP) { Remove-Item $TMP -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $TMP | Out-Null
New-Item -ItemType Directory -Force -Path $OUT | Out-Null

# 이전 캡쳐용 인스턴스 종료 (제목에 "Welcome"이 있거나 --user-data-dir이 temp인 창)
Get-Process Code -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -like "*Welcome*" -or $_.MainWindowTitle -like "*get_started*"
} | ForEach-Object {
    Write-Host "  closing leftover: $($_.Id) '$($_.MainWindowTitle)'"
    $_.CloseMainWindow() | Out-Null
}
Start-Sleep -Seconds 2

# VSCode 메인 창 찾기 — Get-Process 로 단순화
function Find-VSCodeWindow([string]$titleContains) {
    $p = Get-Process Code -ErrorAction SilentlyContinue | Where-Object {
        $_.MainWindowTitle -like "*$titleContains*Visual Studio Code*"
    } | Select-Object -First 1
    if ($p) { return $p.MainWindowHandle } else { return [IntPtr]::Zero }
}

function Capture-Screen([string]$name) {
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $path = Join-Path $OUT $name
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Host "  saved: $path"
}

$script:vscodeHandle = [IntPtr]::Zero

function Ensure-Maximized {
    if ($script:vscodeHandle -eq [IntPtr]::Zero) {
        # 가능한 제목 후보 — Welcome, get_started, Untitled 등
        foreach ($t in @("Welcome", "Untitled", "Get Started", "Extension")) {
            $h = Find-VSCodeWindow $t
            if ($h -ne [IntPtr]::Zero) { $script:vscodeHandle = $h; break }
        }
    }
    if ($script:vscodeHandle -ne [IntPtr]::Zero) {
        [Win32]::ShowWindow($script:vscodeHandle, 3) | Out-Null  # SW_MAXIMIZE
        [Win32]::SetForegroundWindow($script:vscodeHandle) | Out-Null
        Start-Sleep -Milliseconds 500
    }
}

function Send-Keys([string]$k, [int]$wait=600) {
    Ensure-Maximized
    [System.Windows.Forms.SendKeys]::SendWait($k)
    Start-Sleep -Milliseconds $wait
}

function Type-Text([string]$text, [int]$wait=400) {
    Ensure-Maximized
    $special = "+^%~(){}[]"
    foreach ($ch in $text.ToCharArray()) {
        $c = "$ch"
        if ($special.Contains($c)) { $c = "{$c}" }
        [System.Windows.Forms.SendKeys]::SendWait($c)
        Start-Sleep -Milliseconds 25
    }
    Start-Sleep -Milliseconds $wait
}

Write-Host "== VSCode 클린 프로필 실행 =="
Start-Process -FilePath $CODE -ArgumentList "--new-window","--user-data-dir","`"$TMP`"","--disable-workspace-trust" -WindowStyle Maximized
Write-Host "  부팅 대기 (10초)..."
Start-Sleep -Seconds 10

# 핸들 재탐색
$script:vscodeHandle = [IntPtr]::Zero
Ensure-Maximized
if ($script:vscodeHandle -eq [IntPtr]::Zero) {
    Write-Warning "VSCode 창 핸들 미발견 — 그래도 진행"
}

# 추가 안정화
Start-Sleep -Seconds 2
Ensure-Maximized

# 1. Welcome 화면
Capture-Screen "01_welcome.png"

# 2. Extensions 사이드바 (Ctrl+Shift+X)
Send-Keys "^+x" 2000
Ensure-Maximized
Capture-Screen "02_extensions_panel.png"

# 검색창에 Remote - SSH
Type-Text "Remote - SSH" 2000
Capture-Screen "03_extensions_remote_ssh_search.png"

# Esc로 검색 비우기, 사이드바 닫지 않고 그대로 Command Palette 호출
Send-Keys "{ESC}" 500

# 4. Command Palette 빈 상태 (Ctrl+Shift+P)
Send-Keys "^+p" 1500
Ensure-Maximized
Capture-Screen "04_command_palette_empty.png"

# 5. "Remote-SSH: Connect to Host" 타이핑
Type-Text "Remote-SSH: Connect to Host" 1500
Capture-Screen "05_command_palette_remote_ssh.png"

# 6. Enter → 호스트 picker
Send-Keys "{ENTER}" 2500
Ensure-Maximized
Capture-Screen "06_host_picker.png"

# 7. denvia-prod-01 선택 (목록 첫 항목) → 새 창에서 접속
Send-Keys "{ENTER}" 3000
# 새 창이 뜸 — 핸들 다시 찾기 (제목: SSH: denvia-prod-01)
$script:vscodeHandle = [IntPtr]::Zero
Start-Sleep -Seconds 5
foreach ($t in @("SSH:", "denvia-prod-01", "Welcome", "Untitled")) {
    $h = Find-VSCodeWindow $t
    if ($h -ne [IntPtr]::Zero) { $script:vscodeHandle = $h; break }
}
Ensure-Maximized
Capture-Screen "07_connecting_new_window.png"

# 접속 완료 대기 (서버 응답)
Start-Sleep -Seconds 10
Ensure-Maximized
Capture-Screen "08_post_connect.png"

Start-Sleep -Seconds 8
Ensure-Maximized
Capture-Screen "09_connected_status_bar.png"

# 10. 폴더 열기 (Ctrl+K Ctrl+O)
Send-Keys "^k" 200
Send-Keys "^o" 2500
Ensure-Maximized
Capture-Screen "10_open_remote_folder.png"

# 11. /opt/denvia 입력
Type-Text "/opt/denvia" 1000
Capture-Screen "11_open_folder_path.png"

# 12. Enter → 폴더 열림. 신뢰 묻는 모달 뜨면 그대로 둠 (캡쳐).
Send-Keys "{ENTER}" 4000
Ensure-Maximized
Capture-Screen "12_explorer_files.png"

# 신뢰 모달의 "Yes, I trust the authors" 클릭 (Tab + Enter)
Send-Keys "{TAB}" 300
Send-Keys "{ENTER}" 3000
Ensure-Maximized
Capture-Screen "13_files_loaded.png"

Write-Host ""
Write-Host "== 캡쳐 완료 =="
Get-ChildItem $OUT | Format-Table Name, Length
