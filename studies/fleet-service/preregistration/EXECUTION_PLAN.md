# 外部子车队检验执行计划

从研究库根目录使用 PowerShell 7。运行记录提供下列环境变量的实际值：UM_OFFLINE_ROOT（无远端的离线库根）、UM_STAGE_ARCHIVE（新阶段目录）、UM_TRACK_SOURCE（登记源文件）、UM_REGISTRATION（已提交的正文）、UM_OPENING_AUTHORIZATION（外部开封轮的已提交授权文件）、UM_DEADLINE（含时区的绝对截止时间）、UM_RUN_ID（离线运行编号）。原队列彩排使用新运行目录下的 rehearsal，不设置授权文件。先确认研究工作区干净及正文、计划和附录的 SHA-256。正式开封还须有独立时间戳、比特币区块证明和用户同意开封的原话。开封授权文件名为 OPENING_AUTHORIZATION.md，含同意原话并在独立一行列出正文 SHA-256。它与正文同属一个无远端离线库。

```powershell
$ErrorActionPreference = 'Stop'
$Root = $env:UM_OFFLINE_ROOT
$Archive = $env:UM_STAGE_ARCHIVE
$Source = $env:UM_TRACK_SOURCE
$Prereg = $env:UM_REGISTRATION
$Authorization = $env:UM_OPENING_AUTHORIZATION
$Deadline = $env:UM_DEADLINE
$RunId = $env:UM_RUN_ID
$Py = (Resolve-Path '.venv/Scripts/python.exe').Path
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONHASHSEED = '0'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'

function Run-Stage([string]$Cohort, [int]$Stage) {
    $cmdArgs = @('-B','-m','um_charging.m11_external_run','--archive',$Archive,
                 '--cohort',$Cohort,'--stage',$Stage,'--registration',$Prereg,'--deadline',$Deadline)
    if ($Stage -lt 4) { $cmdArgs += @('--source',$Source) }
    if ($Cohort -ne '1-5') { $cmdArgs += @('--authorization',$Authorization) }
    & $Py @cmdArgs
    if ($LASTEXITCODE) { throw '执行中断，保存当前请求记录。' }
}

function Seal-Stage([string]$Cohort, [int]$Stage) {
    $rel = [IO.Path]::GetRelativePath($Root, $Archive)
    $names = @("$rel/$Cohort/stage$Stage")
    if (Test-Path -LiteralPath "$Archive/$Cohort/evidence") {
        $names += "$rel/$Cohort/evidence"
    }
    git -C $Root add -- $names
    if ($LASTEXITCODE) { throw '暂存失败' }
    git -C $Root -c gc.auto=0 commit --quiet --only -m "$RunId 外部检验 $Cohort 阶段 $Stage 封存" -- $names
    if ($LASTEXITCODE) { throw '封存失败' }
    git -C $Root log -1 --format='%H %ci'
}
```

两个入口共用上述函数。阶段 1 由程序在内存核对前五名和已发布原队列是否完全一致；失败即停。逐阶段封存队列名单、分期索引、登记、服务证明、年费、主终点及次要结果，适用范围见正文第 11 节。阶段 2、3 核对记录归属与周计数。每一阶段启动前均检查执行提交与登记一致。任何已封存阶段禁止覆盖。

原队列（彩排，事后参照）：

```powershell
foreach ($stage in 1..4) {
    Run-Stage '1-5' $stage
    Seal-Stage '1-5' $stage
}
```

正式开封时按下列顺序使用同一对函数；各阶段分别提交后才进入下一项。前两队列先各做阶段 1，然后各做 2，再各做 3。两份主终点均封存后各做阶段 4。最后按相同流程完成次要队列。任一队列未过门槛，封存跳过原因。

```powershell
foreach ($stage in 1..4) {
    foreach ($cohort in @('6-10','11-15')) {
        Run-Stage $cohort $stage
        Seal-Stage $cohort $stage
    }
}
foreach ($stage in 1..4) {
    Run-Stage '16+' $stage
    Seal-Stage '16+' $stage
}
```

阶段 4 单独封存逐次请求状态清单，含启动但无证书的记录。逐队列用 m11_external_run.verify 重建阶段结论、回放固定服务和购电证书，并检查清单、祖先和逐次记录。原队列修订轮用 m11_verify --verify 指向包含 rehearsal 的本轮目录。开封前的彩排和论文的外部证据分别呈报。四小时到点、程序错误及未封存数据的记录办法见正文和附录。
