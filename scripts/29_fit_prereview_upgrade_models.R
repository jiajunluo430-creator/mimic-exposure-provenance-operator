suppressPackageStartupMessages({
  library(data.table)
  library(digest)
  library(jsonlite)
  library(survival)
})

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(script_arg) != 1L) stop("Cannot resolve script path")
script_path <- normalizePath(
  sub("^--file=", "", script_arg), winslash = "\\", mustWork = TRUE
)
project <- dirname(dirname(script_path))
root <- file.path(project, "outputs", "jamia_prereview_upgrade_v1_0")
inputs <- file.path(root, "model_inputs")
tables <- file.path(root, "tables")
logs <- file.path(root, "logs")
manifests <- file.path(root, "manifests")
environment <- file.path(project, "environment")
dir.create(tables, recursive = TRUE, showWarnings = FALSE)
dir.create(logs, recursive = TRUE, showWarnings = FALSE)
dir.create(manifests, recursive = TRUE, showWarnings = FALSE)
dir.create(environment, recursive = TRUE, showWarnings = FALSE)

log_path <- file.path(logs, "29_fit_prereview_upgrade_models.log")
started <- Sys.time()
log_message <- function(...) {
  line <- paste(
    format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
    paste0(..., collapse = ""), sep = "\t"
  )
  cat(line, "\n")
  cat(line, "\n", file = log_path, append = TRUE)
}

contract_name <- "jamia_prereview_upgrade_addendum_v1.0_2026-07-31.md"
expected_contract_hash <-
  "0a851a99c9176c16deda2cde9e30fded7f2b5131a5a3f64ac7f050ebd8f81d9d"
contract_path <- file.path(project, "contracts", contract_name)
observed_contract_hash <- digest(
  file = contract_path, algo = "sha256", serialize = FALSE
)
contract_check <- data.table(
  file = contract_name,
  expected_sha256 = expected_contract_hash,
  observed_sha256 = observed_contract_hash,
  match = identical(tolower(expected_contract_hash),
                    tolower(observed_contract_hash))
)
if (!contract_check$match) stop("Prereview-upgrade contract hash mismatch")
fwrite(contract_check, file.path(manifests, "29_contract_verification.csv"))
log_message("PASS prereview-upgrade contract verification")

required <- c(
  a1 = file.path(inputs, "anchor_a1_prereview_upgrade.csv"),
  a2 = file.path(inputs, "anchor_a2_prereview_upgrade.csv")
)
if (!all(file.exists(required))) {
  stop("Missing model inputs: ",
       paste(names(required)[!file.exists(required)], collapse = ", "))
}

safe_relevel <- function(x, ref) {
  x <- factor(x)
  if (ref %in% levels(x)) relevel(x, ref = ref) else x
}

prepare_anchor <- function(d) {
  d <- copy(d)
  d[, gender := safe_relevel(gender, "F")]
  d[, anchor_era := factor(anchor_era)]
  d[, first_careunit := factor(first_careunit)]
  sd_oasis <- sd(d$oasis, na.rm = TRUE)
  d[, oasis_z := if (is.finite(sd_oasis) && sd_oasis > 0) {
    (oasis - mean(oasis, na.rm = TRUE)) / sd_oasis
  } else NA_real_]
  d
}

a1 <- prepare_anchor(fread(required[["a1"]], na.strings = c("", "NA")))
a2 <- prepare_anchor(fread(required[["a2"]], na.strings = c("", "NA")))
if (nrow(a1) != 20248L || uniqueN(a1$subject_id) != nrow(a1)) {
  stop("A1 input count or subject uniqueness failed")
}
if (nrow(a2) != 2813L || uniqueN(a2$subject_id) != nrow(a2)) {
  stop("A2 input count or subject uniqueness failed")
}

minimal_covariates <- list(
  A1 = c("age", "gender", "emergency_admission"),
  A2 = c("age", "gender", "emergency_admission", "anchor_era")
)
enriched_additions <- c(
  "oasis_z", "oasis_missing_components_n", "first_day_mechvent",
  "first_day_vasopressor", "first_day_rrt"
)

