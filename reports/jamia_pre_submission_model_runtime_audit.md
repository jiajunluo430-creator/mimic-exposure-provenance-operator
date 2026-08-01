# JAMIA pre-submission model runtime audit

## 31 July 2026: bounded runner timeout

The first invocation of `27_fit_pre_submission_sensitivity_models.R` was
terminated by the command runner's predeclared 120-second wall-time limit.
The persistent log showed that all 1,000 A1 paired subject-level bootstrap
replicates had completed successfully in 82 seconds, after the static and
time-varying point-estimate models had completed. The process was stopped
before the A2 bootstrap stages and before aggregate bootstrap outputs were
written.

This is an orchestration/runtime failure, not a statistical failure. The
analysis contract, medication dictionary, cohorts, windows, covariates, and
estimands were unchanged. The implementation was revised only to write and
reuse a validated 1,000-row checkpoint after each prespecified bootstrap
comparison. The rerun uses a bounded 15-minute runner limit with log-based
progress checks.
