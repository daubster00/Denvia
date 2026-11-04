# 운영 배포 스크립트 (Windows 작업 스케줄러용)
#
# 하는 일: 운영 서버에 SSH 로 들어가 DB 백업 → git pull → 재빌드 → 헬스체크 → 로그 기록.
# 사람이 없을 때 돌 수 있으므로 **마이그레이션은 하지 않는다** — 새 revision 이 있으면
# 배포를 중단하고 로그에 남긴다(수동 적용이 필요한 단계라 무인 실행에 부적합).
#
# 산출물: scripts/.deploy/deploy-YYYYMMDD_HHmm.log  +  latest.log
# 사용:   powershell -ExecutionPolicy Bypass -File scripts\deploy-prod.ps1

$ErrorActionPreference = 'Continue'

$Root    = Split-Path -Parent $PSScriptRoot
$LogDir  = Join-Path $PSScriptRoot '.deploy'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force $LogDir | Out-Null }

$Stamp   = Get-Date -Format 'yyyyMMdd_HHmm'
$LogFile = Join-Path $LogDir "deploy-$Stamp.log"
$Latest  = Join-Path $LogDir 'latest.log'

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

$Host_   = 'denvia-prod-01'
$Compose = 'docker compose --env-file .env.production -f infra/docker-compose.prod.yml'

Log '=== 운영 배포 시작 ==='

# 0) 배포 대상 커밋 확인
$local = (ssh $Host_ "cd /opt/denvia && git rev-parse --short HEAD") 2>&1
Log "서버 현재 커밋: $local"

# 1) 새 마이그레이션이 있으면 중단 (무인 실행에서 건드리지 않는다)
$newMig = (ssh $Host_ "cd /opt/denvia && git fetch -q origin main && git diff --name-only HEAD origin/main -- api/alembic/versions/ | wc -l") 2>&1
if ("$newMig".Trim() -ne '0') {
    Log "중단: 새 마이그레이션 $newMig 건이 포함돼 있습니다. 무인 배포 대상이 아닙니다."
    Log '=== 배포 중단 (코드 변경 없음) ==='
    Copy-Item $LogFile $Latest -Force
    exit 2
}
Log '새 마이그레이션 없음 — 계속 진행'

# 2) DB 백업
Log 'DB 백업 중...'
$bk = "/opt/denvia/backups/backup_auto_$Stamp.dump"
ssh $Host_ "mkdir -p /opt/denvia/backups && docker exec -t infra-postgres-1 pg_dump -U denvia -F c denvia > $bk && ls -lh $bk" 2>&1 | ForEach-Object { Log "  $_" }

# 3) pull
Log 'git pull...'
ssh $Host_ "cd /opt/denvia && git pull origin main 2>&1 | tail -3 && git rev-parse --short HEAD" 2>&1 | ForEach-Object { Log "  $_" }

# 4) nginx 설정 반영 — **반드시 api 재빌드보다 먼저**
#
#    nginx 설정은 읽기 전용 볼륨 마운트라 `up -d --build` 로는 반영되지 않는다.
#    pull 로 파일만 바뀌고 nginx 는 옛 설정을 그대로 물고 있다.
#    순서가 중요하다: api 가 먼저 올라가면 XFF 를 신뢰하는데 nginx 는 아직
#    클라이언트가 보낸 값을 덧붙이는 상태라, 그 사이 **IP 위조가 가능**해진다.
#    nginx(덮어쓰기) → api(신뢰) 순서여야 그 창이 생기지 않는다.
#    reload 로는 부족하다: denvia.prod.conf 는 **단일 파일** bind mount 라,
#    git pull 이 파일을 통째로 교체(rename)하면 컨테이너는 옛 inode 를 계속 물고 있다.
#    컨테이너를 재생성해야 호스트의 새 파일이 다시 연결된다.
Log 'nginx 컨테이너 재생성(단일 파일 마운트라 reload 로는 반영 안 됨)...'
ssh $Host_ "cd /opt/denvia && $Compose up -d --force-recreate nginx 2>&1 | tail -4" 2>&1 | ForEach-Object { Log "  $_" }
Start-Sleep -Seconds 5

$nginxTest = (ssh $Host_ "docker exec infra-nginx-1 nginx -t 2>&1") 2>&1
$nginxTest | ForEach-Object { Log "  $_" }
if ("$nginxTest" -notmatch 'successful') {
    Log '!!! nginx 설정 오류 — api 재빌드를 중단합니다 !!!'
    Copy-Item $LogFile $Latest -Force
    exit 1
}

$xff = (ssh $Host_ "docker exec infra-nginx-1 grep -h 'X-Forwarded-For' /etc/nginx/conf.d/denvia.conf | head -1") 2>&1
Log "nginx XFF 설정: $xff"
if ("$xff" -notmatch 'remote_addr') {
    Log '!!! nginx 가 아직 옛 설정(append) 입니다 — api 재빌드를 중단합니다(IP 위조 위험) !!!'
    Log '   api 만 올라가면 위조된 X-Forwarded-For 를 그대로 믿게 되므로 진행하지 않습니다.'
    Copy-Item $LogFile $Latest -Force
    exit 1
}

# 5) 재빌드 + 재시작 (web 빌드로 수 분 소요, 재시작 중 약 30초 502 발생)
Log '재빌드 + 재시작... (수 분 소요)'
ssh $Host_ "cd /opt/denvia && $Compose up -d --build 2>&1 | tail -12" 2>&1 | ForEach-Object { Log "  $_" }

# 6) 헬스체크 — 기동까지 최대 3분 대기
Log '헬스체크 대기...'
$ok = $false
for ($i = 1; $i -le 18; $i++) {
    Start-Sleep -Seconds 10
    try {
        $r = Invoke-WebRequest -Uri 'https://denvia.ai.kr/healthz' -UseBasicParsing -TimeoutSec 15
        if ($r.StatusCode -eq 200) {
            Log "헬스체크 OK ($($i*10)초): $($r.Content)"
            $ok = $true
            break
        }
    } catch {
        Log "  대기 중... ($($i*10)초)"
    }
}

if (-not $ok) {
    Log '!!! 헬스체크 실패 — 운영이 응답하지 않습니다. 즉시 확인 필요 !!!'
    Log "복구 참고: ssh $Host_ 'docker logs infra-api-1 --tail 50'"
    Copy-Item $LogFile $Latest -Force
    exit 1
}

# 7) 관리자 로그인 확인
try {
    $body = '{"email":"btmdesign@naver.com","password":"Btm6853!"}'
    $r = Invoke-WebRequest -Uri 'https://denvia.ai.kr/api/v1/admin/auth/login' -Method POST `
         -ContentType 'application/json' -Body $body -UseBasicParsing -TimeoutSec 20
    Log "관리자 로그인 HTTP $($r.StatusCode)"
} catch {
    Log "관리자 로그인 실패: $_"
}

# 8) IP 기록 복구 확인 (이번 배포의 핵심) — 내부 IP 가 아닌 값이 찍혀야 정상
Log 'IP 기록 확인 (172.18.x 가 아니어야 정상)...'
ssh $Host_ "docker logs infra-api-1 --since 5m 2>&1 | grep -oE '\""ip\"": \""[^\""]+\""' | sort | uniq -c | head -5" 2>&1 | ForEach-Object { Log "  $_" }

Log '=== 배포 완료 ==='
Copy-Item $LogFile $Latest -Force
exit 0
