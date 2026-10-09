param(
    [switch]$ProbeCom
)

$ErrorActionPreference = "Continue"

function Add-Result {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail = ""
    )
    [pscustomobject]@{
        name = $Name
        status = $Status
        detail = $Detail
    }
}

$results = @()

$wordCandidates = @(
    "C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE"
)
$wordPath = $wordCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $wordPath) {
    $cmd = Get-Command WINWORD.EXE -ErrorAction SilentlyContinue
    if ($cmd) { $wordPath = $cmd.Source }
}
if ($wordPath) {
    $results += Add-Result "word_executable" "pass" $wordPath
} else {
    $results += Add-Result "word_executable" "fail" "WINWORD.EXE not found"
}

$endnoteApps = Get-ItemProperty `
    HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*,`
    HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*,`
    HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -match "EndNote" } |
    Select-Object -First 5 DisplayName,DisplayVersion,InstallLocation

if ($endnoteApps) {
    $details = ($endnoteApps | ForEach-Object { "$($_.DisplayName) $($_.DisplayVersion) $($_.InstallLocation)" }) -join "; "
    $results += Add-Result "endnote_installation" "pass" $details
} else {
    $results += Add-Result "endnote_installation" "fail" "EndNote not found in uninstall registry"
}

$addinKeys = @(
    "HKCU:\Software\Microsoft\Office\Word\Addins\EndNote.WordAddin.Connect",
    "HKLM:\Software\Microsoft\Office\Word\Addins\EndNote.WordAddin.Connect",
    "HKLM:\Software\WOW6432Node\Microsoft\Office\Word\Addins\EndNote.WordAddin.Connect"
)
$addinProps = foreach ($key in $addinKeys) {
    Get-ItemProperty $key -ErrorAction SilentlyContinue
}
if ($addinProps) {
    $details = ($addinProps | ForEach-Object { "LoadBehavior=$($_.LoadBehavior); FriendlyName=$($_.FriendlyName)" }) -join "; "
    $results += Add-Result "cwyw_registry" "pass" $details
} else {
    $results += Add-Result "cwyw_registry" "fail" "EndNote.WordAddin.Connect not registered for Word"
}

if ($ProbeCom -and @(Get-Process WINWORD -ErrorAction SilentlyContinue).Count -gt 0) {
    $results += Add-Result "word_com_cwyw" "skipped" "Word is already running; use the read-only registry results or a separately controlled task instance"
} elseif ($ProbeCom) {
    $word = $null
    try {
        $word = New-Object -ComObject Word.Application
        if ($word.Documents.Count -gt 0) {
            throw "COM returned an instance with existing documents; refusing to change or close it"
        }
        $word.Visible = $false
        $addinMatches = @()
        foreach ($addin in $word.COMAddIns) {
            if (($addin.ProgId -match "EndNote") -or ($addin.Description -match "EndNote|Cite While You Write")) {
                $addinMatches += "$($addin.ProgId): Connect=$($addin.Connect)"
            }
        }
        if ($addinMatches.Count -gt 0) {
            $results += Add-Result "word_com_cwyw" "pass" ($addinMatches -join "; ")
        } else {
            $results += Add-Result "word_com_cwyw" "fail" "Word COM opened but EndNote CWYW add-in was not visible"
        }
    } catch {
        $results += Add-Result "word_com_cwyw" "fail" $_.Exception.Message
    } finally {
        if ($null -ne $word) {
            # Never quit an instance that acquired any document during the probe.
            try {
                if ($word.Documents.Count -eq 0) { $word.Quit() }
            } catch {
                $results += Add-Result "word_com_cleanup" "warning" $_.Exception.Message
            }
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
        }
    }
} else {
    $results += Add-Result "word_com_cwyw" "skipped" "Run with -ProbeCom to test Word COM and CWYW live add-in state"
}

$results | ConvertTo-Json -Depth 4
