# Pousse les variables de src/.env.production vers Coolify via son API
# (tunnel SSH requis : ssh -N -L 8000:localhost:8000 ubuntu@VPS).
# Le jeton est demandé en saisie masquée et ne quitte pas ce terminal.
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot "..\.env.production"),
    [string]$BaseUrl = "http://localhost:8000/api/v1"
)
$ErrorActionPreference = 'Stop'

$sec = Read-Host "Jeton API Coolify" -AsSecureString
$tok = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
# Un collage en console peut injecter CR/LF ou autres caractères de contrôle.
$tok = ($tok -replace '[^\x21-\x7E]', '').Trim()
if ($tok.Length -lt 10) { throw "Jeton vide ou tronqué ($($tok.Length) caractères lus) — recommencez le collage." }
$headers = @{ Authorization = "Bearer $tok" }

$apps = @(Invoke-RestMethod -Uri "$BaseUrl/applications" -Headers $headers)
if ($apps.Count -eq 0) { throw "Aucune application visible avec ce jeton." }
if ($apps.Count -eq 1) {
    $app = $apps[0]
} else {
    $apps | ForEach-Object { "{0}  {1}" -f $_.uuid, $_.name }
    $uuid = Read-Host "UUID de l'application cible"
    $app = $apps | Where-Object uuid -eq $uuid
}
"Cible : $($app.name) [$($app.uuid)]"

$lignes = Get-Content $EnvFile | Where-Object { $_ -match '^[A-Z0-9_]+=' }
foreach ($l in $lignes) {
    $k, $v = $l -split '=', 2
    if ($v -match 'REPRENDRE-CELUI-DE-COOLIFY') { "SKIP  $k (valeur Coolify conservée)"; continue }
    $body = @{ key = $k; value = $v; is_preview = $false } | ConvertTo-Json
    try {
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/applications/$($app.uuid)/envs" `
            -Headers $headers -ContentType 'application/json' -Body $body | Out-Null
        "CREE  $k"
    } catch {
        Invoke-RestMethod -Method Patch -Uri "$BaseUrl/applications/$($app.uuid)/envs" `
            -Headers $headers -ContentType 'application/json' -Body $body | Out-Null
        "MAJ   $k"
    }
}

$dep = Invoke-RestMethod -Uri "$BaseUrl/deploy?uuid=$($app.uuid)" -Headers $headers
"Déploiement déclenché : $($dep.deployments.message -join '; ')"