failed_effect <- function(anchor, operator, source, variant, measure, d, error) {
  data.table(
    anchor_id = anchor, operator = operator, exposure_source = source,
    model_variant = variant, effect_measure = measure,
    patients_n = uniqueN(d$subject_id), outcomes_n = sum(d$outcome),
    exposed_n = sum(d$exposure), beta = NA_real_, standard_error = NA_real_,
    effect = NA_real_, ci_low = NA_real_, ci_high = NA_real_,
    p_value = NA_real_, converged = FALSE, model_error = error
  )
}

fit_static <- function(data, anchor, operator, source, exposure_col, enriched) {
  d <- copy(data)
  d[, exposure := as.integer(get(exposure_col))]
  variant <- if (enriched) "enriched" else "published_style_minimal"
  covariates <- minimal_covariates[[anchor]]
  if (enriched) covariates <- c(covariates, enriched_additions)
  rhs <- paste(c("exposure", covariates), collapse = " + ")
  if (anchor == "A1") {
    form <- as.formula(paste("outcome ~", rhs))
    measure <- "OR"
  } else {
    form <- as.formula(paste("Surv(followup_days, outcome) ~", rhs))
    measure <- "HR"
  }
  needed <- unique(c(all.vars(form), "subject_id", "exposure", "outcome"))
  d <- d[complete.cases(d[, ..needed])]
  fit <- tryCatch(
    if (anchor == "A1") {
      glm(form, data = d, family = binomial())
    } else {
      coxph(form, data = d, ties = "efron", x = TRUE)
    }, error = function(e) e
  )
  if (inherits(fit, "error")) {
    return(failed_effect(
      anchor, operator, source, variant, measure, d, conditionMessage(fit)
    ))
  }
  co <- summary(fit)$coefficients
  if (!"exposure" %in% rownames(co)) {
    return(failed_effect(
      anchor, operator, source, variant, measure, d,
      "Exposure coefficient absent"
    ))
  }
  beta <- co["exposure", if (anchor == "A1") "Estimate" else "coef"]
  se <- co["exposure", if (anchor == "A1") "Std. Error" else "se(coef)"]
  data.table(
    anchor_id = anchor, operator = operator, exposure_source = source,
    model_variant = variant, effect_measure = measure,
    patients_n = uniqueN(d$subject_id), outcomes_n = sum(d$outcome),
    exposed_n = sum(d$exposure), beta = beta, standard_error = se,
    effect = exp(beta), ci_low = exp(beta - qnorm(0.975) * se),
    ci_high = exp(beta + qnorm(0.975) * se),
    p_value = co["exposure", "Pr(>|z|)"],
    converged = if (anchor == "A1") isTRUE(fit$converged) else TRUE,
    model_error = NA_character_
  )
}

pair_specs <- rbindlist(list(
  data.table(
    anchor_id = "A1",
    operator = c(
      "original_strict", "original_broad", "metadata_constrained_broad"
    ),
    order_col = "order_exposure",
    administration_col = c(
      "admin_strict", "admin_broad", "admin_metadata_constrained"
    )
  ),
  data.table(
    anchor_id = "A2",
    operator = c(
      "original_strict", "original_broad", "hospital_overlap_strict",
      "hospital_overlap_broad"
    ),
    order_col = c(
      "order_exposure", "order_exposure", "hospital_order_exposure",
      "hospital_order_exposure"
    ),
    administration_col = c(
      "admin_strict", "admin_broad", "hospital_admin_strict", "admin_broad"
    )
  )
))

