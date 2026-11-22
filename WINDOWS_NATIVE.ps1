# AIXO Collision Wall RC1 - Windows PowerShell 5.1 / .NET Windows Forms GUI.
# Only talks to the isolated local bridge.py; no network or shell execution from inputs.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$script:Py = $env:AIXO_PY_EXE
$script:BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $script:Py -or -not (Test-Path -LiteralPath $script:Py -PathType Leaf)) {
    [System.Windows.Forms.MessageBox]::Show('Python executable not found. Run START_WINDOWS.cmd.','AIXO / Preflight') | Out-Null
    exit 2
}

function Invoke-Wall {
    param([string]$Action, [hashtable]$Parameters = @{})
    $payload = @{action=$Action; args=$Parameters} | ConvertTo-Json -Compress -Depth 14
    $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($payload))
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $script:Py
    $info.Arguments = '-u "' + (Join-Path $script:BaseDir 'bridge.py') + '"'
    $info.WorkingDirectory = $script:BaseDir
    $info.UseShellExecute = $false
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.CreateNoWindow = $true
    $info.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $info
    try {
        if (-not $proc.Start()) { throw 'Unable to start local engine process' }
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $errTask = $proc.StandardError.ReadToEndAsync()
        $proc.StandardInput.WriteLine($b64)
        $proc.StandardInput.Close()
        if (-not $proc.WaitForExit(45000)) {
            try { $proc.Kill() } catch {}
            throw ('AIXO engine timed out on ' + $Action)
        }
        $out = $outTask.Result
        $err = $errTask.Result
        if ([string]::IsNullOrWhiteSpace($out)) {
            throw ('No JSON reply from engine. Exit=' + $proc.ExitCode + "`n" + $err)
        }
        try { $reply = $out | ConvertFrom-Json } catch { throw ('Invalid engine reply: ' + $out.Substring(0,[Math]::Min(500,$out.Length))) }
        if (-not $reply.ok) { throw ('Engine rejected ' + $Action + ': ' + $reply.error) }
        if ($proc.ExitCode -ne 0) { throw ('Engine exit ' + $proc.ExitCode + "`n" + $err) }
        return $reply.data
    } finally {
        $proc.Dispose()
    }
}

function Error-Dialog([string]$Message) {
    [System.Windows.Forms.MessageBox]::Show($Message,'AIXO / OPERATION BLOCKED', 'OK','Error') | Out-Null
    $script:status.Text = 'REJECTED / ' + $Message
}
function Safe-Action([scriptblock]$Body) {
    try { & $Body } catch { Error-Dialog ([string]$_) }
}
function Prompt-Text([string]$Title,[string]$Help,[string]$Initial='', [bool]$Multiline=$true, [bool]$Readonly=$false) {
    $popup = New-Object System.Windows.Forms.Form
    $popup.Text = 'AIXO / ' + $Title
    $popup.Size = [System.Drawing.Size]::new(650,440)
    $popup.StartPosition = 'CenterParent'
    $popup.BackColor = [System.Drawing.Color]::FromArgb(10,16,12)
    $label = New-Object System.Windows.Forms.Label
    $label.Text=$Help
    $label.ForeColor=[System.Drawing.Color]::Lime
    $label.Dock='Top';$label.Height=48
    $label.Padding=[System.Windows.Forms.Padding]::new(12)
    $entry = New-Object System.Windows.Forms.TextBox
    $entry.Multiline=$Multiline
    $entry.ScrollBars='Vertical'
    $entry.AcceptsReturn=$Multiline
    $entry.WordWrap=$true
    $entry.BackColor=[System.Drawing.Color]::FromArgb(17,29,20)
    $entry.ForeColor=[System.Drawing.Color]::WhiteSmoke
    $entry.Font=[System.Drawing.Font]::new('Consolas',11)
    $entry.Text=$Initial
    $entry.ReadOnly=$Readonly
    $entry.Dock='Fill'
    $bar=New-Object System.Windows.Forms.FlowLayoutPanel
    $bar.Height=50;$bar.Dock='Bottom';$bar.FlowDirection='RightToLeft'
    $ok=New-Object System.Windows.Forms.Button
    $ok.Text= $(if ($Readonly) { 'CLOSE' } else { 'CONFIRM' });$ok.Width=110;$ok.Height=34
    $ok.DialogResult='OK';$bar.Controls.Add($ok)
    if (-not $Readonly) {
        $cancel=New-Object System.Windows.Forms.Button
        $cancel.Text='CANCEL';$cancel.Width=100;$cancel.Height=34;$cancel.DialogResult='Cancel';$bar.Controls.Add($cancel)
    }
    $popup.Controls.Add($entry);$popup.Controls.Add($bar);$popup.Controls.Add($label)
    $popup.AcceptButton=$ok
    $response=$popup.ShowDialog($script:form)
    $value=if($response -eq 'OK'){$entry.Text}else{$null}
    $popup.Dispose()
    return $value
}
function Selected-Id {
    if (-not $script:selectedId) { throw 'Select one marble first.' }
    return $script:selectedId
}
function Add-Button($Container,[string]$Label,[scriptblock]$Callback) {
    $button=New-Object System.Windows.Forms.Button
    $button.Text=$Label
    $button.AutoSize=$false
    $button.Width=115
    $button.Height=37
    $button.BackColor=[System.Drawing.Color]::FromArgb(19,47,27)
    $button.ForeColor=[System.Drawing.Color]::FromArgb(155,255,126)
    $button.FlatStyle='Flat'
    $button.FlatAppearance.BorderColor=[System.Drawing.Color]::FromArgb(55,110,61)
    $button.Font=[System.Drawing.Font]::new('Segoe UI',9,[System.Drawing.FontStyle]::Bold)
    $button.Add_Click($Callback)
    [void]$Container.Controls.Add($button)
}

