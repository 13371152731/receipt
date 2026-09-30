param([Parameter(Mandatory=$true)][string]$InputDocx,[Parameter(Mandatory=$true)][string]$OutputPdf)
$ErrorActionPreference='Stop'
$reportDocPath=(Resolve-Path -LiteralPath $InputDocx).Path
$reportPdfPath=[IO.Path]::GetFullPath($OutputPdf)
$reportWord=$null
$reportDocument=$null
try {
    $reportWord=New-Object -ComObject Word.Application
    $reportWord.Visible=$false
    $reportWord.DisplayAlerts=0
    $reportDocument=$reportWord.Documents.Open($reportDocPath,$false,$true)
    $reportDocument.Repaginate()
    $reportDocument.ExportAsFixedFormat($reportPdfPath,17)
    Write-Output ('Pages: '+$reportDocument.ComputeStatistics(2))
    Write-Output $reportPdfPath
}
finally {
    if ($null -ne $reportDocument) { $reportDocument.Close(0); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($reportDocument) }
    if ($null -ne $reportWord) { $reportWord.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($reportWord) }
}
