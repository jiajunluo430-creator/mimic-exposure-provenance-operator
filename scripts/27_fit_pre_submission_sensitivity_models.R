suppressPackageStartupMessages({
  library(data.table)
  library(digest)
  library(jsonlite)
  library(lmtest)
  library(sandwich)
  library(survival)
})

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(script_arg) != 1L) stop("Cannot resolve script path")
script_path <- normalizePath(
  sub("^--file=", "", script_arg), winslash = "\\", mustWork = TRUE
)
project <- dirname(dirname(script_path))
root <- file.path(project, "outputs", "jamia_pre_submission_v1_0")
inputs <- file.path(root, "model_inputs")
tables <- file.path(root, "tables")
logs <- file.path(root, "logs")
manifests <- file.path(root, "manifests")
environment <- file.path(project, "environment")
dir.create(tables, recursive = TRUE, showWarnings = FALSE)
dir.create(logs, recursive = TRUE, showWarnings = FALSE)
dir.create(manifests, recursive = TRUE, showWarnings = FALSE)
dir.create(environment, recursive = TRUE, showWarnings = FALSE)

log_path <- file.path(logs, "27_fit_pre_submission_sensitivity_models.log")
started <- Sys.time()
log_message <- function(...) {
  line <- paste(
    format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
    paste0(..., collapse = ""), sep = "\t"
  )
  cat(line, "\n")
  cat(line, "\n", file = log_path, append = TRUE)
}

contract_hashes <- c(
  "jamia_pre_submission_sensitivity_addendum_v1.0.md" =
    "219b75672c02498b149ee33ae0c39202a9bb9d5819670dff352e9c6e96f164e6",
  "jamia_pre_submission_sensitivity_status_clarification_v1.0.md" =
    "8aedeec9bb44d7d6c1b47479e8a470161c2ab6ea0b082369dd6e9b6a1a1195b1",
  "jamia_pre_submission_nonconversion_timing_correction_v1.0.md" =
    "9569090405cac52ec1e9bbae742dac82e95bf8960ffae87be8cf79547327ba32"
)
contract_checks <- rbindlist(lapply(names(contract_hashes), function(name) {
  path <- file.path(project, "contracts", name)
  observed <- digest(file = path, algo = "sha256", serialize = FALSE)
  data.table(
    file = name, expected_sha256 = unname(contract_hashes[name]),
    observed_sha256 = observed,
    match = identical(tolower(observed), tolower(unname(contract_hashes[name])))
  )
}))
if (!all(contract_checks$match)) stop("Sensitivity contract hash mismatch")
fwrite(contract_checks, file.path(manifests, "27_contract_verification.csv"))
log_message("PASS sensitivity contract verification")

required <- c(
  a1 = file.path(inputs, "anchor_a1_operator_post.csv"),
  a2 = file.path(inputs, "anchor_a2_operator_post.csv"),
  primary = file.path(
    project, "outputs", "jamia_observability_v1_1", "model_inputs",
    "not_given_primary_corrected_post.csv"
  ),
  semantic = file.path(
    project, "outputs", "jamia_observability_v1_1", "model_inputs",
    "not_given_semantic_corrected_post.csv"
  )
)
if (!all(file.exists(required))) {
  stop("Missing model inputs: ", paste(names(required)[!file.exists(required)], collapse = ", "))
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
  if (anchor == "A1") {
    form <- if (enriched) {
      outcome ~ exposure + age + gender + emergency_admission + oasis_z +
        oasis_missing_components_n + first_day_mechvent +
        first_day_vasopressor + first_day_rrt
    } else {
      outcome ~ exposure + age + gender + emergency_admission
    }
    measure <- "OR"
  } else {
    form <- if (enriched) {
      Surv(followup_days, outcome) ~ exposure + age + gender +
        emergency_admission + anchor_era + oasis_z +
        oasis_missing_components_n + first_day_mechvent +
        first_day_vasopressor + first_day_rrt
    } else {
      Surv(followup_days, outcome) ~ exposure + age + gender +
        emergency_admission + anchor_era
    }
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
    return(failed_effect(anchor, operator, source, variant, measure, d, conditionMessage(fit)))
  }
  co <- summary(fit)$coefficients
  if (!"exposure" %in% rownames(co)) {
    return(failed_effect(anchor, operator, source, variant, measure, d, "Exposure coefficient absent"))
  }
  beta <- co["exposure", if (anchor == "A1") "Estimate" else "coef"]
  se_name <- if (anchor == "A1") "Std. Error" else "se(coef)"
  se <- co["exposure", se_name]
  p_name <- if (anchor == "A1") "Pr(>|z|)" else "Pr(>|z|)"
  data.table(
    anchor_id = anchor, operator = operator, exposure_source = source,
    model_variant = variant, effect_measure = measure,
    patients_n = uniqueN(d$subject_id), outcomes_n = sum(d$outcome),
    exposed_n = sum(d$exposure), beta = beta, standard_error = se,
    effect = exp(beta), ci_low = exp(beta - qnorm(0.975) * se),
    ci_high = exp(beta + qnorm(0.975) * se), p_value = co["exposure", p_name],
    converged = if (anchor == "A1") isTRUE(fit$converged) else TRUE,
    model_error = NA_character_
  )
}

