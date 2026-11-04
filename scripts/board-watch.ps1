<#
  board-watch.ps1 — 수정요청 게시판 새 글 감시기

  하는 일:
    1) 운영 서버(denvia-prod-01) DB의 게시판 글/댓글 현황을 ssh 로 읽어온다.
    2) 지난번 상태(.board-watch/state.json)와 비교해 "새 글 / 다시 요청으로 바뀐 글 / 새 댓글"을 찾는다.
    3) 변화가 있으면 PC 화면 알림 + 요약 파일(.board-watch/latest.md, new-YYYY-MM-DD.md)을 만든다.
    4) 변화가 없으면 조용히 run.log 에 한 줄만 남긴다.

  사용:
    powershell -File scripts/board-watch.ps1              # 평소 (작업 스케줄러가 호출)
    powershell -File scripts/board-watch.ps1 -Baseline    # 기준점만 다시 잡기(알림 없음)
    powershell -File scripts/board-watch.ps1 -SincePost 140 -NoToast   # 테스트용
#>
param(
  [switch]$Baseline,
  [long]$SincePost = -1,
  [long]$SinceComment = -1,
  [switch]$NoToast
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$Root         = Split-Path -Parent $PSScriptRoot
$WatchDir     = Join-Path $Root '.board-watch'
$StateFile    = Join-Path $WatchDir 'state.json'
$LogFile      = Join-Path $WatchDir 'run.log'
$Utf8         = New-Object System.Text.UTF8Encoding $false
$SshHost      = 'denvia-prod-01'
$MasterEmail  = 'btmdesign@naver.com'   # 내가 쓴 댓글은 알림에서 제외
$BoardUrl     = 'https://denvia.ai.kr/admin/board'

if (-not (Test-Path $WatchDir)) { New-Item -ItemType Directory -Path $WatchDir | Out-Null }

function Write-Log([string]$Line) {
  $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  Add-Content -Path $LogFile -Value "[$stamp] $Line" -Encoding UTF8
}

function Show-Alert([string]$Title, [string]$Body) {
  if ($NoToast) { return }
  try {
    [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]
    $tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
             [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $texts = $tpl.GetElementsByTagName('text')
    [void]$texts.Item(0).AppendChild($tpl.CreateTextNode($Title))
    [void]$texts.Item(1).AppendChild($tpl.CreateTextNode($Body))
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(
                  '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe')
    $notifier.Show([Windows.UI.Notifications.ToastNotification]::new($tpl))
    return
  } catch { }
  try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $ni = New-Object System.Windows.Forms.NotifyIcon
    $ni.Icon = [System.Drawing.SystemIcons]::Information
    $ni.Visible = $true
    $ni.ShowBalloonTip(20000, $Title, $Body, [System.Windows.Forms.ToolTipIcon]::Info)
    Start-Sleep -Seconds 6
    $ni.Dispose()
  } catch {
    Write-Log "WARN 화면 알림 실패: $($_.Exception.Message)"
  }
}

$StatusLabel = @{
  'review' = '요청사항검토'; 'rework' = '추가수정'; 'in_progress' = '수정중'
  'confirm_requested' = '컨펌요청'; 'confirmed' = '컨펌'; 'completed' = '수정완료'
  'rejected' = '수정불가'; 'on_hold' = '보류'
}
$CategoryLabel = @{
  'error' = '에러'; 'feature' = '추가개발'; 'inquiry' = '문의'; 'etc' = '기타'
  'chatbot' = '챗봇'; 'admin' = '관리자'; 'mypage' = '마이페이지'; 'design' = '디자인'
  'auth' = '회원'; 'billing' = '결제'; 'messaging' = '알림'
}
function Get-Label($Map, [string]$Key) {
  if ($Map.ContainsKey($Key)) { return $Map[$Key] }
  return $Key
}

# ── 1. 지난 상태 읽기 ───────────────────────────────────────────────────────
$state = $null
if (Test-Path $StateFile) {
  try { $state = Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $state = $null }
}
$isFirstRun    = ($null -eq $state)
$lastCommentId = 0
$prevMaxPostId = 0
$prevStatus    = @{}
if (-not $isFirstRun) {
  $lastCommentId = [long]$state.lastCommentId
  $prevMaxPostId = [long]$state.lastPostId
  if ($state.statuses) {
    foreach ($prop in $state.statuses.PSObject.Properties) { $prevStatus[$prop.Name] = [string]$prop.Value }
  }
}
if ($SincePost -ge 0)    { $prevMaxPostId = $SincePost }
if ($SinceComment -ge 0) { $lastCommentId = $SinceComment }

# ── 2. 운영 DB 조회 (ssh → docker → psql) ──────────────────────────────────
$SEP = '~@~'
$remote = @"
set -e
cd /opt/denvia
psql_q() {
  # </dev/null 필수 — 없으면 docker compose exec 가 남은 스크립트를 stdin 으로 먹어 다음 쿼리가 실행되지 않는다.
  docker compose -f infra/docker-compose.prod.yml exec -T postgres \
    psql -U denvia -d denvia -P pager=off -At -F '$SEP' -c "`$1" </dev/null 2>/dev/null
}
psql_q "SELECT 'P', p.id, p.status, p.category, u.name,
               to_char(p.created_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI'),
               replace(replace(p.title, chr(10), ' '), '$SEP', '/'),
               left(regexp_replace(regexp_replace(p.content_html,'<[^>]+>',' ','g'),'\s+',' ','g'), 300)
        FROM admin_board_posts p JOIN users u ON u.id = p.author_id
        ORDER BY p.id;"
psql_q "SELECT 'C', c.id, c.post_id, u.name,
               to_char(c.created_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI'),
               left(replace(replace(c.content, chr(10), ' '), '$SEP', '/'), 300),
               p.status, replace(p.title, chr(10), ' ')
        FROM admin_board_comments c
        JOIN users u ON u.id = c.author_id
        JOIN admin_board_posts p ON p.id = c.post_id
        WHERE c.id > $lastCommentId AND lower(u.email) <> '$MasterEmail'
        ORDER BY c.id;"
psql_q "SELECT 'M', coalesce(max(id), 0) FROM admin_board_comments;"
"@
$remote = $remote -replace "`r`n", "`n"
$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($remote))

$raw = ''
try {
  $out = & ssh -o BatchMode=yes -o ConnectTimeout=20 $SshHost "echo $b64 | base64 -d | bash"
  # Out-String 은 80자에서 줄을 접어 긴 행을 망가뜨린다 → 반드시 -join 사용.
  $raw = ($out -join "`n")
} catch {
  Write-Log "ERROR ssh 실패: $($_.Exception.Message)"
  Show-Alert '게시판 확인 실패' '운영 서버에 접속하지 못했습니다. .board-watch\run.log 를 확인하세요.'
  exit 1
}
$lines = @($raw -split "`r?`n" | Where-Object { $_ -like "*$SEP*" })
if ($lines.Count -eq 0) {
  Write-Log 'ERROR 조회 결과가 비어 있음 (DB 응답 없음)'
  Show-Alert '게시판 확인 실패' 'DB 조회 결과가 비었습니다. .board-watch\run.log 를 확인하세요.'
  exit 1
}

# ── 3. 파싱 ────────────────────────────────────────────────────────────────
$posts = New-Object System.Collections.Generic.List[object]
$comments = New-Object System.Collections.Generic.List[object]
$dbMaxCommentId = -1
foreach ($line in $lines) {
  $f = $line -split [regex]::Escape($SEP)
  if ($f[0] -eq 'P' -and $f.Count -ge 7) {
    $body = ''
    if ($f.Count -ge 8) { $body = $f[7] }
    $posts.Add([pscustomobject]@{
      Id = [long]$f[1]; Status = $f[2]; Category = $f[3]; Author = $f[4]
      Created = $f[5]; Title = $f[6]; Body = $body
    })
  } elseif ($f[0] -eq 'C' -and $f.Count -ge 8) {
    $comments.Add([pscustomobject]@{
      Id = [long]$f[1]; PostId = [long]$f[2]; Author = $f[3]
      Created = $f[4]; Content = $f[5]; PostStatus = $f[6]; PostTitle = $f[7]
    })
  } elseif ($f[0] -eq 'M' -and $f.Count -ge 2) {
    $dbMaxCommentId = [long]$f[1]
  }
}
if ($posts.Count -eq 0) {
  Write-Log 'ERROR 글 목록 파싱 실패'
  Show-Alert '게시판 확인 실패' '글 목록을 읽지 못했습니다. .board-watch\run.log 를 확인하세요.'
  exit 1
}
$maxPostId = ($posts | Measure-Object -Property Id -Maximum).Maximum
# 댓글 기준점은 DB 전체 최대 id 로 잡는다(내가 쓴 댓글까지 포함) — 안 그러면 매번 같은 댓글을 새 것으로 본다.
$maxCommentId = $lastCommentId
if ($dbMaxCommentId -ge 0) {
  $maxCommentId = $dbMaxCommentId
} elseif ($comments.Count -gt 0) {
  $maxCommentId = ($comments | Measure-Object -Property Id -Maximum).Maximum
}

# ── 4. 차이 계산 ───────────────────────────────────────────────────────────
$newPosts = @($posts | Where-Object { $_.Id -gt $prevMaxPostId })
$reopened = @()
if (-not $isFirstRun) {
  foreach ($p in $posts) {
    if ($p.Id -gt $prevMaxPostId) { continue }
    $key = [string]$p.Id
    if (($p.Status -eq 'review' -or $p.Status -eq 'rework') -and
        $prevStatus.ContainsKey($key) -and $prevStatus[$key] -ne $p.Status) {
      $reopened += $p
    }
  }
}
$waiting = @($posts | Where-Object { $_.Status -eq 'review' -or $_.Status -eq 'rework' })

# ── 5. 상태 저장 ───────────────────────────────────────────────────────────
$statusMap = @{}
foreach ($p in $posts) { $statusMap[[string]$p.Id] = $p.Status }
$newState = [pscustomobject]@{
  lastPostId    = $maxPostId
  lastCommentId = $maxCommentId
  lastRunAt     = (Get-Date).ToString('s')
  statuses      = $statusMap
}
[System.IO.File]::WriteAllText($StateFile, ($newState | ConvertTo-Json -Depth 4), $Utf8)

if ($isFirstRun -or $Baseline) {
  Write-Log "BASELINE 기준점 설정 — 글 $maxPostId 번까지, 댓글 $maxCommentId 번까지. 대기 중 $($waiting.Count)건"
  Write-Host "기준점을 잡았습니다. (글 #$maxPostId / 댓글 #$maxCommentId, 현재 대기 $($waiting.Count)건)"
  Write-Host '다음 실행부터 이 시점 이후의 새 글만 알립니다.'
  exit 0
}

$changeCount = $newPosts.Count + $reopened.Count + $comments.Count
if ($changeCount -eq 0) {
  Write-Log "OK 새 글 없음 (글 $maxPostId 번까지 / 대기 중 $($waiting.Count)건)"
  Write-Host "새 글 없음. 현재 대기 중 $($waiting.Count)건."
  exit 0
}

# ── 6. 요약 파일 작성 ──────────────────────────────────────────────────────
$today = Get-Date -Format 'yyyy-MM-dd'
$now   = Get-Date -Format 'yyyy-MM-dd HH:mm'
$md = New-Object System.Collections.Generic.List[string]
$md.Add("# 게시판 새 소식 — $now")
$md.Add('')
$md.Add("- 새 요청글 **$($newPosts.Count)건** / 다시 요청으로 바뀐 글 **$($reopened.Count)건** / 새 댓글 **$($comments.Count)건**")
$md.Add("- 현재 대기 중(요청사항검토 + 추가수정): **$($waiting.Count)건**")
$md.Add("- 게시판: $BoardUrl")
$md.Add('')
if ($newPosts.Count -gt 0) {
  $md.Add('## 새 요청글')
  $md.Add('')
  foreach ($p in $newPosts) {
    $md.Add("### #$($p.Id) · $(Get-Label $CategoryLabel $p.Category) · $(Get-Label $StatusLabel $p.Status)")
    $md.Add("- 작성: $($p.Author) · $($p.Created)")
    $md.Add("- 제목: **$($p.Title)**")
    $md.Add("- 본문(앞부분): $($p.Body)")
    $md.Add("- 상세: $BoardUrl/$($p.Id)")
    $md.Add('')
  }
}
if ($reopened.Count -gt 0) {
  $md.Add('## 다시 요청으로 바뀐 글')
  $md.Add('')
  foreach ($p in $reopened) {
    $md.Add("- #$($p.Id) [$(Get-Label $StatusLabel $p.Status)] $($p.Title) — $BoardUrl/$($p.Id)")
  }
  $md.Add('')
}
if ($comments.Count -gt 0) {
  $md.Add('## 새 댓글')
  $md.Add('')
  foreach ($c in $comments) {
    $md.Add("- #$($c.PostId) [$(Get-Label $StatusLabel $c.PostStatus)] $($c.PostTitle)")
    $md.Add("  - $($c.Author) ($($c.Created)): $($c.Content)")
  }
  $md.Add('')
}
$md.Add('---')
$md.Add('처리하려면 Claude Code 에서: `/board-fix` 또는 "게시판 확인해서 수정할 것 정리해줘"')

$text = ($md -join "`r`n") + "`r`n"
[System.IO.File]::WriteAllText((Join-Path $WatchDir 'latest.md'), $text, $Utf8)
$datedFile = Join-Path $WatchDir "new-$today.md"
if (Test-Path $datedFile) {
  Add-Content -Path $datedFile -Value "`r`n$text" -Encoding UTF8
} else {
  [System.IO.File]::WriteAllText($datedFile, $text, $Utf8)
}

# ── 7. 화면 알림 ───────────────────────────────────────────────────────────
$bits = @()
if ($newPosts.Count -gt 0) { $bits += "새 요청글 $($newPosts.Count)건" }
if ($reopened.Count -gt 0) { $bits += "재요청 $($reopened.Count)건" }
if ($comments.Count -gt 0) { $bits += "새 댓글 $($comments.Count)건" }
$title = '수정요청 게시판 — ' + ($bits -join ', ')
$detail = @()
foreach ($p in ($newPosts | Select-Object -First 3)) { $detail += "#$($p.Id) $($p.Title)" }
foreach ($p in ($reopened | Select-Object -First 2)) { $detail += "#$($p.Id) $($p.Title)" }
foreach ($c in ($comments | Select-Object -First 2)) { $detail += "#$($c.PostId) 댓글" }
$alertBody = ($detail -join ' / ')
if ($alertBody.Length -gt 180) { $alertBody = $alertBody.Substring(0, 177) + '...' }
if (-not $alertBody) { $alertBody = "대기 중 $($waiting.Count)건" }
Show-Alert $title $alertBody

Write-Log "NEW $title | $alertBody"
Write-Host $title
Write-Host $alertBody
Write-Host "요약 파일: $(Join-Path $WatchDir 'latest.md')"
