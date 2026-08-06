$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$package = Join-Path $root 'manuscript\jbi\JBI_first_submission_package_2026-08-05'
$qcRoot = Join-Path $root 'manuscript\jbi\rendered_qc_v2_redesigned_figures'
$projectRoot = Split-Path -Parent (Split-Path -Parent $root)
$shortExportRoot = Join-Path $projectRoot '_jbi_qc_tmp_v2'
$pdftoppm = 'C:\Users\ljjws\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe'

if (-not (Test-Path -LiteralPath $package)) {
    throw "Prior audited package not found: $package"
}
if (-not (Test-Path -LiteralPath $pdftoppm)) {
    throw "pdftoppm wrapper not found: $pdftoppm"
}

New-Item -ItemType Directory -Force -Path $qcRoot | Out-Null
New-Item -ItemType Directory -Force -Path $shortExportRoot | Out-Null

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.AutomationSecurity = 3
$word.Options.SaveNormalPrompt = $false
$word.Options.UpdateLinksAtOpen = $false

try {
    foreach ($file in Get-ChildItem -LiteralPath $package -Filter '*.docx' -Recurse | Sort-Object Name) {
        $outDir = Join-Path $qcRoot $file.BaseName
        New-Item -ItemType Directory -Force -Path $outDir | Out-Null
        Get-ChildItem -LiteralPath $outDir -Filter 'page-*.png' -ErrorAction SilentlyContinue |
            Remove-Item -Force
        $pdfPath = Join-Path $outDir ($file.BaseName + '.pdf')
        $shortPdfPath = Join-Path $shortExportRoot ($file.BaseName + '.pdf')
        Remove-Item -LiteralPath $pdfPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $shortPdfPath -Force -ErrorAction SilentlyContinue
        Write-Output ('OPEN|' + $file.Name)
        $doc = $word.Documents.Open($file.FullName, $false, $true)
        try {
            $expectedPages = $doc.ComputeStatistics(2)
            Write-Output ('EXPORT|' + $file.Name + '|expected_pages=' + $expectedPages)
            $doc.SaveAs2($shortPdfPath, 17)
        }
        finally {
            $doc.Close($false)
            [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($doc) | Out-Null
        }
        Copy-Item -LiteralPath $shortPdfPath -Destination $pdfPath -Force
        Remove-Item -LiteralPath $shortPdfPath -Force
        & $pdftoppm -png -r 120 $pdfPath (Join-Path $outDir 'page')
        if ($LASTEXITCODE -ne 0) {
            throw "pdftoppm failed for $pdfPath"
        }
        $pages = (Get-ChildItem -LiteralPath $outDir -Filter 'page-*.png').Count
        if ($pages -ne $expectedPages) {
            throw "Rendered page count mismatch for $($file.Name): expected $expectedPages, got $pages"
        }
        Write-Output ('PASS|' + $file.Name + '|pages=' + $pages)
    }
}
finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) | Out-Null
    if ((Test-Path -LiteralPath $shortExportRoot) -and
        -not (Get-ChildItem -LiteralPath $shortExportRoot -Force -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $shortExportRoot -Force
    }
}