static_specs <- list(
  list("A1", "strict_poe_identity", "order", "order_exposure"),
  list("A1", "strict_poe_identity", "administration", "admin_strict"),
  list("A1", "broad_class_window", "order", "order_exposure"),
  list("A1", "broad_class_window", "administration", "admin_broad"),
  list("A2", "strict_poe_identity", "order", "order_exposure"),
  list("A2", "strict_poe_identity", "administration", "admin_strict"),
  list("A2", "broad_class_window", "order", "order_exposure"),
  list("A2", "broad_class_window", "administration", "admin_broad")
)
log_message("START static strict/broad anchor models")
static_effects <- rbindlist(lapply(static_specs, function(s) {
  d <- if (s[[1]] == "A1") a1 else a2
  rbindlist(list(
    fit_static(d, s[[1]], s[[2]], s[[3]], s[[4]], FALSE),
    fit_static(d, s[[1]], s[[2]], s[[3]], s[[4]], TRUE)
  ))
}))
fwrite(static_effects, file.path(tables, "anchor_operator_model_effects.csv"))
log_message("DONE static anchor models rows=", nrow(static_effects))

make_timevarying <- function(data, onset_col) {
  d <- copy(data)
  d[, onset_days := as.numeric(get(onset_col)) / 24]
  pieces <- lapply(seq_len(nrow(d)), function(i) {
    row <- d[i]
    follow <- row$followup_days
    onset <- row$onset_days
    if (!is.finite(onset) || onset >= follow) {
      row[, `:=`(tstart = 0, tstop = follow, exposure = 0L, status = outcome)]
      return(row)
    }
    if (onset <= 0) {
      row[, `:=`(tstart = 0, tstop = follow, exposure = 1L, status = outcome)]
      return(row)
    }
    before <- copy(row)
    after <- copy(row)
    before[, `:=`(tstart = 0, tstop = onset, exposure = 0L, status = 0L)]
    after[, `:=`(tstart = onset, tstop = follow, exposure = 1L, status = outcome)]
    rbind(before, after)
  })
  rbindlist(pieces, use.names = TRUE, fill = TRUE)
}