$script:form=New-Object System.Windows.Forms.Form
$script:form.Text='OX / AIXO Collision Wall RC1 - native Windows'
$script:form.StartPosition='CenterScreen'
$script:form.Size=[System.Drawing.Size]::new(1210,810)
$script:form.MinimumSize=[System.Drawing.Size]::new(940,660)
$script:form.BackColor=[System.Drawing.Color]::FromArgb(8,14,10)
$script:form.ForeColor=[System.Drawing.Color]::WhiteSmoke
$script:form.Font=[System.Drawing.Font]::new('Segoe UI',10)

$top=New-Object System.Windows.Forms.FlowLayoutPanel
$top.Dock='Top';$top.Height=89;$top.AutoScroll=$true;$top.WrapContents=$true
$top.BackColor=[System.Drawing.Color]::FromArgb(12,22,16)
$foot=New-Object System.Windows.Forms.FlowLayoutPanel
$foot.Dock='Bottom';$foot.Height=96;$foot.AutoScroll=$true;$foot.WrapContents=$true
$foot.BackColor=[System.Drawing.Color]::FromArgb(12,22,16)
$script:status=New-Object System.Windows.Forms.Label
$script:status.Dock='Bottom';$script:status.Height=27
$script:status.ForeColor=[System.Drawing.Color]::Lime
$script:status.BackColor=[System.Drawing.Color]::FromArgb(16,35,19)
$script:status.Text='LOCAL / ISOLATED / NO MODEL CALLS / NO EXTERNAL SYSTEM WRITES'

$middle=New-Object System.Windows.Forms.SplitContainer
$middle.Dock='Fill';$middle.Orientation='Vertical';$middle.Size=[System.Drawing.Size]::new(1160,560);$middle.SplitterDistance=550
$middle.BackColor=[System.Drawing.Color]::FromArgb(28,65,36)

$left=New-Object System.Windows.Forms.TableLayoutPanel
$left.Dock='Fill';$left.ColumnCount=1;$left.RowCount=4;$left.Padding=[System.Windows.Forms.Padding]::new(8)
$left.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute,35)) | Out-Null
$left.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Percent,70)) | Out-Null
$left.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute,36)) | Out-Null
$left.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Percent,30)) | Out-Null

$right=New-Object System.Windows.Forms.TableLayoutPanel
$right.Dock='Fill';$right.ColumnCount=1;$right.RowCount=4;$right.Padding=[System.Windows.Forms.Padding]::new(8)
$right.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute,35)) | Out-Null
$right.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Percent,67)) | Out-Null
$right.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute,36)) | Out-Null
$right.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Percent,33)) | Out-Null

