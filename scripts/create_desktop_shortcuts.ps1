$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$desktopPath = [Environment]::GetFolderPath('DesktopDirectory')
$shortcutShell = New-Object -ComObject WScript.Shell
foreach ($entry in @(
    @{ Name = 'Newsroom Engine'; Target = 'Start Local.cmd'; Description = 'Start Newsroom in local review mode' },
    @{ Name = 'Stop Newsroom'; Target = 'Stop Local.cmd'; Description = 'Stop the local Newsroom app safely' }
)) {
    $shortcutPath = Join-Path $desktopPath ($entry.Name + '.lnk')
    $targetPath = Join-Path $projectRoot $entry.Target
    $shortcut = $shortcutShell.CreateShortcut($shortcutPath)
    if ((Test-Path -LiteralPath $shortcutPath) -and $shortcut.TargetPath -ne $targetPath) {
        throw ('An unrelated shortcut already exists: ' + $entry.Name)
    }
    $shortcut.TargetPath = $targetPath
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = $entry.Description
    $shortcut.IconLocation = Join-Path $projectRoot 'frontend\public\favicon.ico'
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Output ('Created desktop shortcut: ' + $entry.Name)
}
