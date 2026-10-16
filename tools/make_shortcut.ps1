# Puts a Lemmatrix shortcut, with its icon, on the desktop and in the Start menu.
# Called by "Make desktop shortcut.bat".
$root = Split-Path -Parent $PSScriptRoot
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    $s = $shell.CreateShortcut((Join-Path $folder 'Lemmatrix.lnk'))
    $s.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
    $s.Arguments = '"' + (Join-Path $root 'tools\launch.pyw') + '"'
    $s.WorkingDirectory = $root
    $s.IconLocation = Join-Path $root 'lemmatrix\resources\lemmatrix.ico'
    $s.Description = 'Lemmatrix: phonology fieldwork database'
    $s.Save()
}