fit_timevarying <- function(data, source, onset_col, enriched) {
  long <- make_timevarying(data, onset_col)
  variant <- if (enriched) "time_varying_enriched" else "time_varying_minimal"
  form <- if (enriched) {
    Surv(tstart, tstop, status) ~ exposure + age + gender +
      emergency_admission + anchor_era + oasis_z +
      oasis_missing_components_n + first_day_mechvent +
      first_day_vasopressor + first_day_rrt + cluster(subject_id)
  } else {
    Surv(tstart, tstop, status) ~ exposure + age + gender +
      emergency_admission + anchor_era + cluster(subject_id)
  }
  needed <- unique(c(all.vars(form), "subject_id", "status", "exposure"))
  long <- long[complete.cases(long[, ..needed]) & tstop > tstart]
  fit <- tryCatch(
    coxph(form, data = long, ties = "efron", x = TRUE),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    fake <- unique(long, by = "subject_id")
    fake[, outcome := status]
    return(failed_effect("A2", "time_varying", source, variant, "HR", fake, conditionMessage(fit)))
  }
  co <- summary(fit)$coefficients
  beta <- co["exposure", "coef"]
  se_col <- if ("robust se" %in% colnames(co)) "robust se" else "se(coef)"
  se <- co["exposure", se_col]
  data.table(
    anchor_id = "A2", operator = "time_varying", exposure_source = source,
    model_variant = variant, effect_measure = "HR",
    patients_n = uniqueN(long$subject_id), outcomes_n = sum(long$status),
    exposed_n = uniqueN(long[exposure == 1, subject_id]), beta = beta,
    standard_error = se, effect = exp(beta),
    ci_low = exp(beta - qnorm(0.975) * se),
    ci_high = exp(beta + qnorm(0.975) * se),
    p_value = co["exposure", "Pr(>|z|)"], converged = TRUE,
    model_error = NA_character_
  )
}

tv_specs <- list(
  list("order", "order_onset_hours"),
  list("strict_administration", "strict_admin_onset_hours"),
  list("broad_administration", "broad_admin_onset_hours")
)
log_message("START A2 time-varying models")
tv_effects <- rbindlist(lapply(tv_specs, function(s) {
  rbindlist(list(
    fit_timevarying(a2, s[[1]], s[[2]], FALSE),
    fit_timevarying(a2, s[[1]], s[[2]], TRUE)
  ))
}))
fwrite(tv_effects, file.path(tables, "a2_time_varying_effects.csv"))
log_message("DONE A2 time-varying models rows=", nrow(tv_effects))

fit_concordant <- function(data, anchor, operator, admin_col) {
  d <- copy(data)[order_exposure == get(admin_col)]
  d[, exposure := order_exposure]
  if (anchor == "A1") {
    form <- outcome ~ exposure + age + gender + emergency_admission
    fit <- tryCatch(glm(form, data = d, family = binomial()), error = function(e) e)
    measure <- "OR"
  } else {
    form <- Surv(followup_days, outcome) ~ exposure + age + gender +
      emergency_admission + anchor_era
    fit <- tryCatch(coxph(form, data = d, ties = "efron"), error = function(e) e)
    measure <- "HR"
  }
  if (inherits(fit, "error")) {
    return(failed_effect(anchor, operator, "common_concordant", "concordant_minimal", measure, d, conditionMessage(fit)))
  }
  co <- summary(fit)$coefficients
  beta <- co["exposure", if (anchor == "A1") "Estimate" else "coef"]
  se <- co["exposure", if (anchor == "A1") "Std. Error" else "se(coef)"]
  data.table(
    anchor_id = anchor, operator = operator,
    exposure_source = "common_concordant", model_variant = "concordant_minimal",
    effect_measure = measure, patients_n = nrow(d), outcomes_n = sum(d$outcome),
    exposed_n = sum(d$exposure), beta = beta, standard_error = se,
    effect = exp(beta), ci_low = exp(beta - qnorm(0.975) * se),
    ci_high = exp(beta + qnorm(0.975) * se),
    p_value = co["exposure", "Pr(>|z|)"], converged = TRUE,
    model_error = NA_character_
  )
}
concordant <- rbindlist(list(
  fit_concordant(a1, "A1", "strict_poe_identity", "admin_strict"),
  fit_concordant(a1, "A1", "broad_class_window", "admin_broad"),
  fit_concordant(a2, "A2", "strict_poe_identity", "admin_strict"),
  fit_concordant(a2, "A2", "broad_class_window", "admin_broad")
))
fwrite(concordant, file.path(tables, "concordant_subset_effects.csv"))

