# AIXO Local Bridge M0.2 - PowerShell 5.1 Windows Forms operator surface.
# No Tkinter, no HTTP server, no automatic imports or owner-store modification.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$script:Py = $env:AIXO_PY_EXE
$script:Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $script:Py -or -not (Test-Path -LiteralPath $script:Py -PathType Leaf)) {
  [System.Windows.Forms.MessageBox]::Show('No Python was selected. Start with START_BRIDGE_WINDOWS.cmd','AIXO Bridge') | Out-Null
  exit 2
}
function Invoke-LocalBridge {
  param([string]$Action, [hashtable]$Args = @{})
  $request = @{schema='aixo.local-bridge.request.v1'; action=$Action; args=$Args} | ConvertTo-Json -Compress -Depth 30
  $data = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($request))
  $info=New-Object System.Diagnostics.ProcessStartInfo
  $info.FileName=$script:Py
  $info.Arguments='-u "' + (Join-Path $script:Root 'bridge_protocol.py') + '"'
  $info.WorkingDirectory=$script:Root
  $info.UseShellExecute=$false
  $info.RedirectStandardInput=$true
  $info.RedirectStandardOutput=$true
  $info.RedirectStandardError=$true
  $info.CreateNoWindow=$true
  $info.EnvironmentVariables['PYTHONIOENCODING']='utf-8'
  $proc=New-Object System.Diagnostics.Process
  $proc.StartInfo=$info
  try {
    if (-not $proc.Start()){throw 'Cannot start bridge process'}
    $output=$proc.StandardOutput.ReadToEndAsync()
    $errorText=$proc.StandardError.ReadToEndAsync()
    $proc.StandardInput.WriteLine($data)
    $proc.StandardInput.Close()
    if (-not $proc.WaitForExit(45000)) {
      try{$proc.Kill()}catch{}
      throw ('Bridge timed out on ' + $Action)
    }
    $content=$output.Result
    if ([string]::IsNullOrWhiteSpace($content)){throw ('No JSON response. '+$errorText.Result)}
    try{$reply=$content | ConvertFrom-Json}catch{throw ('Malformed JSON response: ' + $content.Substring(0,[Math]::Min(300,$content.Length)))}
    if (-not $reply.ok){throw ('Bridge rejected '+$Action+': '+$reply.error)}
    if ($proc.ExitCode -ne 0){throw ('Bridge exited with '+$proc.ExitCode)}
    return $reply.data
  } finally {$proc.Dispose()}
}
function Render($o){
  $script:results.Text=($o | ConvertTo-Json -Depth 30)
}
function Safe([scriptblock]$operation){
  try {& $operation} catch {
    $script:status.Text='BLOCKED: '+[string]$_
    [System.Windows.Forms.MessageBox]::Show([string]$_,'AIXO Bridge - operation blocked','OK','Error') | Out-Null
  }
}
function Btn([string]$text,[scriptblock]$handler){
  $b=New-Object System.Windows.Forms.Button
  $b.Text=$text;$b.Width=135;$b.Height=37
  $b.BackColor=[System.Drawing.Color]::FromArgb(22,52,29)
  $b.ForeColor=[System.Drawing.Color]::LightGreen
  $b.FlatStyle='Flat'
  $b.Add_Click($handler)
  [void]$script:buttons.Controls.Add($b)
}
$script:form=New-Object System.Windows.Forms.Form
$script:form.Text='OX / AIXO Local Bridge M0.2 - source review and handoff'
$script:form.Size=[System.Drawing.Size]::new(1120,750)
$script:form.MinimumSize=[System.Drawing.Size]::new(860,560)
$script:form.StartPosition='CenterScreen'
$script:form.Font=[System.Drawing.Font]::new('Segoe UI',10)
$script:form.ForeColor=[System.Drawing.Color]::WhiteSmoke
$script:form.BackColor=[System.Drawing.Color]::FromArgb(8,15,11)