log_message("START static prereview-upgrade models")
static_effects <- rbindlist(lapply(seq_len(nrow(pair_specs)), function(i) {
  s <- pair_specs[i]
  d <- if (s$anchor_id == "A1") a1 else a2
  rbindlist(lapply(c(FALSE, TRUE), function(enriched) {
    rbindlist(list(
      fit_static(
        d, s$anchor_id, s$operator, "order", s$order_col, enriched
      ),
      fit_static(
        d, s$anchor_id, s$operator, "administration",
        s$administration_col, enriched
      )
    ))
  }))
}))
fwrite(static_effects, file.path(tables, "prereview_static_model_effects.csv"))
if (!all(static_effects$converged)) stop("At least one static model failed")
log_message("DONE static models rows=", nrow(static_effects))

make_timevarying <- function(data, onset_col) {
  d <- copy(data)
  d[, onset_days := as.numeric(get(onset_col)) / 24]
  pieces <- lapply(seq_len(nrow(d)), function(i) {
    row <- copy(d[i])
    follow <- min(as.numeric(row$followup_days), 90)
    onset <- row$onset_days
    if (!is.finite(follow) || follow <= 0) return(NULL)
    if (!is.finite(onset) || onset >= follow || onset > 2) {
      row[, `:=`(tstart = 0, tstop = follow, exposure = 0L,
                 status = outcome)]
      return(row)
    }
    onset <- max(0, onset)
    if (onset == 0) {
      row[, `:=`(tstart = 0, tstop = follow, exposure = 1L,
                 status = outcome)]
      return(row)
    }
    before <- copy(row)
    before[, `:=`(tstart = 0, tstop = onset, exposure = 0L, status = 0L)]
    after <- copy(row)
    after[, `:=`(tstart = onset, tstop = follow, exposure = 1L,
                 status = outcome)]
    rbind(before, after)
  })
  rbindlist(pieces, use.names = TRUE, fill = TRUE)
}

fit_timevarying <- function(data, operator, source, onset_col, enriched) {
  long <- make_timevarying(data, onset_col)
  variant <- if (enriched) "time_varying_enriched" else "time_varying_minimal"
  covariates <- minimal_covariates[["A2"]]
  if (enriched) covariates <- c(covariates, enriched_additions)
  rhs <- paste(c("exposure", covariates, "cluster(subject_id)"),
               collapse = " + ")
  form <- as.formula(paste("Surv(tstart, tstop, status) ~", rhs))
  fit <- tryCatch(
    coxph(form, data = long, ties = "efron", x = TRUE),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    fake <- unique(long, by = "subject_id")
    fake[, outcome := status]
    return(failed_effect(
      "A2", operator, source, variant, "HR", fake, conditionMessage(fit)
    ))
  }
  co <- summary(fit)$coefficients
  beta <- co["exposure", "coef"]
  se_name <- if ("robust se" %in% colnames(co)) "robust se" else "se(coef)"
  se <- co["exposure", se_name]
  data.table(
    anchor_id = "A2", operator = operator, exposure_source = source,
    model_variant = variant, effect_measure = "HR",
    patients_n = uniqueN(long$subject_id), outcomes_n = sum(long$status),
    exposed_n = uniqueN(long[exposure == 1, subject_id]),
    beta = beta, standard_error = se, effect = exp(beta),
    ci_low = exp(beta - qnorm(0.975) * se),
    ci_high = exp(beta + qnorm(0.975) * se),
    p_value = co["exposure", "Pr(>|z|)"], converged = TRUE,
    model_error = NA_character_
  )
}

tv_specs <- data.table(
  operator = c(
    "original_strict", "original_broad", "hospital_overlap_strict",
    "hospital_overlap_broad"
  ),
  order_onset_col = c(
    "order_onset_hours", "order_onset_hours", "hospital_order_onset_hours",
    "hospital_order_onset_hours"
  ),
  administration_onset_col = c(
    "strict_admin_onset_hours", "broad_admin_onset_hours",
    "hospital_strict_admin_onset_hours", "broad_admin_onset_hours"
  )
)