function Label-Line([string]$Text) {
    $label=New-Object System.Windows.Forms.Label
    $label.Text=$Text;$label.Dock='Fill'
    $label.Font=[System.Drawing.Font]::new('Consolas',11,[System.Drawing.FontStyle]::Bold)
    $label.ForeColor=[System.Drawing.Color]::Lime
    return $label
}
$script:inventory=New-Object System.Windows.Forms.ListView
$script:inventory.View='Details';$script:inventory.FullRowSelect=$true;$script:inventory.MultiSelect=$false
$script:inventory.GridLines=$true;$script:inventory.Dock='Fill'
$script:inventory.BackColor=[System.Drawing.Color]::FromArgb(17,28,20)
$script:inventory.ForeColor=[System.Drawing.Color]::WhiteSmoke
[void]$script:inventory.Columns.Add('MARBLE',295)
[void]$script:inventory.Columns.Add('KIND',100)
[void]$script:inventory.Columns.Add('STATUS',100)
$script:choices=New-Object System.Windows.Forms.ListBox
$script:choices.Dock='Fill'
$script:choices.BackColor=[System.Drawing.Color]::FromArgb(17,28,20)
$script:choices.ForeColor=[System.Drawing.Color]::WhiteSmoke
$script:choices.Font=[System.Drawing.Font]::new('Consolas',9)
$script:detail=New-Object System.Windows.Forms.TextBox
$script:detail.Dock='Fill';$script:detail.Multiline=$true;$script:detail.ReadOnly=$true
$script:detail.ScrollBars='Both';$script:detail.WordWrap=$true
$script:detail.BackColor=[System.Drawing.Color]::FromArgb(17,28,20)
$script:detail.ForeColor=[System.Drawing.Color]::WhiteSmoke
$script:detail.Font=[System.Drawing.Font]::new('Consolas',10)
$script:events=New-Object System.Windows.Forms.ListBox
$script:events.Dock='Fill'
$script:events.BackColor=[System.Drawing.Color]::FromArgb(17,28,20)
$script:events.ForeColor=[System.Drawing.Color]::Silver
$script:events.Font=[System.Drawing.Font]::new('Consolas',9)
$left.Controls.Add((Label-Line '01 / MARBLES'),0,0)
$left.Controls.Add($script:inventory,0,1)
$left.Controls.Add((Label-Line '02 / COLLISION CANDIDATES - NOT FACTS'),0,2)
$left.Controls.Add($script:choices,0,3)
$right.Controls.Add((Label-Line '03 / SELECTED MARBLE'),0,0)
$right.Controls.Add($script:detail,0,1)
$right.Controls.Add((Label-Line '04 / EVENT RECORDS'),0,2)
$right.Controls.Add($script:events,0,3)
$middle.Panel1.Controls.Add($left)
$middle.Panel2.Controls.Add($right)
$shell=New-Object System.Windows.Forms.TableLayoutPanel
$shell.Dock='Fill';$shell.ColumnCount=1;$shell.RowCount=4
$shell.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute,89)) | Out-Null
$shell.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Percent,100)) | Out-Null
$shell.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute,96)) | Out-Null
$shell.RowStyles.Add([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute,27)) | Out-Null
$shell.Controls.Add($top,0,0)
$shell.Controls.Add($middle,0,1)
$shell.Controls.Add($foot,0,2)
$shell.Controls.Add($script:status,0,3)
$script:form.Controls.Add($shell)
$script:selectedId=$null
$script:candidates=@()
$script:refreshing=$false

function Refresh-Selected {
    if ($script:refreshing) {return}
    if ($script:inventory.SelectedItems.Count -eq 0) {return}
    $script:selectedId=[string]$script:inventory.SelectedItems[0].Tag
    Safe-Action {
        $item=Invoke-Wall 'get' @{id=$script:selectedId}
        $script:detail.Text = @"
TITLE: $($item.title)
ID: $($item.id)
TYPE: $($item.kind) | STATUS: $($item.status)
DEPTH: $($item.depth)
PARENT: $($item.parent_id)
SOURCE: $($item.source)
CREATED: $($item.created_at)

$($item.body)

SHA256: $($item.body_hash)
"@
    }
}
$script:inventory.Add_SelectedIndexChanged({ Refresh-Selected })