$sourceRow=New-Object System.Windows.Forms.FlowLayoutPanel
$sourceRow.Dock='Top';$sourceRow.Height=49;$sourceRow.WrapContents=$false
$sourceRow.AutoScroll=$true
$sourceLabel=New-Object System.Windows.Forms.Label
$sourceLabel.Text='GREMLIN JSON:';$sourceLabel.Width=120;$sourceLabel.Height=33
$sourceRow.Controls.Add($sourceLabel)
$script:source=New-Object System.Windows.Forms.TextBox
$script:source.Width=680;$script:source.ReadOnly=$true;$script:source.Height=33
$script:source.BackColor=[System.Drawing.Color]::FromArgb(20,29,23)
$script:source.ForeColor=[System.Drawing.Color]::WhiteSmoke
$sourceRow.Controls.Add($script:source)
$open=New-Object System.Windows.Forms.Button
$open.Text='CHOOSE FILE';$open.Width=125;$open.Height=31
$open.Add_Click({Safe {
  $d=New-Object System.Windows.Forms.OpenFileDialog
  $d.Filter='GREMLIN JSON (*.json)|*.json|All files (*.*)|*.*'
  $d.CheckFileExists=$true
  if($d.ShowDialog($script:form) -eq 'OK'){
    $script:source.Text=$d.FileName
    $script:previewHash=$null
    $script:results.Text='Selected new file. Click PREVIEW before importing.'
  }
  $d.Dispose()
}})
$sourceRow.Controls.Add($open)

$options=New-Object System.Windows.Forms.FlowLayoutPanel
$options.Dock='Top';$options.Height=48;$options.WrapContents=$false
$nLabel=New-Object System.Windows.Forms.Label
$nLabel.Text='NAMESPACE:';$nLabel.Width=120;$nLabel.Height=31
$options.Controls.Add($nLabel)
$script:namespace=New-Object System.Windows.Forms.TextBox
$script:namespace.Width=190;$script:namespace.Text='gremlin-local'
$options.Controls.Add($script:namespace)
$script:revision=New-Object System.Windows.Forms.CheckBox
$script:revision.Width=370;$script:revision.Text='Allow separately approved source revisions'
$options.Controls.Add($script:revision)
$notice=New-Object System.Windows.Forms.Label
$notice.Text='Offline / explicit review only';$notice.Width=230;$notice.Height=31
$options.Controls.Add($notice)

$script:buttons=New-Object System.Windows.Forms.FlowLayoutPanel
$script:buttons.Dock='Top';$script:buttons.Height=95;$script:buttons.WrapContents=$true
$script:buttons.AutoScroll=$true
$script:buttons.BackColor=[System.Drawing.Color]::FromArgb(11,23,16)

$script:status=New-Object System.Windows.Forms.Label
$script:status.Dock='Bottom';$script:status.Height=32
$script:status.ForeColor=[System.Drawing.Color]::Lime
$script:status.Text='READY / PREVIEW IS READ-ONLY TO GREMLIN / NO AUTOMATIC SYNC'
$script:results=New-Object System.Windows.Forms.TextBox
$script:results.Multiline=$true;$script:results.Dock='Fill';$script:results.ReadOnly=$true
$script:results.ScrollBars='Both';$script:results.WordWrap=$false
$script:results.Font=[System.Drawing.Font]::new('Consolas',10)
$script:results.BackColor=[System.Drawing.Color]::FromArgb(15,28,20)
$script:results.ForeColor=[System.Drawing.Color]::FromArgb(178,246,178)
$script:results.Text='Select an explicit GREMLIN JSON export. PREVIEW → APPROVE IMPORT → SCAN → VERIFY → EXPORT REVIEW. Original GREMLIN files remain unchanged.'
$script:previewHash=$null
$script:previewNamespace=$null