bootstrap_glm_pair <- function(data, replicate_n = 1000L, seed = 20260731L) {
  d <- copy(data)
  needed <- c("subject_id", "outcome", "order_exposure", "admin_strict", "age", "gender", "emergency_admission")
  d <- d[complete.cases(d[, ..needed])]
  y <- d$outcome
  x_order <- model.matrix(~ order_exposure + age + gender + emergency_admission, d)
  x_admin <- model.matrix(~ admin_strict + age + gender + emergency_admission, d)
  colnames(x_order)[colnames(x_order) == "order_exposure"] <- "exposure"
  colnames(x_admin)[colnames(x_admin) == "admin_strict"] <- "exposure"
  set.seed(seed)
  rows <- vector("list", replicate_n)
  for (b in seq_len(replicate_n)) {
    w <- tabulate(sample.int(nrow(d), nrow(d), replace = TRUE), nbins = nrow(d))
    bo <- tryCatch(unname(coef(glm.fit(x_order, y, weights = w, family = binomial()))["exposure"]), error = function(e) NA_real_)
    ba <- tryCatch(unname(coef(glm.fit(x_admin, y, weights = w, family = binomial()))["exposure"]), error = function(e) NA_real_)
    rows[[b]] <- data.table(
      comparison = "A1_primary_strict_static", replicate = b,
      beta_order = bo, beta_administration = ba,
      delta_log_effect = ba - bo,
      success = is.finite(bo) && is.finite(ba)
    )
  }
  rbindlist(rows)
}

bootstrap_static_cox_pair <- function(data, replicate_n = 1000L, seed = 20260731L) {
  d <- copy(data)
  needed <- c("subject_id", "followup_days", "outcome", "order_exposure", "admin_broad", "age", "gender", "emergency_admission", "anchor_era")
  d <- d[complete.cases(d[, ..needed])]
  set.seed(seed)
  rows <- vector("list", replicate_n)
  for (b in seq_len(replicate_n)) {
    w <- tabulate(sample.int(nrow(d), nrow(d), replace = TRUE), nbins = nrow(d))
    keep <- w > 0
    bo <- tryCatch(coef(coxph(
      Surv(followup_days, outcome) ~ order_exposure + age + gender +
        emergency_admission + anchor_era,
      data = d[keep], weights = w[keep], ties = "efron", robust = FALSE
    ))[["order_exposure"]], error = function(e) NA_real_)
    ba <- tryCatch(coef(coxph(
      Surv(followup_days, outcome) ~ admin_broad + age + gender +
        emergency_admission + anchor_era,
      data = d[keep], weights = w[keep], ties = "efron", robust = FALSE
    ))[["admin_broad"]], error = function(e) NA_real_)
    rows[[b]] <- data.table(
      comparison = "A2_primary_broad_static", replicate = b,
      beta_order = bo, beta_administration = ba,
      delta_log_effect = ba - bo,
      success = is.finite(bo) && is.finite(ba)
    )
  }
  rbindlist(rows)
}

bootstrap_tv_cox_pair <- function(data, replicate_n = 1000L, seed = 20260731L) {
  needed <- c("subject_id", "followup_days", "outcome", "age", "gender", "emergency_admission", "anchor_era")
  d <- copy(data)[complete.cases(data[, ..needed])]
  order_long <- make_timevarying(d, "order_onset_hours")
  admin_long <- make_timevarying(d, "broad_admin_onset_hours")
  ids <- d$subject_id
  set.seed(seed)
  rows <- vector("list", replicate_n)
  for (b in seq_len(replicate_n)) {
    counts <- tabulate(sample.int(length(ids), length(ids), replace = TRUE), nbins = length(ids))
    names(counts) <- as.character(ids)
    wo <- unname(counts[as.character(order_long$subject_id)])
    wa <- unname(counts[as.character(admin_long$subject_id)])
    keep_o <- wo > 0
    keep_a <- wa > 0
    bo <- tryCatch(coef(coxph(
      Surv(tstart, tstop, status) ~ exposure + age + gender +
        emergency_admission + anchor_era,
      data = order_long[keep_o], weights = wo[keep_o], ties = "efron",
      robust = FALSE
    ))[["exposure"]], error = function(e) NA_real_)
    ba <- tryCatch(coef(coxph(
      Surv(tstart, tstop, status) ~ exposure + age + gender +
        emergency_admission + anchor_era,
      data = admin_long[keep_a], weights = wa[keep_a], ties = "efron",
      robust = FALSE
    ))[["exposure"]], error = function(e) NA_real_)
    rows[[b]] <- data.table(
      comparison = "A2_broad_time_varying", replicate = b,
      beta_order = bo, beta_administration = ba,
      delta_log_effect = ba - bo,
      success = is.finite(bo) && is.finite(ba)
    )
  }
  rbindlist(rows)
}