log_message("START time-varying prereview-upgrade models")
tv_effects <- rbindlist(lapply(seq_len(nrow(tv_specs)), function(i) {
  s <- tv_specs[i]
  rbindlist(lapply(c(FALSE, TRUE), function(enriched) {
    rbindlist(list(
      fit_timevarying(a2, s$operator, "order", s$order_onset_col, enriched),
      fit_timevarying(
        a2, s$operator, "administration", s$administration_onset_col,
        enriched
      )
    ))
  }))
}))
fwrite(tv_effects, file.path(tables, "prereview_time_varying_effects.csv"))
if (!all(tv_effects$converged)) stop("At least one time-varying model failed")
log_message("DONE time-varying models rows=", nrow(tv_effects))

fit_concordant <- function(data, anchor, operator, order_col, admin_col) {
  d <- copy(data)[get(order_col) == get(admin_col)]
  d[, exposure := as.integer(get(order_col))]
  if (anchor == "A1") {
    form <- outcome ~ exposure + age + gender + emergency_admission
    fit <- tryCatch(glm(form, data = d, family = binomial()),
                    error = function(e) e)
    measure <- "OR"
  } else {
    form <- Surv(followup_days, outcome) ~ exposure + age + gender +
      emergency_admission + anchor_era
    fit <- tryCatch(coxph(form, data = d, ties = "efron"),
                    error = function(e) e)
    measure <- "HR"
  }
  if (inherits(fit, "error")) {
    return(failed_effect(
      anchor, operator, "common_concordant", "concordant_minimal", measure,
      d, conditionMessage(fit)
    ))
  }
  co <- summary(fit)$coefficients
  beta <- co["exposure", if (anchor == "A1") "Estimate" else "coef"]
  se <- co["exposure", if (anchor == "A1") "Std. Error" else "se(coef)"]
  data.table(
    anchor_id = anchor, operator = operator,
    exposure_source = "common_concordant",
    model_variant = "concordant_minimal", effect_measure = measure,
    patients_n = nrow(d), outcomes_n = sum(d$outcome),
    exposed_n = sum(d$exposure), beta = beta, standard_error = se,
    effect = exp(beta), ci_low = exp(beta - qnorm(0.975) * se),
    ci_high = exp(beta + qnorm(0.975) * se),
    p_value = co["exposure", "Pr(>|z|)"], converged = TRUE,
    model_error = NA_character_
  )
}

concordant_effects <- rbindlist(lapply(seq_len(nrow(pair_specs)), function(i) {
  s <- pair_specs[i]
  d <- if (s$anchor_id == "A1") a1 else a2
  fit_concordant(d, s$anchor_id, s$operator, s$order_col,
                 s$administration_col)
}))
fwrite(
  concordant_effects,
  file.path(tables, "prereview_concordant_subset_effects.csv")
)

