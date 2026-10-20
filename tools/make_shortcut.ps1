# Puts a Lemmatrix shortcut, with its icon, on the desktop and in the Start menu.
# Called by "Make desktop shortcut.bat".
$root = Split-Path -Parent $PSScriptRoot
$shell = New-Object -ComObject WScript.Shell
# Windows remembers a shortcut's icon by its file's path, so a changed icon kept its old picture.
# The icon is copied under a name made from its contents: a new icon is a new path, and is shown.
$ico = Join-Path $root 'lemmatrix\resources\lemmatrix.ico'
$hash = (Get-FileHash $ico -Algorithm SHA256).Hash.Substring(0, 8)
$iconDir = Join-Path $env:LOCALAPPDATA 'Lemmatrix'
New-Item -ItemType Directory -Force -Path $iconDir | Out-Null
Get-ChildItem $iconDir -Filter 'lemmatrix-*.ico' | Remove-Item -Force -ErrorAction SilentlyContinue
$iconCopy = Join-Path $iconDir "lemmatrix-$hash.ico"
Copy-Item $ico $iconCopy -Force
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    $lnk = Join-Path $folder 'Lemmatrix.lnk'
    Remove-Item $lnk -Force -ErrorAction SilentlyContinue    # a fresh shortcut, not the old one updated
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
    $s.Arguments = '"' + (Join-Path $root 'tools\launch.pyw') + '"'
    $s.WorkingDirectory = $root
    $s.IconLocation = "$iconCopy,0"
    $s.Description = 'Lemmatrix: phonology fieldwork database'
    $s.Save()
}