log_message("START 1000 paired subject bootstrap replicates per comparison")
boot_a1_path <- file.path(tables, "bootstrap_checkpoint_a1_primary_strict_static.csv")
boot_a2_path <- file.path(tables, "bootstrap_checkpoint_a2_primary_broad_static.csv")
boot_tv_path <- file.path(tables, "bootstrap_checkpoint_a2_broad_time_varying.csv")
boot_a1 <- if (file.exists(boot_a1_path)) fread(boot_a1_path) else bootstrap_glm_pair(a1)
if (nrow(boot_a1) != 1000L) stop("Invalid A1 bootstrap checkpoint")
fwrite(boot_a1, boot_a1_path)
log_message("CHECKPOINT bootstrap A1 success=", sum(boot_a1$success))
boot_a2 <- if (file.exists(boot_a2_path)) fread(boot_a2_path) else bootstrap_static_cox_pair(a2)
if (nrow(boot_a2) != 1000L) stop("Invalid A2 static bootstrap checkpoint")
fwrite(boot_a2, boot_a2_path)
log_message("CHECKPOINT bootstrap A2 static success=", sum(boot_a2$success))
boot_tv <- if (file.exists(boot_tv_path)) fread(boot_tv_path) else bootstrap_tv_cox_pair(a2)
if (nrow(boot_tv) != 1000L) stop("Invalid A2 time-varying bootstrap checkpoint")
fwrite(boot_tv, boot_tv_path)
log_message("CHECKPOINT bootstrap A2 time-varying success=", sum(boot_tv$success))
bootstrap_replicates <- rbindlist(list(boot_a1, boot_a2, boot_tv))
fwrite(bootstrap_replicates, file.path(tables, "paired_bootstrap_delta_log_effect_replicates.csv"))

observed_pairs <- rbindlist(list(
  static_effects[anchor_id == "A1" & operator == "strict_poe_identity" & model_variant == "published_style_minimal",
    .(comparison = "A1_primary_strict_static", exposure_source, beta)],
  static_effects[anchor_id == "A2" & operator == "broad_class_window" & model_variant == "published_style_minimal",
    .(comparison = "A2_primary_broad_static", exposure_source, beta)],
  tv_effects[model_variant == "time_varying_minimal" & exposure_source %in% c("order", "broad_administration"),
    .(comparison = "A2_broad_time_varying",
      exposure_source = fifelse(exposure_source == "broad_administration", "administration", exposure_source), beta)]
))
observed_wide <- dcast(observed_pairs, comparison ~ exposure_source, value.var = "beta")
observed_wide[, `:=`(
  observed_delta_log_effect = administration - order,
  observed_relative_log_change_pct = 100 * abs((administration - order) / order)
)]
bootstrap_summary <- bootstrap_replicates[, .(
  replicates_n = .N, successful_pairs_n = sum(success),
  failed_pairs_n = sum(!success),
  delta_ci_low = quantile(delta_log_effect[success], 0.025, na.rm = TRUE),
  delta_ci_high = quantile(delta_log_effect[success], 0.975, na.rm = TRUE)
), by = comparison]
bootstrap_summary <- merge(bootstrap_summary, observed_wide, by = "comparison", all.x = TRUE)
bootstrap_summary[, minimum_950_pass := successful_pairs_n >= 950L]
fwrite(bootstrap_summary, file.path(tables, "paired_bootstrap_delta_log_effect_summary.csv"))
if (!all(bootstrap_summary$minimum_950_pass)) stop("Paired bootstrap success threshold failed")
log_message("DONE paired bootstrap")