function Refresh-All {
    $current=$script:selectedId
    $script:refreshing=$true
    try {
        $marbles=@(Invoke-Wall 'list')
        $candidates=@(Invoke-Wall 'candidates')
        $events=@(Invoke-Wall 'events')
        $stats=Invoke-Wall 'stats'
        $script:inventory.BeginUpdate()
        try {
            $script:inventory.Items.Clear()
            foreach ($m in $marbles) {
                if ($null -eq $m) {continue}
                $r=New-Object System.Windows.Forms.ListViewItem([string]$m.title)
                [void]$r.SubItems.Add([string]$m.kind)
                [void]$r.SubItems.Add([string]$m.status)
                $r.Tag=[string]$m.id
                [void]$script:inventory.Items.Add($r)
                if ($r.Tag -eq $current) {$r.Selected=$true}
            }
        } finally {$script:inventory.EndUpdate()}
        $script:choices.Items.Clear()
        $script:candidates=@($candidates | Where-Object {$null -ne $_ -and $_.state -eq 'suggested'})
        foreach ($c in $script:candidates) {
            [void]$script:choices.Items.Add(('{0:N2} / {1} <-> {2}' -f $c.score,$c.a_title,$c.b_title))
        }
        $script:events.Items.Clear()
        foreach ($ev in $events) {
            if ($null -ne $ev) { [void]$script:events.Items.Add(('{0:00000} / {1} / {2}' -f [int]$ev.seq,$ev.action,([string]$ev.subject).Substring(0,8))) }
        }
        $script:status.Text=('MARBLES: {0}  EDGES: {1}  EVENTS: {2}   /  LOCAL + ISOLATED' -f $stats.marbles,$stats.edges,$stats.events)
    } finally {$script:refreshing=$false}
    if ($script:inventory.SelectedItems.Count -gt 0) {Refresh-Selected}
    elseif ($script:inventory.Items.Count -gt 0 -and -not $current) {
        $script:inventory.Items[0].Selected=$true
        Refresh-Selected
    }
}
function Commit-And-Refresh([string]$Message) {
    Refresh-All
    $script:status.Text=$Message
}