static_bootstrap_pair <- function(
  data, anchor, operator, order_col, administration_col, enriched,
  replicate_n = 1000L, seed = 20260731L
) {
  d <- copy(data)
  covariates <- minimal_covariates[[anchor]]
  if (enriched) covariates <- c(covariates, enriched_additions)
  needed <- unique(c(
    "subject_id", "outcome", order_col, administration_col,
    if (anchor == "A2") "followup_days", covariates
  ))
  d <- d[complete.cases(d[, ..needed])]
  n <- nrow(d)
  variant <- if (enriched) "enriched" else "published_style_minimal"
  comparison <- paste(anchor, operator, variant, "static", sep = "__")
  if (anchor == "A1") {
    order_frame <- copy(d); order_frame[, exposure := get(order_col)]
    admin_frame <- copy(d); admin_frame[, exposure := get(administration_col)]
    rhs <- paste(c("exposure", covariates), collapse = " + ")
    x_order <- model.matrix(as.formula(paste("~", rhs)), order_frame)
    x_admin <- model.matrix(as.formula(paste("~", rhs)), admin_frame)
    y <- d$outcome
  }
  set.seed(seed)
  rows <- vector("list", replicate_n)
  for (b in seq_len(replicate_n)) {
    weights <- tabulate(sample.int(n, n, replace = TRUE), nbins = n)
    if (anchor == "A1") {
      bo <- tryCatch(
        unname(glm.fit(
          x = x_order, y = y, weights = weights, family = binomial()
        )$coefficients[["exposure"]]), error = function(e) NA_real_
      )
      ba <- tryCatch(
        unname(glm.fit(
          x = x_admin, y = y, weights = weights, family = binomial()
        )$coefficients[["exposure"]]), error = function(e) NA_real_
      )
    } else {
      keep <- weights > 0
      order_frame <- copy(d[keep]); order_frame[, exposure := get(order_col)]
      admin_frame <- copy(d[keep]); admin_frame[, exposure := get(administration_col)]
      rhs <- paste(c("exposure", covariates), collapse = " + ")
      form <- as.formula(paste("Surv(followup_days, outcome) ~", rhs))
      bo <- tryCatch(unname(coef(coxph(
        form, data = order_frame, weights = weights[keep], ties = "efron",
        robust = FALSE
      ))[["exposure"]]), error = function(e) NA_real_)
      ba <- tryCatch(unname(coef(coxph(
        form, data = admin_frame, weights = weights[keep], ties = "efron",
        robust = FALSE
      ))[["exposure"]]), error = function(e) NA_real_)
    }
    rows[[b]] <- data.table(
      comparison = comparison, anchor_id = anchor, operator = operator,
      model_variant = variant, model_time = "static", replicate = b,
      beta_order = bo, beta_administration = ba,
      delta_log_effect = ba - bo,
      success = is.finite(bo) && is.finite(ba)
    )
  }
  rbindlist(rows)
}

timevarying_bootstrap_pair <- function(
  data, operator, order_onset_col, administration_onset_col, enriched,
  replicate_n = 1000L, seed = 20260731L
) {
  covariates <- minimal_covariates[["A2"]]
  if (enriched) covariates <- c(covariates, enriched_additions)
  needed <- unique(c(
    "subject_id", "followup_days", "outcome", order_onset_col,
    administration_onset_col, covariates
  ))
  d <- copy(data)
  needed_nononset <- setdiff(needed, c(order_onset_col, administration_onset_col))
  d <- d[complete.cases(d[, ..needed_nononset])]
  order_long <- make_timevarying(d, order_onset_col)
  admin_long <- make_timevarying(d, administration_onset_col)
  ids <- d$subject_id
  n <- length(ids)
  variant <- if (enriched) "time_varying_enriched" else "time_varying_minimal"
  comparison <- paste("A2", operator, variant, sep = "__")
  rhs <- paste(c("exposure", covariates), collapse = " + ")
  form <- as.formula(paste("Surv(tstart, tstop, status) ~", rhs))
  set.seed(seed)
  rows <- vector("list", replicate_n)
  for (b in seq_len(replicate_n)) {
    sampled <- sample(ids, n, replace = TRUE)
    counts <- data.table(subject_id = ids, boot_weight = tabulate(
      match(sampled, ids), nbins = n
    ))
    ol <- merge(order_long, counts, by = "subject_id", all.x = TRUE)
    al <- merge(admin_long, counts, by = "subject_id", all.x = TRUE)
    ol <- ol[boot_weight > 0]
    al <- al[boot_weight > 0]
    bo <- tryCatch(unname(coef(coxph(
      form, data = ol, weights = boot_weight, ties = "efron", robust = FALSE
    ))[["exposure"]]), error = function(e) NA_real_)
    ba <- tryCatch(unname(coef(coxph(
      form, data = al, weights = boot_weight, ties = "efron", robust = FALSE
    ))[["exposure"]]), error = function(e) NA_real_)
    rows[[b]] <- data.table(
      comparison = comparison, anchor_id = "A2", operator = operator,
      model_variant = variant, model_time = "time_varying", replicate = b,
      beta_order = bo, beta_administration = ba,
      delta_log_effect = ba - bo,
      success = is.finite(bo) && is.finite(ba)
    )
  }
  rbindlist(rows)
}

