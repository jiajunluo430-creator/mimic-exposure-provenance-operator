suppressPackageStartupMessages({
  library(data.table)
  library(jsonlite)
  library(lmtest)
  library(sandwich)
  library(survival)
})

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(script_arg) != 1L) {
  stop("Cannot resolve this script path.")
}
script_path <- normalizePath(
  sub("^--file=", "", script_arg),
  winslash = "\\",
  mustWork = TRUE
)
project <- dirname(dirname(script_path))
cache_dir <- file.path(project, "cache")
tables_dir <- file.path(project, "outputs", "tables")
logs_dir <- file.path(project, "outputs", "logs")
reports_dir <- file.path(project, "reports")
environment_dir <- file.path(project, "environment")
manifests_dir <- file.path(project, "outputs", "manifests")
dir.create(tables_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(logs_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(reports_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(environment_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(manifests_dir, recursive = TRUE, showWarnings = FALSE)

log_path <- file.path(logs_dir, "05_fit_prespecified_models.log")
log_message <- function(...) {
  line <- paste(
    format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
    paste0(..., collapse = ""),
    sep = "\t"
  )
  cat(line, "\n")
  cat(line, "\n", file = log_path, append = TRUE)
}

started <- Sys.time()
frozen_manifest <- file.path(
  project, "contracts", "frozen_contract_sha256_2026-07-29.txt"
)
if (!file.exists(frozen_manifest) || length(readLines(frozen_manifest)) != 5L) {
  stop("Frozen contract manifest is absent or incomplete.")
}
semantic_manifest <- file.path(
  project, "contracts", "semantic_audit_addendum_sha256_2026-07-29.txt"
)
if (!file.exists(semantic_manifest) ||
    length(readLines(semantic_manifest)) != 2L) {
  stop("Pre-model semantic-audit addendum manifest is absent or incomplete.")
}

required_inputs <- c(
  file.path(cache_dir, "not_given_model_aggregated.csv"),
  file.path(
    cache_dir, "not_given_audit_semantic_sensitivity_aggregated.csv"
  ),
  file.path(cache_dir, "anchor_a1_cohort.csv"),
  file.path(cache_dir, "anchor_a2_cohort.csv")
)
if (!all(file.exists(required_inputs))) {
  stop(
    "Run Python extraction scripts 01-04 first. Missing: ",
    paste(required_inputs[!file.exists(required_inputs)], collapse = ", ")
  )
}

weighted_sd <- function(x, w) {
  ok <- is.finite(x) & is.finite(w) & w > 0
  x <- x[ok]
  w <- w[ok]
  if (length(x) < 2L || sum(w) <= 1) {
    return(NA_real_)
  }
  mu <- sum(w * x) / sum(w)
  sqrt(sum(w * (x - mu)^2) / (sum(w) - 1))
}

safe_glm <- function(formula, data, family = binomial()) {
  warnings <- character()
  fit <- tryCatch(
    withCallingHandlers(
      glm(formula, data = data, family = family),
      warning = function(w) {
        warnings <<- c(warnings, conditionMessage(w))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) e
  )
  list(
    fit = if (inherits(fit, "error")) NULL else fit,
    error = if (inherits(fit, "error")) conditionMessage(fit) else NA_character_,
    warnings = paste(unique(warnings), collapse = " || ")
  )
}

safe_cox <- function(formula, data) {
  warnings <- character()
  fit <- tryCatch(
    withCallingHandlers(
      coxph(formula, data = data, ties = "efron", x = TRUE),
      warning = function(w) {
        warnings <<- c(warnings, conditionMessage(w))
        invokeRestart("muffleWarning")
      }
    ),
    error = function(e) e
  )
  list(
    fit = if (inherits(fit, "error")) NULL else fit,
    error = if (inherits(fit, "error")) conditionMessage(fit) else NA_character_,
    warnings = paste(unique(warnings), collapse = " || ")
  )
}

failed_effect <- function(
  anchor_id, model_variant, exposure_definition, effect_measure,
  n, outcomes, exposed, error, warnings
) {
  data.table(
    anchor_id = anchor_id,
    model_variant = model_variant,
    exposure_definition = exposure_definition,
    effect_measure = effect_measure,
    n = n,
    outcomes_n = outcomes,
    exposed_n = exposed,
    beta = NA_real_,
    standard_error = NA_real_,
    effect = NA_real_,
    ci_low = NA_real_,
    ci_high = NA_real_,
    p_value = NA_real_,
    converged = FALSE,
    model_error = error,
    model_warnings = warnings
  )
}

extract_glm_effect <- function(
  fitted, anchor_id, model_variant, exposure_definition, data
) {
  n <- nrow(data)
  outcomes <- sum(data$outcome)
  exposed <- sum(data$exposure)
  if (is.null(fitted$fit)) {
    return(failed_effect(
      anchor_id, model_variant, exposure_definition, "OR",
      n, outcomes, exposed, fitted$error, fitted$warnings
    ))
  }
  coefficients <- summary(fitted$fit)$coefficients
  if (!"exposure" %in% rownames(coefficients)) {
    return(failed_effect(
      anchor_id, model_variant, exposure_definition, "OR",
      n, outcomes, exposed, "Exposure coefficient absent", fitted$warnings
    ))
  }
  beta <- coefficients["exposure", "Estimate"]
  se <- coefficients["exposure", "Std. Error"]
  data.table(
    anchor_id = anchor_id,
    model_variant = model_variant,
    exposure_definition = exposure_definition,
    effect_measure = "OR",
    n = n,
    outcomes_n = outcomes,
    exposed_n = exposed,
    beta = beta,
    standard_error = se,
    effect = exp(beta),
    ci_low = exp(beta - qnorm(0.975) * se),
    ci_high = exp(beta + qnorm(0.975) * se),
    p_value = coefficients["exposure", "Pr(>|z|)"],
    converged = isTRUE(fitted$fit$converged),
    model_error = NA_character_,
    model_warnings = fitted$warnings
  )
}

extract_cox_effect <- function(
  fitted, anchor_id, model_variant, exposure_definition, data
) {
  n <- nrow(data)
  outcomes <- sum(data$outcome)
  exposed <- sum(data$exposure)
  if (is.null(fitted$fit)) {
    return(failed_effect(
      anchor_id, model_variant, exposure_definition, "HR",
      n, outcomes, exposed, fitted$error, fitted$warnings
    ))
  }
  coefficients <- summary(fitted$fit)$coefficients
  if (!"exposure" %in% rownames(coefficients)) {
    return(failed_effect(
      anchor_id, model_variant, exposure_definition, "HR",
      n, outcomes, exposed, "Exposure coefficient absent", fitted$warnings
    ))
  }
  beta <- coefficients["exposure", "coef"]
  se <- coefficients["exposure", "se(coef)"]
  data.table(
    anchor_id = anchor_id,
    model_variant = model_variant,
    exposure_definition = exposure_definition,
    effect_measure = "HR",
    n = n,
    outcomes_n = outcomes,
    exposed_n = exposed,
    beta = beta,
    standard_error = se,
    effect = exp(beta),
    ci_low = exp(beta - qnorm(0.975) * se),
    ci_high = exp(beta + qnorm(0.975) * se),
    p_value = coefficients["exposure", "Pr(>|z|)"],
    converged = TRUE,
    model_error = NA_character_,
    model_warnings = fitted$warnings
  )
}

log_message("START locked not-given clustered logistic model")
not_given <- fread(required_inputs[1], na.strings = c("", "NA"))
not_given[, gender := relevel(factor(gender), ref = "F")]
not_given[, shift := relevel(factor(shift), ref = "day_0700_1859")]
not_given[, drug_class := factor(drug_class)]
not_given[, first_careunit := factor(first_careunit)]
not_given[, anchor_era := factor(anchor_era)]
not_given[, total_n := not_given_n + given_n]
oasis_mean <- weighted.mean(
  not_given$oasis, not_given$total_n, na.rm = TRUE
)
oasis_sd <- weighted_sd(not_given$oasis, not_given$total_n)
if (!is.finite(oasis_sd) || oasis_sd <= 0) {
  stop("Cannot calculate the locked event-weighted OASIS SD.")
}
not_given[, oasis_z := (oasis - oasis_mean) / oasis_sd]

not_given_formula <- cbind(not_given_n, given_n) ~
  oasis_z + oasis_missing_components_n + shift +
  invasive_ventilation_active + vasopressor_active + rrt_active +
  drug_class + age_at_icu + gender + emergency_admission +
  first_careunit + anchor_era
not_given_fit <- safe_glm(not_given_formula, not_given)
if (is.null(not_given_fit$fit)) {
  stop("Locked not-given model failed: ", not_given_fit$error)
}
not_given_vcov <- vcovCL(
  not_given_fit$fit,
  cluster = not_given$stay_id,
  type = "HC0"
)
not_given_test <- coeftest(not_given_fit$fit, vcov. = not_given_vcov)
not_given_coefficients <- data.table(
  term = rownames(not_given_test),
  beta = not_given_test[, "Estimate"],
  cluster_robust_se = not_given_test[, "Std. Error"],
  z_value = not_given_test[, "z value"],
  p_value = not_given_test[, "Pr(>|z|)"]
)
not_given_coefficients[
  ,
  `:=`(
    adjusted_or = exp(beta),
    ci_low = exp(beta - qnorm(0.975) * cluster_robust_se),
    ci_high = exp(beta + qnorm(0.975) * cluster_robust_se)
  )
]
locked_terms <- c(
  "oasis_z",
  "shiftnight_1900_0659",
  "invasive_ventilation_active",
  "vasopressor_active",
  "rrt_active"
)
not_given_primary <- not_given_coefficients[term %in% locked_terms]
not_given_primary[, bh_q_value := p.adjust(p_value, method = "BH")]
not_given_primary[
  ,
  locked_correlate := fifelse(
    term == "oasis_z", "OASIS per SD",
    fifelse(
      term == "shiftnight_1900_0659", "Night versus day shift",
      fifelse(
        term == "invasive_ventilation_active",
        "Active invasive ventilation",
        fifelse(
          term == "vasopressor_active",
          "Active vasopressor",
          "Active RRT"
        )
      )
    )
  )
]
setcolorder(
  not_given_primary,
  c(
    "locked_correlate", "term", "adjusted_or", "ci_low", "ci_high",
    "beta", "cluster_robust_se", "z_value", "p_value", "bh_q_value"
  )
)
fwrite(
  not_given_coefficients,
  file.path(tables_dir, "not_given_clustered_logistic_all_coefficients.csv")
)
fwrite(
  not_given_primary,
  file.path(tables_dir, "not_given_prespecified_correlates.csv")
)
oasis_row <- not_given_primary[term == "oasis_z"]
meaningful_oasis <- (
  nrow(oasis_row) == 1L &&
    is.finite(oasis_row$adjusted_or) &&
    (oasis_row$adjusted_or >= 1.15 || oasis_row$adjusted_or <= 0.87) &&
    (oasis_row$ci_low > 1 || oasis_row$ci_high < 1)
)
log_message(
  "DONE locked not-given model events=", sum(not_given$total_n),
  " stays=", uniqueN(not_given$stay_id),
  " OASIS_OR_per_SD=", format(oasis_row$adjusted_or, digits = 5),
  " meaningful=", meaningful_oasis
)

log_message("START pre-model audit-semantic not-given sensitivity")
not_given_sensitivity <- fread(
  required_inputs[2], na.strings = c("", "NA")
)
not_given_sensitivity[
  ,
  gender := relevel(factor(gender), ref = "F")
]
not_given_sensitivity[
  ,
  shift := relevel(factor(shift), ref = "day_0700_1859")
]
not_given_sensitivity[, drug_class := factor(drug_class)]
not_given_sensitivity[, first_careunit := factor(first_careunit)]
not_given_sensitivity[, anchor_era := factor(anchor_era)]
not_given_sensitivity[, total_n := not_given_n + given_n]
sensitivity_oasis_mean <- weighted.mean(
  not_given_sensitivity$oasis,
  not_given_sensitivity$total_n,
  na.rm = TRUE
)
sensitivity_oasis_sd <- weighted_sd(
  not_given_sensitivity$oasis,
  not_given_sensitivity$total_n
)
if (!is.finite(sensitivity_oasis_sd) || sensitivity_oasis_sd <= 0) {
  stop("Cannot calculate audit-sensitivity event-weighted OASIS SD.")
}
not_given_sensitivity[
  ,
  oasis_z := (oasis - sensitivity_oasis_mean) / sensitivity_oasis_sd
]
sensitivity_fit <- safe_glm(
  not_given_formula, not_given_sensitivity
)
if (is.null(sensitivity_fit$fit)) {
  stop(
    "Audit-semantic not-given sensitivity failed: ",
    sensitivity_fit$error
  )
}
sensitivity_vcov <- vcovCL(
  sensitivity_fit$fit,
  cluster = not_given_sensitivity$stay_id,
  type = "HC0"
)
sensitivity_test <- coeftest(
  sensitivity_fit$fit, vcov. = sensitivity_vcov
)
sensitivity_coefficients <- data.table(
  term = rownames(sensitivity_test),
  beta = sensitivity_test[, "Estimate"],
  cluster_robust_se = sensitivity_test[, "Std. Error"],
  z_value = sensitivity_test[, "z value"],
  p_value = sensitivity_test[, "Pr(>|z|)"]
)
sensitivity_coefficients[
  ,
  `:=`(
    adjusted_or = exp(beta),
    ci_low = exp(beta - qnorm(0.975) * cluster_robust_se),
    ci_high = exp(beta + qnorm(0.975) * cluster_robust_se)
  )
]
sensitivity_primary <- sensitivity_coefficients[term %in% locked_terms]
sensitivity_primary[, bh_q_value := p.adjust(p_value, method = "BH")]
sensitivity_primary[
  ,
  locked_correlate := fifelse(
    term == "oasis_z", "OASIS per SD",
    fifelse(
      term == "shiftnight_1900_0659", "Night versus day shift",
      fifelse(
        term == "invasive_ventilation_active",
        "Active invasive ventilation",
        fifelse(
          term == "vasopressor_active",
          "Active vasopressor",
          "Active RRT"
        )
      )
    )
  )
]
setcolorder(
  sensitivity_primary,
  c(
    "locked_correlate", "term", "adjusted_or", "ci_low", "ci_high",
    "beta", "cluster_robust_se", "z_value", "p_value", "bh_q_value"
  )
)
fwrite(
  sensitivity_coefficients,
  file.path(
    tables_dir,
    "not_given_audit_semantic_sensitivity_all_coefficients.csv"
  )
)
fwrite(
  sensitivity_primary,
  file.path(
    tables_dir,
    "not_given_audit_semantic_sensitivity_correlates.csv"
  )
)
log_message(
  "DONE audit-semantic sensitivity events=",
  sum(not_given_sensitivity$total_n),
  " stays=", uniqueN(not_given_sensitivity$stay_id),
  " OASIS_OR_per_SD=",
  format(
    sensitivity_primary[term == "oasis_z", adjusted_or],
    digits = 5
  )
)

prepare_common <- function(d) {
  d[, gender := relevel(factor(gender), ref = "F")]
  d[, anchor_era := factor(anchor_era)]
  d[, oasis_z := as.numeric(scale(oasis))]
  d
}

fit_a1_pair <- function(data, enriched = FALSE) {
  variant <- if (enriched) "enriched" else "published_style_minimal"
  rows <- list()
  for (exposure_name in c("order_exposure", "administration_exposure")) {
    d <- copy(data)
    d[, exposure := get(exposure_name)]
    if (enriched) {
      formula <- outcome ~ exposure + age + gender +
        emergency_admission + oasis_z +
        oasis_missing_components_n + first_day_mechvent +
        first_day_vasopressor + first_day_rrt
    } else {
      formula <- outcome ~ exposure + age + gender +
        emergency_admission
    }
    needed <- all.vars(formula)
    d <- d[complete.cases(d[, ..needed])]
    fitted <- safe_glm(formula, d)
    rows[[exposure_name]] <- extract_glm_effect(
      fitted, "A1", variant,
      sub("_exposure$", "", exposure_name), d
    )
  }
  rbindlist(rows, use.names = TRUE, fill = TRUE)
}

fit_a2_pair <- function(data, enriched = FALSE, landmark = FALSE) {
  if (landmark) {
    variant <- if (enriched) "landmark_48h_enriched" else
      "landmark_48h_minimal"
  } else {
    variant <- if (enriched) "enriched" else "published_style_minimal"
  }
  rows <- list()
  for (exposure_name in c("order_exposure", "administration_exposure")) {
    d <- copy(data)
    if (landmark) {
      d <- d[landmark_48h_eligible == 1 & followup_days > 2]
      d[, analysis_time := followup_days - 2]
    } else {
      d[, analysis_time := followup_days]
    }
    d[, exposure := get(exposure_name)]
    if (enriched) {
      formula <- Surv(analysis_time, outcome) ~
        exposure + age + gender + emergency_admission + anchor_era +
        oasis_z + oasis_missing_components_n + first_day_mechvent +
        first_day_vasopressor + first_day_rrt
    } else {
      formula <- Surv(analysis_time, outcome) ~
        exposure + age + gender + emergency_admission + anchor_era
    }
    needed <- unique(c(
      "analysis_time", "outcome", "exposure",
      setdiff(all.vars(formula), c("Surv"))
    ))
    d <- d[complete.cases(d[, ..needed])]
    fitted <- safe_cox(formula, d)
    rows[[exposure_name]] <- extract_cox_effect(
      fitted, "A2", variant,
      sub("_exposure$", "", exposure_name), d
    )
  }
  rbindlist(rows, use.names = TRUE, fill = TRUE)
}

log_message("START two frozen published-association model pairs")
a1 <- prepare_common(fread(required_inputs[3], na.strings = c("", "NA")))
a2 <- prepare_common(fread(required_inputs[4], na.strings = c("", "NA")))
association_effects <- rbindlist(
  list(
    fit_a1_pair(a1, enriched = FALSE),
    fit_a1_pair(a1, enriched = TRUE),
    fit_a2_pair(a2, enriched = FALSE, landmark = FALSE),
    fit_a2_pair(a2, enriched = TRUE, landmark = FALSE),
    fit_a2_pair(a2, enriched = FALSE, landmark = TRUE),
    fit_a2_pair(a2, enriched = TRUE, landmark = TRUE)
  ),
  use.names = TRUE,
  fill = TRUE
)
fwrite(
  association_effects,
  file.path(tables_dir, "published_association_model_effects.csv")
)

same_cohort_check <- association_effects[
  ,
  .(
    definitions_n = uniqueN(exposure_definition),
    n_min = min(n),
    n_max = max(n),
    outcomes_min = min(outcomes_n),
    outcomes_max = max(outcomes_n),
    identical_n_and_outcomes = (
      uniqueN(n) == 1L && uniqueN(outcomes_n) == 1L
    )
  ),
  by = .(anchor_id, model_variant)
]
fwrite(
  same_cohort_check,
  file.path(tables_dir, "published_association_same_cohort_check.csv")
)

effect_change <- dcast(
  association_effects,
  anchor_id + model_variant + effect_measure ~ exposure_definition,
  value.var = c("beta", "effect", "ci_low", "ci_high", "n", "outcomes_n")
)
effect_change[
  ,
  `:=`(
    log_effect_change_admin_minus_order = beta_administration - beta_order,
    absolute_log_effect_change = abs(beta_administration - beta_order),
    relative_absolute_log_effect_change_pct = fifelse(
      is.finite(beta_order) & abs(beta_order) > 1e-12,
      100 * abs(beta_administration - beta_order) / abs(beta_order),
      NA_real_
    ),
    ratio_of_effects_admin_to_order =
      exp(beta_administration - beta_order),
    direction_reversal = (
      is.finite(beta_order) & is.finite(beta_administration) &
        sign(beta_order) != 0 & sign(beta_administration) != 0 &
        sign(beta_order) != sign(beta_administration)
    ),
    material_absolute_log_change = (
      abs(beta_administration - beta_order) >= log(1.25)
    ),
    material_relative_log_change = (
      is.finite(beta_order) & abs(beta_order) > 1e-12 &
        100 * abs(beta_administration - beta_order) / abs(beta_order) >= 25
    )
  )
]
effect_change[
  ,
  material_effect_change := (
    direction_reversal |
      material_absolute_log_change |
      material_relative_log_change
  )
]
fwrite(
  effect_change,
  file.path(tables_dir, "published_association_effect_change.csv")
)
log_message(
  "DONE published-association model pairs rows=", nrow(association_effects),
  " primary_material_anchors=",
  effect_change[
    model_variant == "published_style_minimal" &
      material_effect_change == TRUE,
    uniqueN(anchor_id)
  ]
)

format_table <- function(x) {
  paste(capture.output(print(as.data.frame(x), row.names = FALSE)), collapse = "\n")
}

primary_effects <- association_effects[
  model_variant == "published_style_minimal",
  .(
    anchor_id, exposure_definition, effect_measure, n, outcomes_n,
    exposed_n, effect, ci_low, ci_high, beta, p_value,
    converged, model_error, model_warnings
  )
]
primary_change <- effect_change[
  model_variant == "published_style_minimal",
  .(
    anchor_id, effect_measure,
    effect_order, ci_low_order, ci_high_order,
    effect_administration, ci_low_administration,
    ci_high_administration,
    log_effect_change_admin_minus_order,
    relative_absolute_log_effect_change_pct,
    ratio_of_effects_admin_to_order,
    direction_reversal, material_absolute_log_change,
    material_relative_log_change, material_effect_change
  )
]

report_lines <- c(
  "# 05 — Prespecified models and exposure-definition effect change",
  "",
  "All models were specified in the frozen contract. No drug class, anchor,",
  "covariate, or analysis window was selected by statistical significance.",
  "Estimates quantify exposure-definition sensitivity and are not interpreted",
  "as new causal efficacy or safety conclusions.",
  "",
  "## Held/not-given correlates",
  "",
  paste0(
    "The grouped-binomial implementation is algebraically equivalent to the ",
    "locked event-level logistic score for identical covariate patterns. ",
    "HC0 standard errors are clustered by ICU stay. OASIS was standardized ",
    "using the event-weighted SD (", signif(oasis_sd, 5), ")."
  ),
  "",
  "```text",
  format_table(not_given_primary),
  "```",
  "",
  paste0(
    "- Meaningful locked OASIS association: ", meaningful_oasis,
    " (OR per SD outside 0.87–1.15 and 95% CI excludes 1)."
  ),
  "",
  "### Audit-semantic sensitivity",
  "",
  "The separately hashed pre-model addendum adds only exact `Hold Dose`",
  "and `Not Given per Sliding Scale*`. The frozen literal model above",
  "remains primary and governs every gate.",
  "",
  "```text",
  format_table(sensitivity_primary),
  "```",
  "",
  "## Published-style primary model pairs",
  "",
  "```text",
  format_table(primary_effects),
  "```",
  "",
  "## Primary effect-change estimands",
  "",
  "```text",
  format_table(primary_change),
  "```",
  "",
  "A material change is locked as a direction reversal, an absolute log-effect",
  "change of at least log(1.25), or a relative absolute log-effect change of",
  "at least 25%. Statistical significance is not a selection rule.",
  "",
  "## Same-cohort verification and sensitivities",
  "",
  "```text",
  format_table(same_cohort_check),
  "```",
  "",
  "Enriched OASIS/organ-support models and the A2 48-hour landmark diagnostic",
  "are retained in the machine-readable tables. They do not replace the",
  "published-style primary model pair.",
  ""
)
writeLines(
  enc2utf8(report_lines),
  file.path(reports_dir, "05_published_association_effect_change.md"),
  useBytes = TRUE
)

session_lines <- capture.output(sessionInfo())
writeLines(
  session_lines,
  file.path(environment_dir, "R_sessionInfo.txt"),
  useBytes = TRUE
)

metadata <- list(
  started_at = format(started, "%Y-%m-%dT%H:%M:%S%z"),
  finished_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
  elapsed_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
  script = script_path,
  script_md5 = unname(tools::md5sum(script_path)),
  frozen_manifest_present = TRUE,
  semantic_addendum_manifest_present = TRUE,
  not_given_events_n = sum(not_given$total_n),
  not_given_stays_n = uniqueN(not_given$stay_id),
  oasis_event_weighted_mean = oasis_mean,
  oasis_event_weighted_sd = oasis_sd,
  meaningful_oasis_association = meaningful_oasis,
  not_given_audit_sensitivity_events_n =
    sum(not_given_sensitivity$total_n),
  not_given_audit_sensitivity_stays_n =
    uniqueN(not_given_sensitivity$stay_id),
  audit_sensitivity_oasis_event_weighted_mean = sensitivity_oasis_mean,
  audit_sensitivity_oasis_event_weighted_sd = sensitivity_oasis_sd,
  primary_material_effect_change_anchors = effect_change[
    model_variant == "published_style_minimal" &
      material_effect_change == TRUE,
    unique(anchor_id)
  ],
  same_cohort_all_pairs = all(same_cohort_check$identical_n_and_outcomes),
  causal_claim = FALSE,
  significance_based_selection = FALSE
)
write_json(
  metadata,
  file.path(manifests_dir, "05_fit_prespecified_models.json"),
  pretty = TRUE,
  auto_unbox = TRUE,
  null = "null"
)
log_message(
  "DONE all prespecified R models elapsed_seconds=",
  round(metadata$elapsed_seconds, 3)
)