Btn 'PREFLIGHT' { Safe {Render (Invoke-LocalBridge 'health');$script:status.Text='BRIDGE READY'} }
Btn 'PREVIEW' { Safe {
  if(-not $script:source.Text){throw 'Choose a GREMLIN JSON export first'}
  $ns=$script:namespace.Text.Trim()
  $out=Invoke-LocalBridge 'preview' @{path=$script:source.Text;namespace=$ns}
  $script:previewHash=$out.export_sha256
  $script:previewNamespace=$ns
  Render $out
  $script:status.Text='PREVIEW ONLY / '+$out.count+' ENTRIES / NO IMPORT'
} }
Btn 'APPROVE IMPORT' { Safe {
  if(-not $script:previewHash -or $script:previewNamespace -ne $script:namespace.Text.Trim()){
    throw 'PREVIEW the current file/namespace before importing'
  }
  $yes=[System.Windows.Forms.MessageBox]::Show('Append the explicitly previewed GREMLIN entries to the isolated AIXO store? This never writes to GREMLIN.','AIXO / Confirm import','YesNo','Warning')
  if($yes -ne 'Yes'){return}
  if($script:revision.Checked){
    $yes2=[System.Windows.Forms.MessageBox]::Show('You have enabled revisions. Existing original marbles remain unchanged. Create new descendant marbles for edited entries?','AIXO / Confirm revisions','YesNo','Warning')
    if($yes2 -ne 'Yes'){return}
  }
  $out=Invoke-LocalBridge 'import' @{path=$script:source.Text;namespace=$script:namespace.Text.Trim();expected_sha256=$script:previewHash;allow_revisions=[bool]$script:revision.Checked;selected_ids=$null}
  Render $out;$script:status.Text='IMPORT FINISHED / inspect outcomes / source unchanged'
  $script:previewHash=$null
} }
Btn 'SCAN COLLISIONS' { Safe {Render (Invoke-LocalBridge 'scan');$script:status.Text='LOCAL DETERMINISTIC COLLISION SCAN COMPLETE'} }
Btn 'VERIFY' { Safe {
  $out=Invoke-LocalBridge 'verify';Render $out
  if($out.ok){$script:status.Text='G0 STORE INTEGRITY PASSED'}else{$script:status.Text='G0 INTEGRITY FAILED / DO NOT EXPORT'}
} }
Btn 'RECEIPTS' { Safe {
  Render (Invoke-LocalBridge 'receipts' @{namespace=$script:namespace.Text.Trim()})
  $script:status.Text='LOCAL IMPORT RECEIPTS / ORIGINAL JSON PRESERVED'
} }
Btn 'EXPORT REVIEW' { Safe {
  $pick=New-Object System.Windows.Forms.FolderBrowserDialog
  $pick.Description='Choose an existing folder for NEW Thought Spine review files'
  if($pick.ShowDialog($script:form) -eq 'OK'){
    Render (Invoke-LocalBridge 'export' @{folder=$pick.SelectedPath;namespace=$script:namespace.Text.Trim()})
    $script:status.Text='NEW REVIEW MARKDOWN CREATED / IMPORT MANUALLY INTO THOUGHT SPINE'
  }
  $pick.Dispose()
} }
Btn 'BACKUP BOTH' { Safe {
  $pick=New-Object System.Windows.Forms.FolderBrowserDialog
  $pick.Description='Choose an existing folder for a verified backup pair'
  if($pick.ShowDialog($script:form) -eq 'OK'){
    Render (Invoke-LocalBridge 'backup' @{folder=$pick.SelectedPath})
    $script:status.Text='BACKUP COPY VERIFIED / NOT AUTOMATIC RESTORE'
  }
  $pick.Dispose()
} }

$script:form.Controls.Add($script:results)
$script:form.Controls.Add($script:status)
$script:form.Controls.Add($script:buttons)
$script:form.Controls.Add($options)
$script:form.Controls.Add($sourceRow)
try{Render (Invoke-LocalBridge 'health')}catch{$script:results.Text='Initial health check failed: '+[string]$_}
[void]$script:form.ShowDialog()
$script:form.Dispose()