bootstrap_parts <- list()
log_message("START complete paired bootstrap coverage")
for (i in seq_len(nrow(pair_specs))) {
  s <- pair_specs[i]
  d <- if (s$anchor_id == "A1") a1 else a2
  for (enriched in c(FALSE, TRUE)) {
    variant <- if (enriched) "enriched" else "published_style_minimal"
    checkpoint <- file.path(
      tables,
      paste0("bootstrap_checkpoint_", s$anchor_id, "_", s$operator, "_",
             variant, "_static.csv")
    )
    if (file.exists(checkpoint)) {
      part <- fread(checkpoint)
    } else {
      log_message("START bootstrap ", basename(checkpoint))
      part <- static_bootstrap_pair(
        d, s$anchor_id, s$operator, s$order_col,
        s$administration_col, enriched
      )
      fwrite(part, checkpoint)
    }
    if (nrow(part) != 1000L) stop("Invalid bootstrap checkpoint: ", checkpoint)
    log_message("CHECKPOINT ", basename(checkpoint),
                " success=", sum(part$success))
    bootstrap_parts[[length(bootstrap_parts) + 1L]] <- part
  }
}
for (i in seq_len(nrow(tv_specs))) {
  s <- tv_specs[i]
  for (enriched in c(FALSE, TRUE)) {
    variant <- if (enriched) "time_varying_enriched" else "time_varying_minimal"
    checkpoint <- file.path(
      tables,
      paste0("bootstrap_checkpoint_v2_A2_", s$operator, "_", variant, ".csv")
    )
    if (file.exists(checkpoint)) {
      part <- fread(checkpoint)
    } else {
      log_message("START bootstrap ", basename(checkpoint))
      part <- timevarying_bootstrap_pair(
        a2, s$operator, s$order_onset_col,
        s$administration_onset_col, enriched
      )
      fwrite(part, checkpoint)
    }
    if (nrow(part) != 1000L) stop("Invalid bootstrap checkpoint: ", checkpoint)
    log_message("CHECKPOINT ", basename(checkpoint),
                " success=", sum(part$success))
    bootstrap_parts[[length(bootstrap_parts) + 1L]] <- part
  }
}
bootstrap_replicates <- rbindlist(bootstrap_parts, fill = TRUE)
fwrite(
  bootstrap_replicates,
  file.path(tables, "prereview_paired_bootstrap_replicates.csv")
)

observed_static <- dcast(
  static_effects,
  anchor_id + operator + model_variant ~ exposure_source,
  value.var = "beta"
)
observed_static[, `:=`(
  model_time = "static",
  comparison = paste(anchor_id, operator, model_variant, "static", sep = "__")
)]
observed_tv <- dcast(
  tv_effects,
  anchor_id + operator + model_variant ~ exposure_source,
  value.var = "beta"
)
observed_tv[, `:=`(
  model_time = "time_varying",
  comparison = paste(anchor_id, operator, model_variant, sep = "__")
)]
observed <- rbindlist(list(observed_static, observed_tv), fill = TRUE)
observed[, `:=`(
  observed_delta_log_effect = administration - order,
  observed_relative_log_change_pct =
    100 * abs((administration - order) / order)
)]
bootstrap_summary <- bootstrap_replicates[, .(
  replicates_n = .N,
  successful_pairs_n = sum(success),
  failed_pairs_n = sum(!success),
  delta_ci_low = quantile(
    delta_log_effect[success], 0.025, na.rm = TRUE
  ),
  delta_ci_high = quantile(
    delta_log_effect[success], 0.975, na.rm = TRUE
  )
), by = .(comparison, anchor_id, operator, model_variant, model_time)]
bootstrap_summary <- merge(
  bootstrap_summary,
  observed[, .(
    comparison, observed_beta_order = order,
    observed_beta_administration = administration,
    observed_delta_log_effect, observed_relative_log_change_pct
  )],
  by = "comparison", all.x = TRUE
)
bootstrap_summary[, minimum_950_pass := successful_pairs_n >= 950L]
fwrite(
  bootstrap_summary,
  file.path(tables, "prereview_paired_bootstrap_summary.csv")
)
if (!all(bootstrap_summary$minimum_950_pass)) {
  stop("At least one paired bootstrap comparison failed the 950-fit gate")
}
log_message("DONE complete paired bootstrap comparisons=",
            nrow(bootstrap_summary))

