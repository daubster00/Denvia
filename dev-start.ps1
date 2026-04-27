# Denvia 로컬 개발 환경 시작 스크립트
# 실행: 프로젝트 루트에서 우클릭 → "PowerShell로 실행"
# 또는: PowerShell에서 .\dev-start.ps1

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "1/3  DB + Redis 시작 중..." -ForegroundColor Cyan
Set-Location "$ROOT\infra"
docker compose up postgres redis -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker 실패. Docker Desktop이 실행 중인지 확인하세요." -ForegroundColor Red
    pause
    exit 1
}

Write-Host "2/3  API 서버 + 웹 서버 터미널 오픈 중..." -ForegroundColor Cyan

# Windows Terminal이 있으면 탭으로, 없으면 별도 창으로 오픈
$wt = Get-Command wt -ErrorAction SilentlyContinue

if ($wt) {
    # --profile Ubuntu 대신 wsl.exe 직접 지정 — wt가 Linux 경로를 Windows 경로로 오해하는 문제 우회
    wt `
        new-tab --title "API" -- wsl.exe -d Ubuntu /usr/bin/bash /mnt/d/projects/Dental\ Chatbot/api-dev.sh `; `
        new-tab --title "Web" --startingDirectory "$ROOT\web" -- powershell -NoExit -Command "pnpm dev"
} else {
    # Windows Terminal 없을 때 — 별도 PowerShell 창 2개
    Start-Process wsl -ArgumentList "-d", "Ubuntu", "/usr/bin/bash", "/mnt/d/projects/Dental Chatbot/api-dev.sh"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$ROOT\web'; pnpm dev"
}

Write-Host ""
Write-Host "3/3  준비 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "  잠시 후 브라우저에서 확인:" -ForegroundColor White
Write-Host "  http://localhost:3000        (랜딩 페이지)" -ForegroundColor Yellow
Write-Host "  http://localhost:3000/chat   (채팅 — 로그인 필요)" -ForegroundColor Yellow
Write-Host ""
Write-Host "종료하려면: docker compose -f infra\docker-compose.yml stop postgres redis" -ForegroundColor Gray
