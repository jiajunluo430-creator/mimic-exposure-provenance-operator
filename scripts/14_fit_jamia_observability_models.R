suppressPackageStartupMessages({
  library(data.table)
  library(digest)
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
runtime_args <- commandArgs(trailingOnly = TRUE)
extension_version <- if (
  "--extension-version=v1_1" %in% runtime_args
) {
  "v1_1"
} else {
  "v1_0"
}
extension_root <- file.path(
  project,
  "outputs",
  if (extension_version == "v1_1") {
    "jamia_observability_v1_1"
  } else {
    "jamia_observability"
  }
)
inputs_dir <- file.path(extension_root, "model_inputs")
tables_dir <- file.path(extension_root, "tables")
logs_dir <- file.path(extension_root, "logs")
manifests_dir <- file.path(extension_root, "manifests")
reports_dir <- file.path(project, "reports")
environment_dir <- file.path(project, "environment")
dir.create(tables_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(logs_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(manifests_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(reports_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(environment_dir, recursive = TRUE, showWarnings = FALSE)

log_path <- file.path(logs_dir, "14_fit_jamia_observability_models.log")
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

verify_contract <- function() {
  manifest_path <- file.path(
    project,
    "contracts",
    if (extension_version == "v1_1") {
      "jamia_observability_sha256_v1.1_2026-07-30.txt"
    } else {
      "jamia_observability_sha256_2026-07-30.txt"
    }
  )
  if (!file.exists(manifest_path)) {
    stop("JAMIA observability contract manifest is missing.")
  }
  lines <- readLines(manifest_path, warn = FALSE)
  lines <- lines[nzchar(trimws(lines))]
  checks <- rbindlist(lapply(lines, function(line) {
    fields <- strsplit(trimws(line), "\\s+", perl = TRUE)[[1]]
    expected <- fields[1]
    name <- paste(fields[-1], collapse = " ")
    path <- if (name == "analysis_decision_log.md") {
      file.path(project, name)
    } else {
      file.path(project, "contracts", name)
    }
    actual <- digest(file = path, algo = "sha256", serialize = FALSE)
    data.table(
      file = name,
      expected_sha256 = expected,
      actual_sha256 = actual,
      match = identical(tolower(expected), tolower(actual))
    )
  }))
  if (nrow(checks) == 0L || !all(checks$match)) {
    stop("JAMIA observability contract hash verification failed.")
  }
  fwrite(
    checks,
    file.path(manifests_dir, "14_contract_verification.csv")
  )
  checks
}

contract_checks <- verify_contract()
log_message("PASS JAMIA contract verification files=", nrow(contract_checks))

required_inputs <- c(
  primary_all = file.path(inputs_dir, "not_given_primary_corrected_all.csv"),
  primary_post = file.path(inputs_dir, "not_given_primary_corrected_post.csv"),
  semantic_all = file.path(inputs_dir, "not_given_semantic_corrected_all.csv"),
  semantic_post = file.path(inputs_dir, "not_given_semantic_corrected_post.csv"),
  a1_all = file.path(inputs_dir, "anchor_a1_corrected_all.csv"),
  a1_post = file.path(inputs_dir, "anchor_a1_corrected_post.csv"),
  a2_all = file.path(inputs_dir, "anchor_a2_corrected_all.csv"),
  a2_post = file.path(inputs_dir, "anchor_a2_corrected_post.csv")
)
if (!all(file.exists(required_inputs))) {
  stop(
    "Missing corrected model inputs: ",
    paste(names(required_inputs)[!file.exists(required_inputs)], collapse = ", ")
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
  analysis_population, anchor_id, model_variant, exposure_definition,
  effect_measure, n, outcomes, exposed, error, warnings
) {
  data.table(
    analysis_population = analysis_population,
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
  fitted, analysis_population, anchor_id, model_variant,
  exposure_definition, data
) {
  n <- nrow(data)
  outcomes <- sum(data$outcome)
  exposed <- sum(data$exposure)
  if (is.null(fitted$fit)) {
    return(failed_effect(
      analysis_population, anchor_id, model_variant, exposure_definition,
      "OR", n, outcomes, exposed, fitted$error, fitted$warnings
    ))
  }
  coefficients <- summary(fitted$fit)$coefficients
  if (!"exposure" %in% rownames(coefficients)) {
    return(failed_effect(
      analysis_population, anchor_id, model_variant, exposure_definition,
      "OR", n, outcomes, exposed, "Exposure coefficient absent",
      fitted$warnings
    ))
  }
  beta <- coefficients["exposure", "Estimate"]
  se <- coefficients["exposure", "Std. Error"]
  data.table(
    analysis_population = analysis_population,
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
  fitted, analysis_population, anchor_id, model_variant,
  exposure_definition, data
) {
  n <- nrow(data)
  outcomes <- sum(data$outcome)
  exposed <- sum(data$exposure)
  if (is.null(fitted$fit)) {
    return(failed_effect(
      analysis_population, anchor_id, model_variant, exposure_definition,
      "HR", n, outcomes, exposed, fitted$error, fitted$warnings
    ))
  }
  coefficients <- summary(fitted$fit)$coefficients
  if (!"exposure" %in% rownames(coefficients)) {
    return(failed_effect(
      analysis_population, anchor_id, model_variant, exposure_definition,
      "HR", n, outcomes, exposed, "Exposure coefficient absent",
      fitted$warnings
    ))
  }
  beta <- coefficients["exposure", "coef"]
  se <- coefficients["exposure", "se(coef)"]
  data.table(
    analysis_population = analysis_population,
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

locked_terms <- c(
  "oasis_z",
  "shiftnight_1900_0659",
  "invasive_ventilation_active",
  "vasopressor_active",
  "rrt_active"
)

locked_labels <- c(
  oasis_z = "OASIS per SD",
  shiftnight_1900_0659 = "Night versus day shift",
  invasive_ventilation_active = "Active invasive ventilation",
  vasopressor_active = "Active vasopressor",
  rrt_active = "Active RRT"
)

fit_not_given <- function(path, analysis_population, event_mapping) {
  d <- fread(path, na.strings = c("", "NA"))
  d[, gender := relevel(factor(gender), ref = "F")]
  d[, shift := relevel(factor(shift), ref = "day_0700_1859")]
  d[, drug_class := factor(drug_class)]
  d[, first_careunit := factor(first_careunit)]
  d[, anchor_era := factor(anchor_era)]
  d[, total_n := not_given_n + given_n]
  oasis_mean <- weighted.mean(d$oasis, d$total_n, na.rm = TRUE)
  oasis_sd <- weighted_sd(d$oasis, d$total_n)
  if (!is.finite(oasis_sd) || oasis_sd <= 0) {
    stop("Cannot calculate event-weighted OASIS SD for ", analysis_population)
  }
  d[, oasis_z := (oasis - oasis_mean) / oasis_sd]
  formula <- cbind(not_given_n, given_n) ~
    oasis_z + oasis_missing_components_n + shift +
    invasive_ventilation_active + vasopressor_active + rrt_active +
    drug_class + age_at_icu + gender + emergency_admission +
    first_careunit + anchor_era
  needed <- all.vars(formula)
  d <- d[complete.cases(d[, ..needed])]
  fitted <- safe_glm(formula, d)
  if (is.null(fitted$fit)) {
    return(list(
      coefficients = data.table(),
      correlates = data.table(),
      status = data.table(
        analysis_population = analysis_population,
        event_mapping = event_mapping,
        converged = FALSE,
        model_error = fitted$error,
        model_warnings = fitted$warnings,
        rows_n = nrow(d),
        decision_events_n = sum(d$total_n),
        stays_n = uniqueN(d$stay_id),
        oasis_event_weighted_mean = oasis_mean,
        oasis_event_weighted_sd = oasis_sd,
        meaningful_oasis = FALSE
      )
    ))
  }
  robust <- vcovCL(fitted$fit, cluster = d$stay_id, type = "HC0")
  test <- coeftest(fitted$fit, vcov. = robust)
  coefficients <- data.table(
    analysis_population = analysis_population,
    event_mapping = event_mapping,
    term = rownames(test),
    beta = test[, "Estimate"],
    cluster_robust_se = test[, "Std. Error"],
    z_value = test[, "z value"],
    p_value = test[, "Pr(>|z|)"]
  )
  coefficients[
    ,
    `:=`(
      adjusted_or = exp(beta),
      ci_low = exp(beta - qnorm(0.975) * cluster_robust_se),
      ci_high = exp(beta + qnorm(0.975) * cluster_robust_se)
    )
  ]
  correlates <- coefficients[term %in% locked_terms]
  correlates[, bh_q_value := p.adjust(p_value, method = "BH")]
  correlates[, locked_correlate := unname(locked_labels[term])]
  setcolorder(
    correlates,
    c(
      "analysis_population", "event_mapping", "locked_correlate", "term",
      "adjusted_or", "ci_low", "ci_high", "beta", "cluster_robust_se",
      "z_value", "p_value", "bh_q_value"
    )
  )
  oasis_row <- correlates[term == "oasis_z"]
  meaningful_oasis <- (
    nrow(oasis_row) == 1L &&
      is.finite(oasis_row$adjusted_or) &&
      (oasis_row$adjusted_or >= 1.15 || oasis_row$adjusted_or <= 0.87) &&
      (oasis_row$ci_low > 1 || oasis_row$ci_high < 1)
  )
  list(
    coefficients = coefficients,
    correlates = correlates,
    status = data.table(
      analysis_population = analysis_population,
      event_mapping = event_mapping,
      converged = isTRUE(fitted$fit$converged),
      model_error = NA_character_,
      model_warnings = fitted$warnings,
      rows_n = nrow(d),
      decision_events_n = sum(d$total_n),
      stays_n = uniqueN(d$stay_id),
      oasis_event_weighted_mean = oasis_mean,
      oasis_event_weighted_sd = oasis_sd,
      meaningful_oasis = meaningful_oasis
    )
  )
}

not_given_specs <- list(
  list(
    path = required_inputs[["primary_all"]],
    population = "all_periods_corrected_era",
    mapping = "frozen_primary"
  ),
  list(
    path = required_inputs[["primary_post"]],
    population = "post_implementation",
    mapping = "frozen_primary"
  ),
  list(
    path = required_inputs[["semantic_all"]],
    population = "all_periods_corrected_era",
    mapping = "audit_semantic_sensitivity"
  ),
  list(
    path = required_inputs[["semantic_post"]],
    population = "post_implementation",
    mapping = "audit_semantic_sensitivity"
  )
)

not_given_results <- vector("list", length(not_given_specs))
for (i in seq_along(not_given_specs)) {
  spec <- not_given_specs[[i]]
  log_message(
    "START not-given model population=", spec$population,
    " mapping=", spec$mapping
  )
  not_given_results[[i]] <- fit_not_given(
    spec$path, spec$population, spec$mapping
  )
  log_message(
    "DONE not-given model population=", spec$population,
    " mapping=", spec$mapping,
    " converged=", not_given_results[[i]]$status$converged
  )
}

not_given_coefficients <- rbindlist(
  lapply(not_given_results, `[[`, "coefficients"),
  use.names = TRUE,
  fill = TRUE
)
not_given_correlates <- rbindlist(
  lapply(not_given_results, `[[`, "correlates"),
  use.names = TRUE,
  fill = TRUE
)
not_given_status <- rbindlist(
  lapply(not_given_results, `[[`, "status"),
  use.names = TRUE,
  fill = TRUE
)
fwrite(
  not_given_coefficients,
  file.path(tables_dir, "not_given_corrected_all_coefficients.csv")
)
fwrite(
  not_given_correlates,
  file.path(tables_dir, "not_given_corrected_prespecified_correlates.csv")
)
fwrite(
  not_given_status,
  file.path(tables_dir, "not_given_corrected_model_status.csv")
)

prepare_common <- function(d) {
  d[, gender := relevel(factor(gender), ref = "F")]
  d[, anchor_era := factor(anchor_era)]
  d[, oasis_z := as.numeric(scale(oasis))]
  d
}

fit_a1_pair <- function(data, analysis_population, enriched = FALSE) {
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
      formula <- outcome ~ exposure + age + gender + emergency_admission
    }
    needed <- all.vars(formula)
    d <- d[complete.cases(d[, ..needed])]
    fitted <- safe_glm(formula, d)
    rows[[exposure_name]] <- extract_glm_effect(
      fitted, analysis_population, "A1", variant,
      sub("_exposure$", "", exposure_name), d
    )
  }
  rbindlist(rows, use.names = TRUE, fill = TRUE)
}

fit_a2_pair <- function(
  data, analysis_population, enriched = FALSE, landmark = FALSE
) {
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
      setdiff(all.vars(formula), "Surv")
    ))
    d <- d[complete.cases(d[, ..needed])]
    fitted <- safe_cox(formula, d)
    rows[[exposure_name]] <- extract_cox_effect(
      fitted, analysis_population, "A2", variant,
      sub("_exposure$", "", exposure_name), d
    )
  }
  rbindlist(rows, use.names = TRUE, fill = TRUE)
}

fit_anchor_population <- function(
  a1_path, a2_path, analysis_population
) {
  a1 <- prepare_common(fread(a1_path, na.strings = c("", "NA")))
  a2 <- prepare_common(fread(a2_path, na.strings = c("", "NA")))
  rbindlist(
    list(
      fit_a1_pair(a1, analysis_population, enriched = FALSE),
      fit_a1_pair(a1, analysis_population, enriched = TRUE),
      fit_a2_pair(
        a2, analysis_population, enriched = FALSE, landmark = FALSE
      ),
      fit_a2_pair(
        a2, analysis_population, enriched = TRUE, landmark = FALSE
      ),
      fit_a2_pair(
        a2, analysis_population, enriched = FALSE, landmark = TRUE
      ),
      fit_a2_pair(
        a2, analysis_population, enriched = TRUE, landmark = TRUE
      )
    ),
    use.names = TRUE,
    fill = TRUE
  )
}

log_message("START corrected all-period anchor model pairs")
all_effects <- fit_anchor_population(
  required_inputs[["a1_all"]],
  required_inputs[["a2_all"]],
  "all_periods_corrected_era"
)
log_message("DONE corrected all-period anchor model pairs")

log_message("START post-implementation anchor model pairs")
post_effects <- fit_anchor_population(
  required_inputs[["a1_post"]],
  required_inputs[["a2_post"]],
  "post_implementation"
)
log_message("DONE post-implementation anchor model pairs")

association_effects <- rbindlist(
  list(all_effects, post_effects),
  use.names = TRUE,
  fill = TRUE
)
fwrite(
  association_effects,
  file.path(tables_dir, "anchor_model_effects_by_population.csv")
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
  by = .(analysis_population, anchor_id, model_variant)
]
fwrite(
  same_cohort_check,
  file.path(tables_dir, "anchor_same_cohort_check_by_population.csv")
)

effect_change <- dcast(
  association_effects,
  analysis_population + anchor_id + model_variant + effect_measure ~
    exposure_definition,
  value.var = c(
    "beta", "effect", "ci_low", "ci_high", "n", "outcomes_n", "exposed_n"
  )
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
  file.path(tables_dir, "anchor_effect_change_by_population.csv")
)

pre_gates_path <- file.path(tables_dir, "pilot_gates_pre_model.csv")
gates <- fread(pre_gates_path)
set_gate <- function(gate_id, status, evidence) {
  gate_id_value <- gate_id
  status_value <- status
  evidence_value <- evidence
  gates[
    gate_id == gate_id_value,
    `:=`(status = status_value, evidence = evidence_value)
  ]
}

j04_pass <- nrow(not_given_status) == 4L && all(not_given_status$converged)
set_gate(
  "J04",
  if (j04_pass) "PASS" else "FAIL",
  paste0(
    sum(not_given_status$converged), "/4 corrected not-given models converged"
  )
)

post_primary_effects <- association_effects[
  analysis_population == "post_implementation" &
    model_variant == "published_style_minimal"
]
j05_summary <- post_primary_effects[
  ,
  .(
    n = unique(n),
    order_exposed = exposed_n[exposure_definition == "order"],
    administration_exposed =
      exposed_n[exposure_definition == "administration"]
  ),
  by = anchor_id
]
j05_pass <- (
  nrow(j05_summary) == 2L &&
    all(j05_summary$n >= 500) &&
    all(j05_summary$order_exposed > 0) &&
    all(j05_summary$administration_exposed > 0)
)
set_gate(
  "J05",
  if (j05_pass) "PASS" else "FAIL",
  paste(
    paste0(
      j05_summary$anchor_id, ": n=", j05_summary$n,
      ", order=", j05_summary$order_exposed,
      ", admin=", j05_summary$administration_exposed
    ),
    collapse = " | "
  )
)

j06_pass <- all(same_cohort_check$identical_n_and_outcomes)
set_gate(
  "J06",
  if (j06_pass) "PASS" else "FAIL",
  paste0(
    sum(same_cohort_check$identical_n_and_outcomes), "/",
    nrow(same_cohort_check), " paired variants have identical n/outcomes"
  )
)

post_primary_change <- effect_change[
  analysis_population == "post_implementation" &
    model_variant == "published_style_minimal"
]
material_post_anchors <- post_primary_change[
  material_effect_change == TRUE, unique(anchor_id)
]
j07_pass <- length(material_post_anchors) >= 1L
set_gate(
  "J07",
  if (j07_pass) "PASS" else "FAIL",
  if (j07_pass) {
    paste(
      "Material post-implementation anchor(s):",
      paste(material_post_anchors, collapse = ", ")
    )
  } else {
    "Neither post-implementation published-style anchor met the frozen rule"
  }
)
set_gate(
  "J08",
  "PASS",
  "Outcome models used deployment_era inputs only; any_emar was not a filter"
)
set_gate(
  "J09",
  "PENDING_TEXT_QA",
  "Claim-boundary scan follows manuscript revision"
)
set_gate(
  "J10",
  "PENDING_FINAL_VALIDATION",
  "Model assets complete; final package validation pending"
)

fatal_ids <- c("J01", "J02", "J03", "J04", "J05", "J06", "J08")
fatal_failure <- any(gates[gate_id %in% fatal_ids, status != "PASS"])
decision <- if (fatal_failure) {
  "NO_GO_JAMIA_IMPLEMENTATION"
} else if (j07_pass) {
  "GO_JAMIA_ANALYTIC"
} else {
  "BACKUP_PDS"
}
fwrite(gates, file.path(tables_dir, "pilot_gates_after_models.csv"))

format_table <- function(x) {
  paste(
    capture.output(print(as.data.frame(x), row.names = FALSE)),
    collapse = "\n"
  )
}

key_effects <- association_effects[
  model_variant == "published_style_minimal",
  .(
    analysis_population, anchor_id, exposure_definition, effect_measure,
    n, outcomes_n, exposed_n, effect, ci_low, ci_high
  )
]
key_change <- effect_change[
  model_variant == "published_style_minimal",
  .(
    analysis_population, anchor_id, effect_measure,
    effect_order, effect_administration,
    absolute_log_effect_change,
    relative_absolute_log_effect_change_pct,
    ratio_of_effects_admin_to_order,
    direction_reversal,
    material_effect_change
  )
]

report_lines <- c(
  if (extension_version == "v1_1") {
    "# 17 — JAMIA observability v1.1 post-2016 models"
  } else {
    "# 13 — JAMIA observability corrected and post-implementation models"
  },
  "",
  paste0("**Decision: ", decision, ".**"),
  "",
  "The original frozen outputs remain preserved. Models below use the same",
  "classes, exposure definitions, windows, cohorts, outcomes, covariates,",
  "model families, and material-change rule. The complete-cohort repair changes",
  "only stay-level calendar alignment; the post-implementation analysis is the",
  "versioned observability sensitivity.",
  "",
  "## Corrected and post-implementation not-given correlates",
  "",
  "```text",
  format_table(not_given_correlates),
  "```",
  "",
  "## Published-style anchor effects",
  "",
  "```text",
  format_table(key_effects),
  "```",
  "",
  "## Effect-change estimands",
  "",
  "```text",
  format_table(key_change),
  "```",
  "",
  "## Same-cohort verification",
  "",
  "```text",
  format_table(same_cohort_check),
  "```",
  "",
  "## JAMIA pilot gates",
  "",
  "```text",
  format_table(gates),
  "```",
  "",
  "`any_emar_in_admission` was not used to select an outcome-model cohort.",
  "The estimates remain exposure-definition sensitivity analyses and are not",
  "new causal drug-effect estimates.",
  ""
)
report_path <- file.path(
  reports_dir,
  if (extension_version == "v1_1") {
    "17_jamia_observability_v1_1_model_results.md"
  } else {
    "13_jamia_observability_model_results.md"
  }
)
writeLines(enc2utf8(report_lines), report_path, useBytes = TRUE)

session_lines <- capture.output(sessionInfo())
writeLines(
  session_lines,
  file.path(
    environment_dir,
    if (extension_version == "v1_1") {
      "R_sessionInfo_JAMIA_observability_v1_1.txt"
    } else {
      "R_sessionInfo_JAMIA_observability.txt"
    }
  ),
  useBytes = TRUE
)

metadata <- list(
  started_at = format(started, "%Y-%m-%dT%H:%M:%S%z"),
  finished_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
  elapsed_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
  script = script_path,
  script_sha256 = digest(
    file = script_path, algo = "sha256", serialize = FALSE
  ),
  extension_version = extension_version,
  deployment_interval = if (extension_version == "v1_1") {
    "2014-2016_source_corrected"
  } else {
    "2011-2013_v1_0_superseded"
  },
  contract_verified = TRUE,
  not_given_models_n = nrow(not_given_status),
  not_given_models_converged_n = sum(not_given_status$converged),
  anchor_effect_rows_n = nrow(association_effects),
  paired_variants_n = nrow(same_cohort_check),
  same_cohort_all_pairs = j06_pass,
  material_post_implementation_anchors = material_post_anchors,
  any_emar_used_for_outcome_selection = FALSE,
  decision = decision,
  causal_claim = FALSE,
  significance_based_selection = FALSE
)
write_json(
  metadata,
  file.path(manifests_dir, "14_jamia_observability_models.json"),
  pretty = TRUE,
  auto_unbox = TRUE,
  null = "null"
)

log_message(
  "DONE JAMIA observability models decision=", decision,
  " elapsed_seconds=", round(metadata$elapsed_seconds, 3)
)
