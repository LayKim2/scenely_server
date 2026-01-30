# Replace "pick 0a83cad" with "edit 0a83cad" in the rebase todo file
$path = $args[0]
(Get-Content $path -Raw) -replace 'pick 0a83cad ', 'edit 0a83cad ' | Set-Content $path -NoNewline