calendar_levels <- c("pre_2020_certain", "crosses_2020_boundary", "year_2020_plus_certain")
a2[, calendar_sensitivity_group := factor(calendar_sensitivity_group, levels = calendar_levels)]
calendar_counts <- a2[, .(
  patients_n = .N, deaths_90d_n = sum(outcome),
  death_90d_pct = 100 * mean(outcome)
), by = calendar_sensitivity_group]
fwrite(calendar_counts, file.path(tables, "a2_calendar_group_counts.csv"))

calendar_sources <- c(
  order = "order_exposure",
  strict_administration = "admin_strict",
  broad_administration = "admin_broad"
)
calendar_effects <- list()
calendar_interactions <- list()
for (source in names(calendar_sources)) {
  exposure_col <- calendar_sources[[source]]
  for (group in calendar_levels) {
    d <- copy(a2[calendar_sensitivity_group == group])
    d[, exposure := get(exposure_col)]
    fit <- tryCatch(coxph(
      Surv(followup_days, outcome) ~ exposure + age + gender +
        emergency_admission + anchor_era,
      data = d, ties = "efron"
    ), error = function(e) e)
    if (inherits(fit, "error") || !"exposure" %in% names(coef(fit))) {
      calendar_effects[[length(calendar_effects) + 1L]] <- data.table(
        exposure_source = source, calendar_sensitivity_group = group,
        patients_n = nrow(d), deaths_90d_n = sum(d$outcome),
        exposed_n = sum(d$exposure), beta = NA_real_, effect = NA_real_,
        ci_low = NA_real_, ci_high = NA_real_, p_value = NA_real_,
        converged = FALSE,
        model_error = if (inherits(fit, "error")) conditionMessage(fit) else "Exposure coefficient absent"
      )
    } else {
      co <- summary(fit)$coefficients["exposure", ]
      se <- co[["se(coef)"]]
      calendar_effects[[length(calendar_effects) + 1L]] <- data.table(
        exposure_source = source, calendar_sensitivity_group = group,
        patients_n = nrow(d), deaths_90d_n = sum(d$outcome),
        exposed_n = sum(d$exposure), beta = co[["coef"]],
        effect = exp(co[["coef"]]),
        ci_low = exp(co[["coef"]] - qnorm(0.975) * se),
        ci_high = exp(co[["coef"]] + qnorm(0.975) * se),
        p_value = co[["Pr(>|z|)"]], converged = TRUE,
        model_error = NA_character_
      )
    }
  }
  d <- copy(a2)
  d[, exposure := get(exposure_col)]
  base_fit <- tryCatch(coxph(
    Surv(followup_days, outcome) ~ exposure + calendar_sensitivity_group +
      age + gender + emergency_admission + anchor_era,
    data = d, ties = "efron"
  ), error = function(e) e)
  int_fit <- tryCatch(coxph(
    Surv(followup_days, outcome) ~ exposure * calendar_sensitivity_group +
      age + gender + emergency_admission + anchor_era,
    data = d, ties = "efron"
  ), error = function(e) e)
  if (!inherits(base_fit, "error") && !inherits(int_fit, "error")) {
    lr <- anova(base_fit, int_fit, test = "LRT")
    p_col <- grep("P", colnames(lr), value = TRUE)[1]
    co <- summary(int_fit)$coefficients
    terms <- rownames(co)[grepl("exposure.*calendar_sensitivity_group", rownames(co))]
    calendar_interactions[[length(calendar_interactions) + 1L]] <- rbindlist(list(
      data.table(
        exposure_source = source, term = terms,
        beta = co[terms, "coef"], standard_error = co[terms, "se(coef)"],
        p_value = co[terms, "Pr(>|z|)"], joint_lrt_p_value = NA_real_,
        converged = TRUE, model_error = NA_character_
      ),
      data.table(
        exposure_source = source, term = "joint_exposure_by_calendar_interaction",
        beta = NA_real_, standard_error = NA_real_, p_value = NA_real_,
        joint_lrt_p_value = as.numeric(lr[2, p_col]), converged = TRUE,
        model_error = NA_character_
      )
    ), use.names = TRUE, fill = TRUE)
  } else {
    calendar_interactions[[length(calendar_interactions) + 1L]] <- data.table(
      exposure_source = source, term = "joint_exposure_by_calendar_interaction",
      beta = NA_real_, standard_error = NA_real_, p_value = NA_real_,
      joint_lrt_p_value = NA_real_, converged = FALSE,
      model_error = paste(
        if (inherits(base_fit, "error")) conditionMessage(base_fit) else "",
        if (inherits(int_fit, "error")) conditionMessage(int_fit) else ""
      )
    )
  }
}
calendar_effects <- rbindlist(calendar_effects, fill = TRUE)
calendar_interactions <- rbindlist(calendar_interactions, fill = TRUE)
fwrite(calendar_effects, file.path(tables, "a2_calendar_sensitivity_effects.csv"))
fwrite(calendar_interactions, file.path(tables, "a2_calendar_interactions.csv"))

