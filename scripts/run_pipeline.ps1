param(
    [string]$PythonExe = $env:PYTHON_EXE,
    [string]$RscriptExe = $env:RSCRIPT_EXE
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($PythonExe)) { $PythonExe = "python" }
if ([string]::IsNullOrWhiteSpace($RscriptExe)) { $RscriptExe = "Rscript" }
if ([string]::IsNullOrWhiteSpace($env:MIMIC_IV_ROOT)) { throw "Set MIMIC_IV_ROOT" }
if ([string]::IsNullOrWhiteSpace($env:EICU_ZIP)) { throw "Set EICU_ZIP" }

function Invoke-Checked {
    param([string]$Executable, [string]$Script, [string[]]$Arguments = @())
    & $Executable $Script @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Failed: $Script" }
}

Push-Location $ProjectRoot
try {
    Invoke-Checked $PythonExe "$PSScriptRoot\01_full_interface_audit.py"
    $stage02 = "$PSScriptRoot\02_build_primary_estimands_v2.py"
    Invoke-Checked $PythonExe $stage02 @("--pilot-only")
    Invoke-Checked $PythonExe $stage02 @("--through-prescriptions")
    Invoke-Checked $PythonExe $stage02 @("--pilot-downstream")
    Invoke-Checked $PythonExe $stage02 @("--full")
    Invoke-Checked $PythonExe "$PSScriptRoot\03_build_severity_notgiven.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\04_build_published_association_cohorts.py"
    Invoke-Checked $RscriptExe "$PSScriptRoot\05_fit_prespecified_models.R"
    Invoke-Checked $PythonExe "$PSScriptRoot\06_finalize_qdp.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\07_validate_package.py"

    Invoke-Checked $PythonExe "$PSScriptRoot\13_build_jamia_observability_extension.py"
    Invoke-Checked $RscriptExe "$PSScriptRoot\14_fit_jamia_observability_models.R"
    Invoke-Checked $PythonExe "$PSScriptRoot\15_validate_jamia_analytics.py"

    Invoke-Checked $PythonExe "$PSScriptRoot\26_build_pre_submission_diagnostics.py"
    Invoke-Checked $RscriptExe "$PSScriptRoot\27_fit_pre_submission_sensitivity_models.R"
    Invoke-Checked $PythonExe "$PSScriptRoot\28_build_prereview_upgrade_analytics.py"
    Invoke-Checked $RscriptExe "$PSScriptRoot\29_fit_prereview_upgrade_models.R"
    Invoke-Checked $PythonExe "$PSScriptRoot\30_build_rxnav_ndc_validation.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\31_retrieve_published_operator_landscape.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\32_finalize_published_operator_landscape.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\33_validate_prereview_upgrade.py"

    Invoke-Checked $PythonExe "$PSScriptRoot\34_build_residual_provenance_diagnostics.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\35_build_residual_prescription_eligibility_audit.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\36_validate_residual_provenance.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\37_audit_published_operator_evidence_scope.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\38_finalize_published_operator_evidence_scope.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\42_build_poe_temporal_mechanism_audit.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\43_build_cross_poe_pairing_audit.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\44_prepare_independent_recoding_sample.py"
    Invoke-Checked $PythonExe "$PSScriptRoot\19_make_jamia_figures.py"
}
finally { Pop-Location }
