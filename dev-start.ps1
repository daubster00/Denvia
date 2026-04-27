# Denvia 로컬 개발 환경 시작 — 도시락(Docker) 한 벌로 통일
# 실행: 프로젝트 루트에서 우클릭 → "PowerShell로 실행"
# 또는: PowerShell에서 .\dev-start.ps1
#
# 전제: Docker Desktop이 켜져 있어야 함.

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "도시락(컨테이너)을 한 번에 켭니다..." -ForegroundColor Cyan
Write-Host "서비스: web · api · worker · beat · postgres · redis" -ForegroundColor Gray
Write-Host ""

docker compose -f "$ROOT\infra\docker-compose.yml" up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "실패. Docker Desktop이 켜져 있는지 확인하세요." -ForegroundColor Red
    pause
    exit 1
}

Write-Host ""
Write-Host "준비 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "  잠시(10~20초) 후 브라우저에서 확인:" -ForegroundColor White
Write-Host "  http://localhost:3000        (랜딩 페이지)" -ForegroundColor Yellow
Write-Host "  http://localhost:3000/chat   (채팅 — 로그인 필요)" -ForegroundColor Yellow
Write-Host ""
Write-Host "현재 상태 보기 :  docker compose -f infra\docker-compose.yml ps" -ForegroundColor Gray
Write-Host "로그 보기      :  docker compose -f infra\docker-compose.yml logs -f api" -ForegroundColor Gray
Write-Host "다 끄기        :  docker compose -f infra\docker-compose.yml down" -ForegroundColor Gray
