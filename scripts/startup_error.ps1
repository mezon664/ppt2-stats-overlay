# start.bat found no Python to run the app with: says so (the full zip
# brings one in runtime\; without it, Python from python.org is needed).
Add-Type -AssemblyName System.Windows.Forms
$text = "PPTetrics を起動できませんでした。`n`n" +
        "アプリを動かす Python が見つかりません（アプリのフォルダに runtime フォルダがありません）。`n" +
        "runtime フォルダ入りの完全版の zip を、新しいフォルダに入れ直してください。`n`n" +
        "No Python to run the app with (no runtime folder): reinstall the full zip."
[System.Windows.Forms.MessageBox]::Show($text, "PPTetrics", "OK", "Error") | Out-Null