weighted_sd <- function(x, w) {
  ok <- is.finite(x) & is.finite(w) & w > 0
  x <- x[ok]; w <- w[ok]
  if (length(x) < 2L || sum(w) <= 1) return(NA_real_)
  mu <- sum(w * x) / sum(w)
  sqrt(sum(w * (x - mu)^2) / (sum(w) - 1))
}
locked_terms <- c(
  "oasis_z", "shiftnight_1900_0659", "invasive_ventilation_active",
  "vasopressor_active", "rrt_active"
)

fit_not_given_class <- function(path, mapping, class_name) {
  d <- fread(path, na.strings = c("", "NA"))[drug_class == class_name]
  d[, `:=`(
    gender = safe_relevel(gender, "F"),
    shift = safe_relevel(shift, "day_0700_1859"),
    first_careunit = factor(first_careunit),
    anchor_era = factor(anchor_era),
    total_n = not_given_n + given_n
  )]
  mu <- weighted.mean(d$oasis, d$total_n, na.rm = TRUE)
  sdev <- weighted_sd(d$oasis, d$total_n)
  d[, oasis_z := (oasis - mu) / sdev]
  form <- cbind(not_given_n, given_n) ~ oasis_z +
    oasis_missing_components_n + shift + invasive_ventilation_active +
    vasopressor_active + rrt_active + age_at_icu + gender +
    emergency_admission + first_careunit + anchor_era
  needed <- unique(c(all.vars(form), "stay_id", "total_n"))
  d <- d[complete.cases(d[, ..needed])]
  fit <- tryCatch(glm(form, data = d, family = binomial()), error = function(e) e)
  if (inherits(fit, "error")) {
    return(list(
      coefficients = data.table(), correlates = data.table(),
      status = data.table(
        event_mapping = mapping, drug_class = class_name, converged = FALSE,
        rows_n = nrow(d), stays_n = uniqueN(d$stay_id),
        decision_events_n = sum(d$total_n), model_error = conditionMessage(fit)
      )
    ))
  }
  robust <- tryCatch(vcovCL(fit, cluster = d$stay_id, type = "HC0"), error = function(e) e)
  if (inherits(robust, "error")) {
    return(list(
      coefficients = data.table(), correlates = data.table(),
      status = data.table(
        event_mapping = mapping, drug_class = class_name, converged = FALSE,
        rows_n = nrow(d), stays_n = uniqueN(d$stay_id),
        decision_events_n = sum(d$total_n), model_error = conditionMessage(robust)
      )
    ))
  }
  test <- coeftest(fit, vcov. = robust)
  coefficients <- data.table(
    event_mapping = mapping, drug_class = class_name,
    term = rownames(test), beta = test[, "Estimate"],
    cluster_robust_se = test[, "Std. Error"],
    z_value = test[, "z value"], p_value = test[, "Pr(>|z|)"]
  )
  coefficients[, `:=`(
    adjusted_or = exp(beta),
    ci_low = exp(beta - qnorm(0.975) * cluster_robust_se),
    ci_high = exp(beta + qnorm(0.975) * cluster_robust_se)
  )]
  correlates <- coefficients[term %in% locked_terms]
  correlates[, bh_q_value := p.adjust(p_value, method = "BH")]
  list(
    coefficients = coefficients, correlates = correlates,
    status = data.table(
      event_mapping = mapping, drug_class = class_name,
      converged = isTRUE(fit$converged), rows_n = nrow(d),
      stays_n = uniqueN(d$stay_id), decision_events_n = sum(d$total_n),
      oasis_event_weighted_mean = mu, oasis_event_weighted_sd = sdev,
      model_error = NA_character_
    )
  )
}