Add-Button $top 'ADD MARBLE' {
    Safe-Action {
        $title=Prompt-Text 'ADD' 'Give this original thought a title' '' $false
        if ($null -eq $title) {return}
        $body=Prompt-Text 'ADD' 'Enter the complete source thought (kept unchanged)' '' $true
        if ($null -eq $body) {return}
        $r=Invoke-Wall 'add' @{title=$title;body=$body}
        $script:selectedId=$r.id;Commit-And-Refresh 'ORIGINAL MARBLE SAVED'
    }
}
Add-Button $top 'SLICE' {
    Safe-Action {
        $id=Selected-Id
        $orig=Invoke-Wall 'get' @{id=$id}
        $excerpt=Prompt-Text 'SLICE' 'Use an EXACT excerpt of the original content' ([string]$orig.body) $true
        if ($null -eq $excerpt) {return}
        $r=Invoke-Wall 'slice' @{id=$id;excerpt=$excerpt}
        $script:selectedId=$r.id;Commit-And-Refresh 'SLICE SAVED - PARENT PRESERVED'
    }
}
Add-Button $top 'MUTATE' {
    Safe-Action {
        $id=Selected-Id
        $orig=Invoke-Wall 'get' @{id=$id}
        $body=Prompt-Text 'MUTATE' 'Propose a changed version (the original remains immutable)' ([string]$orig.body) $true
        if ($null -eq $body) {return}
        $r=Invoke-Wall 'mutate' @{id=$id;new_body=$body}
        $script:selectedId=$r.id;Commit-And-Refresh 'REVISION PROPOSED - ORIGINAL PRESERVED'
    }
}
Add-Button $top 'MULTIPLY' {
    Safe-Action {
        $id=Selected-Id
        $raw=Prompt-Text 'MULTIPLY' 'Use 1 to 5 lines: TITLE | BRANCH CONTENT' 'Investigation A | Examine the first possible interpretation' $true
        if ($null -eq $raw) {return}
        $branches=@()
        foreach ($line in ($raw -split "`r?`n")) {
            if (-not $line.Trim()) {continue}
            if (-not $line.Contains('|')) {throw 'Each branch must use TITLE | BODY'}
            $splitAt=$line.IndexOf('|')
            $parts=@($line.Substring(0,$splitAt),$line.Substring($splitAt+1))
            $branches+=@{title=$parts[0].Trim();body=$parts[1].Trim()}
        }
        $r=Invoke-Wall 'multiply' @{id=$id;branches=@($branches)}
        $script:selectedId=$r.ids[0];Commit-And-Refresh 'MULTIPLICATION COMMITTED ATOMICALLY'
    }
}
Add-Button $top 'CONNECT' {
    Safe-Action {
        $id=Selected-Id
        $other=Prompt-Text 'CONNECT' 'Paste the full target marble ID (seen in details)' '' $false
        if ($null -eq $other) {return}
        $relation=Prompt-Text 'CONNECT' 'Enter COLLIDE, RECONCILE, SUPPORTS or CONTRADICTS' 'RECONCILE' $false
        if ($null -eq $relation) {return}
        $r=Invoke-Wall 'connect' @{left=$id;right=$other.Trim();relation=$relation.Trim().ToUpperInvariant()}
        Commit-And-Refresh 'RELATION RECORDED (NOT VERIFIED)'
    }
}
Add-Button $top 'REVIEW' {
    Safe-Action {
        $id=Selected-Id
        $state=Prompt-Text 'REVIEW' 'Status: reviewed / rejected / candidate' 'reviewed' $false
        if ($null -eq $state) {return}
        $reason=Prompt-Text 'REVIEW' 'Why? Record evidence; this does NOT prove truth.' '' $true
        if ($null -eq $reason) {return}
        $null=Invoke-Wall 'review' @{id=$id;state=$state.Trim().ToLowerInvariant();evidence=$reason}
        Commit-And-Refresh 'HUMAN REVIEW RECORDED'
    }
}
Add-Button $top 'REVERSE TRACE' {
    Safe-Action {
        $id=Selected-Id
        $t=Invoke-Wall 'trace' @{id=$id}
        $txt="ANCESTRY / ORIGINAL -> SELECTED`r`n"
        foreach($a in $t.ancestors){$txt+="`r`n$($a.depth): $($a.title) / $($a.id)"}
        $txt+="`r`n`r`nDESCENDANTS`r`n"
        foreach($d in $t.descendants){$txt+="`r`n$($d.depth): $($d.title) / $($d.id)"}
        $txt+="`r`n`r`nRELATIONSHIPS`r`n"
        foreach($r in $t.relationships){$txt+="`r`n$($r.relation): $($r.other_title)"}
        $null=Prompt-Text 'REVERSE TRACE' 'Read-only: causal ancestry and linked relationships' $txt $true $true
    }
}

