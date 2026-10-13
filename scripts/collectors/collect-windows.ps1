[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory,

    [Parameter(Mandatory = $true)]
    [string[]] $SourceRoot,

    [string] $Environment = "production"
)

$ErrorActionPreference = "Stop"
$bundle = [System.IO.Path]::GetFullPath($OutputDirectory)
$resolvedRoots = @()
foreach ($rootInput in $SourceRoot) {
    $root = (Resolve-Path -LiteralPath $rootInput).Path.TrimEnd('\')
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "Source root is not a directory: $rootInput"
    }
    if (($bundle -eq $root) -or
        $bundle.StartsWith($root + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "OutputDirectory must not be inside a SourceRoot: $root"
    }
    $resolvedRoots += $root
}

$supportedExtensions = @(
    ".ps1", ".psm1", ".psd1", ".ps1xml", ".bat", ".cmd",
    ".py", ".pyw", ".pyi", ".sql", ".ddl", ".dml", ".psql", ".db2",
    ".json", ".yaml", ".yml", ".xml", ".ini", ".cfg", ".conf",
    ".config", ".properties", ".toml"
)
$skipDirectories = @(
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules",
    "__pycache__", ".tox", "dist", "build", "bin", "obj"
)

New-Item -ItemType Directory -Force -Path `
    (Join-Path $bundle "windows\tasks"), `
    (Join-Path $bundle "source") | Out-Null

$fqdn = $env:COMPUTERNAME
try {
    $fqdn = [System.Net.Dns]::GetHostEntry($env:COMPUTERNAME).HostName
} catch {
    Write-Warning "Could not resolve the FQDN; using the computer name."
}

[ordered]@{
    hostname    = $env:COMPUTERNAME
    fqdn        = $fqdn
    os          = "windows"
    environment = $Environment
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $bundle "server.json")

$taskIndex = 0
Get-ScheduledTask | ForEach-Object {
    $task = $_
    $taskIndex++
    $safeName = ($task.TaskPath + $task.TaskName) -replace '[\\/:*?"<>|]', '_'
    $destination = Join-Path $bundle ("windows\tasks\{0:D5}-{1}.xml" -f $taskIndex, $safeName)
    try {
        Export-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath |
            Set-Content -Encoding UTF8 $destination
    } catch {
        Write-Warning "Could not export task '$($task.TaskPath)$($task.TaskName)': $_"
    }
}

$rootIndex = 0
foreach ($root in $resolvedRoots) {
    $rootIndex++
    $safeRootName = ($root -replace '[:\\/]', '_').Trim('_')
    $rootDestination = Join-Path $bundle ("source\{0:D2}-{1}" -f $rootIndex, $safeRootName)
    Get-ChildItem -LiteralPath $root -File -Recurse -Force -ErrorAction SilentlyContinue |
        ForEach-Object {
            $file = $_
            $relative = $file.FullName.Substring($root.Length).TrimStart('\')
            if (($file.Extension.ToLowerInvariant() -notin $supportedExtensions) -and
                ($file.Name -notlike ".env*")) {
                return
            }
            if ($file.Length -gt 4000000) {
                Write-Warning "Skipping file larger than Atlas's 4 MB scan limit: $($file.FullName)"
                return
            }
            if (($file.FullName -split '[\\/]') | Where-Object { $_ -in $skipDirectories }) {
                return
            }
            $target = Join-Path $rootDestination $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $file.FullName -Destination $target -Force
        }
}

Write-Host "Bundle created at $bundle"
Write-Host "Review the collection warnings, then copy the bundle to the Atlas host."
Write-Warning "The bundle may contain credentials or other sensitive source data. Store and transfer it securely."