calendar_levels <- c(
  "pre_2020_certain", "crosses_2020_boundary", "year_2020_plus_certain"
)
a2[, calendar_sensitivity_group := factor(
  calendar_sensitivity_group, levels = calendar_levels
)]
calendar_specs <- c(
  original_order = "order_exposure",
  original_strict_administration = "admin_strict",
  original_broad_administration = "admin_broad",
  hospital_overlap_order = "hospital_order_exposure",
  hospital_overlap_strict_administration = "hospital_admin_strict"
)
calendar_effects <- list()
for (source in names(calendar_specs)) {
  exposure_col <- calendar_specs[[source]]
  for (group in calendar_levels) {
    d <- copy(a2[calendar_sensitivity_group == group])
    d[, exposure := as.integer(get(exposure_col))]
    fit <- tryCatch(coxph(
      Surv(followup_days, outcome) ~ exposure + age + gender +
        emergency_admission + anchor_era,
      data = d, ties = "efron"
    ), error = function(e) e)
    if (inherits(fit, "error") || !"exposure" %in% names(coef(fit))) {
      calendar_effects[[length(calendar_effects) + 1L]] <- data.table(
        exposure_source = source, calendar_sensitivity_group = group,
        patients_n = nrow(d), deaths_90d_n = sum(d$outcome),
        exposed_n = sum(d$exposure), effect = NA_real_, ci_low = NA_real_,
        ci_high = NA_real_, converged = FALSE,
        model_error = if (inherits(fit, "error")) conditionMessage(fit)
          else "Exposure coefficient absent"
      )
    } else {
      co <- summary(fit)$coefficients["exposure", ]
      se <- co[["se(coef)"]]
      calendar_effects[[length(calendar_effects) + 1L]] <- data.table(
        exposure_source = source, calendar_sensitivity_group = group,
        patients_n = nrow(d), deaths_90d_n = sum(d$outcome),
        exposed_n = sum(d$exposure), effect = exp(co[["coef"]]),
        ci_low = exp(co[["coef"]] - qnorm(0.975) * se),
        ci_high = exp(co[["coef"]] + qnorm(0.975) * se),
        converged = TRUE, model_error = NA_character_
      )
    }
  }
}
calendar_effects <- rbindlist(calendar_effects, fill = TRUE)
fwrite(
  calendar_effects,
  file.path(tables, "prereview_a2_calendar_stratum_effects.csv")
)

finished <- Sys.time()
manifest <- list(
  script = basename(script_path),
  script_sha256 = digest(file = script_path, algo = "sha256", serialize = FALSE),
  contract_sha256 = observed_contract_hash,
  started = format(started, "%Y-%m-%dT%H:%M:%S%z"),
  finished = format(finished, "%Y-%m-%dT%H:%M:%S%z"),
  elapsed_seconds = as.numeric(difftime(finished, started, units = "secs")),
  static_models_n = nrow(static_effects),
  static_models_converged_n = sum(static_effects$converged),
  time_varying_models_n = nrow(tv_effects),
  time_varying_models_converged_n = sum(tv_effects$converged),
  bootstrap_comparisons_n = nrow(bootstrap_summary),
  bootstrap_min_success_n = min(bootstrap_summary$successful_pairs_n),
  bootstrap_seed = 20260731L,
  raw_data_modified = FALSE
)
write_json(
  manifest,
  file.path(manifests, "29_prereview_upgrade_models_manifest.json"),
  pretty = TRUE, auto_unbox = TRUE
)
capture.output(
  sessionInfo(),
  file = file.path(environment, "R_sessionInfo_JAMIA_prereview_upgrade.txt")
)
log_message("COMPLETE elapsed_seconds=", round(manifest$elapsed_seconds, 3))
