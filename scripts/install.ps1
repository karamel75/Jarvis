# JARVIS — installation sous Windows 10/11
# Usage (PowerShell, depuis le dossier du projet) :
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Step($msg) { Write-Host "`n▸ $msg" -ForegroundColor Cyan }

Step "Python 3.12"
function Invoke-Py([string]$cmd, [string[]]$more) {
    $parts = $cmd -split " "
    $rest = @($parts | Select-Object -Skip 1) + $more
    & $parts[0] @rest
}
$py = $null
foreach ($cand in @("py -3.12", "py -3.11", "python")) {
    try {
        if ((Invoke-Py $cand @("-c", "import sys; print(sys.version_info >= (3, 11))") 2>$null) -eq "True") { $py = $cand; break }
    } catch {}
}
if (-not $py) {
    Write-Host "Python 3.11+ introuvable : installation de Python 3.12 via winget…"
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $py = "py -3.12"
}
Write-Host "  $py"

Step "Environnement virtuel .venv"
if (-not (Test-Path .venv)) { Invoke-Py $py @("-m", "venv", ".venv") }
$venvPy = ".\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip wheel
& $venvPy -m pip install -e ".[dev]"

Step "Configuration"
if (-not (Test-Path config.yaml)) { Copy-Item config.example.yaml config.yaml; Write-Host "  config.yaml créé" }

Step "Modèles locaux (mot-clé + transcription, une seule fois)"
& $venvPy -c "import openwakeword.utils as u; u.download_models(model_names=['hey_jarvis'])"
& $venvPy -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

Step "WebView2 (fenêtre du globe)"
$wv = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue
if ($wv) { Write-Host "  présent ($($wv.pv))" } else { winget install -e --id Microsoft.EdgeWebView2Runtime }

Write-Host "`nInstallation terminée. Ensuite :" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\jarvis setup     # clés Anthropic + ElevenLabs, voice_id, Obsidian"
Write-Host "  .\.venv\Scripts\jarvis doctor    # diagnostic"
Write-Host "  .\.venv\Scripts\jarvis preview   # voir le globe"
Write-Host "  .\.venv\Scripts\jarvis run       # « Hey Jarvis »"
