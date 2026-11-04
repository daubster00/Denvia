# 판단 단계(query_rewriter) 건강도 일일 수집기
#
# 왜 필요한가: docker 로그는 **배포 때 컨테이너가 재생성되면 전부 사라진다.**
# 2~3일 추이를 보려면 매일 집계해 파일에 누적해야 한다.
#
# 보는 것 2가지 (2026-11-04 수정의 사후 검증 항목):
#   1) parse_error 비율 — 판단이 빈 응답으로 실패한 비율. 수정 전 기준치 10.7%(28건 중 3건).
#      0 이 아니면 REWRITER_MAX_TOKENS 를 1500 으로 더 올리거나 비추론 모델 검토.
#   2) related=true 비율 — 동시청구 프롬프트 완화의 부작용 점검.
#      급등했으면 맥락이 과도하게 붙는 것 → '새 사례는 false' 반례 강화.
#
# 산출물: scripts/.watch/rewriter.tsv  (탭 구분, 엑셀로 바로 열림)
# 사용:   powershell -ExecutionPolicy Bypass -File scripts\rewriter-watch.ps1

$ErrorActionPreference = 'Continue'

$Dir = Join-Path $PSScriptRoot '.watch'
if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Force $Dir | Out-Null }
$Tsv = Join-Path $Dir 'rewriter.tsv'
if (-not (Test-Path $Tsv)) {
    "날짜`t컨테이너기동`t판단전체`tparse_error`t오류율%`trelated_true`ttrue율%`t되묻기누적" |
        Out-File -FilePath $Tsv -Encoding utf8
}

$H = 'denvia-prod-01'

# 컨테이너 기동 시각 — 로그 구간이 얼마나 되는지 알아야 수치를 읽을 수 있다.
$started = (ssh $H "docker inspect -f '{{.State.StartedAt}}' infra-api-1") 2>&1

$total  = (ssh $H "docker logs infra-api-1 2>&1 | grep -c 'qa.rewriter.decided'") 2>&1
$perr   = (ssh $H "docker logs infra-api-1 2>&1 | grep -c 'qa.rewriter.parse_error'") 2>&1
$rtrue  = (ssh $H "docker logs infra-api-1 2>&1 | grep 'qa.rewriter.decided' | grep -c 'related.: true'") 2>&1

# 되묻기는 DB 에 남으므로 배포와 무관하게 누적치를 볼 수 있다.
# PowerShell 은 네이티브 명령 인자에서 큰따옴표를 삼킨다. `\""` 로 넘겨야
# 원격 bash 가 따옴표를 제대로 받는다(그냥 `""` 나 `--%` 로는 깨진다).
$clar = (ssh $H "docker exec -i infra-postgres-1 psql -U denvia -d denvia -At -c \""SELECT count(*) FROM qa_logs WHERE answer_kind='clarification'\""") 2>&1

function N($v) { $n = 0; [int]::TryParse(("$v".Trim()), [ref]$n) | Out-Null; return $n }
$t = N $total; $e = N $perr; $r = N $rtrue; $c = N $clar

$errPct  = if ($t -gt 0) { [math]::Round(100.0 * $e / $t, 1) } else { 0 }
$truePct = if ($t -gt 0) { [math]::Round(100.0 * $r / $t, 1) } else { 0 }

$row = "{0}`t{1}`t{2}`t{3}`t{4}`t{5}`t{6}`t{7}" -f `
    (Get-Date -Format 'yyyy-MM-dd HH:mm'), "$started".Trim(), $t, $e, $errPct, $r, $truePct, $c
Add-Content -Path $Tsv -Value $row -Encoding utf8

Write-Output "판단 $t 건 / parse_error $e 건($errPct%) / related=true $r 건($truePct%) / 되묻기 누적 $c 건"
if ($t -lt 20) { Write-Output "  ※ 표본 $t 건 — 20건 미만이면 비율은 읽지 말 것" }
if ($e -gt 0)  { Write-Output "  !! parse_error 발생 — REWRITER_MAX_TOKENS 추가 상향 검토" }
Write-Output "누적 파일: $Tsv"