Add-Button $foot 'SCAN QUEUE' {
    Safe-Action {$r=Invoke-Wall 'scan';Commit-And-Refresh ('PROCESSED ' + @($r.processed).Count + ' JOBS')}
}
Add-Button $foot 'DEMO DATA' {
    Safe-Action {
        if([System.Windows.Forms.MessageBox]::Show('Insert six test marbles? Existing data is never cleared.','AIXO / Demo','YesNo','Question') -ne 'Yes'){return}
        $r=Invoke-Wall 'demo';Commit-And-Refresh 'SIX DEMO MARBLES ADDED'
    }
}
Add-Button $foot 'ACCEPT LINK' {
    Safe-Action {
        $idx=$script:choices.SelectedIndex
        if($idx -lt 0){throw 'Select one suggested collision first'}
        $c=$script:candidates[$idx]
        if([System.Windows.Forms.MessageBox]::Show('Record a proposed COLLIDE link? This does not verify the claim.','AIXO / Review','YesNo','Question') -ne 'Yes'){return}
        $r=Invoke-Wall 'decide' @{id=$c.id;accept=$true}
        Commit-And-Refresh 'CANDIDATE LINK ACCEPTED'
    }
}
Add-Button $foot 'DISMISS LINK' {
    Safe-Action {
        $idx=$script:choices.SelectedIndex
        if($idx -lt 0){throw 'Select one suggested collision first'}
        $c=$script:candidates[$idx]
        $null=Invoke-Wall 'decide' @{id=$c.id;accept=$false}
        Commit-And-Refresh 'CANDIDATE DISMISSED'
    }
}
Add-Button $foot 'INTEGRITY' {
    Safe-Action {
        $r=Invoke-Wall 'verify'
        if($r.ok){[System.Windows.Forms.MessageBox]::Show('PASS - SQLite + event chain + graph replay agree.','AIXO / Integrity') | Out-Null}
        else {Error-Dialog ('Integrity failed: ' + ($r.errors -join '; '))}
    }
}
Add-Button $foot 'BACKUP' {
    Safe-Action {
        $r=Invoke-Wall 'backup'
        [System.Windows.Forms.MessageBox]::Show(('Verified backup created at:' + "`r`n" + $r.path),'AIXO / Backup') | Out-Null
    }
}
Add-Button $foot 'RESTORE NEW' {
    Safe-Action {
        $pick=New-Object System.Windows.Forms.OpenFileDialog
        $pick.Title='Choose verified AIXO backup';$pick.Filter='SQLite (*.sqlite3)|*.sqlite3|All files|*.*'
        if($pick.ShowDialog($script:form) -ne 'OK'){return}
        $save=New-Object System.Windows.Forms.SaveFileDialog
        $save.Title='Choose NEW database filename - never replaces existing';$save.Filter='SQLite (*.sqlite3)|*.sqlite3';$save.DefaultExt='sqlite3';$save.OverwritePrompt=$true
        if($save.ShowDialog($script:form) -ne 'OK'){return}
        if(Test-Path -LiteralPath $save.FileName){throw 'Target already exists. Restore only to a NEW file.'}
        $r=Invoke-Wall 'restore-new' @{backup=$pick.FileName;target=$save.FileName}
        [System.Windows.Forms.MessageBox]::Show(('Restored into a NEW copy:' + "`r`n" + $r.path + "`r`nActive workspace unchanged."),'AIXO / Restore') | Out-Null
    }
}
Add-Button $foot 'EXPORT JSON' {
    Safe-Action {
        $save=New-Object System.Windows.Forms.SaveFileDialog
        $save.Title='Export a Thought Spine REVIEW packet (no auto import)';$save.Filter='JSON (*.json)|*.json';$save.DefaultExt='json'
        if($save.ShowDialog($script:form) -ne 'OK'){return}
        if(Test-Path -LiteralPath $save.FileName){throw 'Destination exists. Choose a new filename.'}
        $r=Invoke-Wall 'export' @{path=$save.FileName}
        [System.Windows.Forms.MessageBox]::Show(('Explicit review packet written:' + "`r`n" + $r.path),'AIXO / Export') | Out-Null
    }
}
Add-Button $foot 'REFRESH' { Safe-Action {Refresh-All} }

$script:workerTimer = New-Object System.Windows.Forms.Timer
$script:workerTimer.Interval=4500
$script:workerTimer.Add_Tick({
    try {
        $health=Invoke-Wall 'stats'
        if ($health.jobs.pending -gt 0) {
            $processed=Invoke-Wall 'scan'
            if (@($processed.processed).Count -gt 0) {Refresh-All}
        }
    } catch {
        $script:workerTimer.Stop()
        $script:status.Text='QUEUE PAUSED / '+[string]$_
    }
})
try {
    $init=Invoke-Wall 'verify' 
    if(-not $init.ok){throw ('Existing data failed verification: '+($init.errors -join '; '))}
    Refresh-All
    $script:workerTimer.Start()
    [void]$script:form.ShowDialog()
} catch {
    [System.Windows.Forms.MessageBox]::Show([string]$_,'AIXO / STARTUP BLOCKED','OK','Error') | Out-Null
    exit 2
} finally { $script:workerTimer.Stop(); $script:workerTimer.Dispose(); $script:form.Dispose() }