classes <- sort(unique(fread(required[["primary"]], select = "drug_class")$drug_class))
if (length(classes) != 6L) stop("Expected six frozen drug classes")
not_given_fits <- list()
for (mapping in c("frozen_primary", "audit_semantic_sensitivity")) {
  path <- if (mapping == "frozen_primary") required[["primary"]] else required[["semantic"]]
  for (class_name in classes) {
    log_message("START class-specific not-given mapping=", mapping, " class=", class_name)
    not_given_fits[[paste(mapping, class_name)]] <- fit_not_given_class(path, mapping, class_name)
  }
}
not_given_coefficients <- rbindlist(lapply(not_given_fits, `[[`, "coefficients"), fill = TRUE)
not_given_correlates <- rbindlist(lapply(not_given_fits, `[[`, "correlates"), fill = TRUE)
not_given_status <- rbindlist(lapply(not_given_fits, `[[`, "status"), fill = TRUE)
fwrite(not_given_coefficients, file.path(tables, "not_given_class_specific_all_coefficients.csv"))
fwrite(not_given_correlates, file.path(tables, "not_given_class_specific_prespecified_correlates.csv"))
fwrite(not_given_status, file.path(tables, "not_given_class_specific_model_status.csv"))
log_message("DONE class-specific not-given models converged=", sum(not_given_status$converged), "/", nrow(not_given_status))

capture.output(sessionInfo(), file = file.path(environment, "sessionInfo_jamia_pre_submission_models.txt"))
finished <- Sys.time()
manifest <- list(
  status = "PASS",
  script = script_path,
  script_sha256 = digest(file = script_path, algo = "sha256", serialize = FALSE),
  started = format(started, "%Y-%m-%dT%H:%M:%S%z"),
  finished = format(finished, "%Y-%m-%dT%H:%M:%S%z"),
  elapsed_seconds = as.numeric(difftime(finished, started, units = "secs")),
  static_models_n = nrow(static_effects),
  static_models_converged_n = sum(static_effects$converged),
  time_varying_models_n = nrow(tv_effects),
  time_varying_models_converged_n = sum(tv_effects$converged),
  bootstrap_comparisons_n = nrow(bootstrap_summary),
  bootstrap_min_success_n = min(bootstrap_summary$successful_pairs_n),
  class_specific_models_n = nrow(not_given_status),
  class_specific_models_converged_n = sum(not_given_status$converged),
  session_info = file.path(environment, "sessionInfo_jamia_pre_submission_models.txt"),
  contract_checks = contract_checks
)
write_json(
  manifest,
  file.path(manifests, "27_pre_submission_sensitivity_models_manifest.json"),
  pretty = TRUE, auto_unbox = TRUE, na = "null"
)
log_message(
  "PASS pre-submission sensitivity models elapsed_seconds=",
  round(as.numeric(difftime(finished, started, units = "secs")), 1)
)
