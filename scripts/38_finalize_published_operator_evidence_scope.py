from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
PRIOR = PROJECT / "outputs" / "jamia_prereview_upgrade_v1_0"
OUTPUT = PROJECT / "outputs" / "jamia_residual_provenance_v1_0"
TABLES = OUTPUT / "tables"
LOGS = OUTPUT / "logs"
MANIFESTS = OUTPUT / "manifests"
SAMPLE = PRIOR / "tables" / "published_operator_landscape_sample.csv"
SCOPE = TABLES / "published_operator_evidence_scope.csv"
SUPPLEMENTS = TABLES / "published_operator_supplement_inventory.csv"
REPOSITORIES = TABLES / "published_operator_repository_inventory.csv"
SQL_TEXT = (
    OUTPUT
    / "literature_scope_text"
    / "PMC12513587__pone.0333795.s003.sql.txt"
)
ADDENDUM = (
    PROJECT
    / "contracts"
    / "jamia_residual_provenance_addendum_v1.0_2026-07-31.md"
)
CODEBOOK = (
    PROJECT
    / "contracts"
    / "published_operator_landscape_codebook_v1.0_2026-07-31.md"
)

EXPECTED = {
    ADDENDUM: "af533e4d3a9b636c368dc6c76cc3e3ea472c77f9884476520d341ae09575dcfd",
    CODEBOOK: "ecfab4f17c4c277c3cf0a26e4aecb4a9e6fae1193149ac687c599baf717bea53",
    SAMPLE: "69fc62e3ff0bf3f8f9eb626817a6342ebcfebf46f9ca11d7a7ed07418e407678",
}

for directory in (TABLES, LOGS, MANIFESTS):
    directory.mkdir(parents=True, exist_ok=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    for path, expected in EXPECTED.items():
        if sha256(path) != expected:
            raise RuntimeError(f"Frozen input hash mismatch: {path}")

    sample = pd.read_csv(SAMPLE)
    scope = pd.read_csv(SCOPE)
    supplements = pd.read_csv(SUPPLEMENTS)
    repositories = pd.read_csv(REPOSITORIES)
    if len(sample) != 40 or sample["pmcid"].nunique() != 40:
        raise RuntimeError("Sample cardinality failed")
    if len(scope) != 40 or scope["pmcid"].nunique() != 40:
        raise RuntimeError("Evidence-scope cardinality failed")
    if int(supplements["http_status"].eq(200).sum()) != 55:
        raise RuntimeError("Expected 55/56 supplement retrievals")
    if int(scope["supplement_status"].eq("retrieved_and_reviewed").sum()) != 28:
        raise RuntimeError("Expected complete supplement retrieval for 28 studies")
    article_repos = repositories.loc[~repositories["generic_repository"].astype(bool)]
    if len(article_repos) != 3 or not article_repos["http_status"].eq(200).all():
        raise RuntimeError("Article-specific repository scope failed")

    sql = SQL_TEXT.read_text(encoding="utf-8")
    required_sql_tokens = [
        "mimiciv_icu.inputevents",
        "ii.itemid = 225975",
        "sum(ii.amount)",
    ]
    if not all(token in sql for token in required_sql_tokens):
        raise RuntimeError("Supplementary SQL evidence gate failed")
    forbidden_operator_tokens = [
        "event_txt",
        "order by ii.starttime",
        "ii.starttime between",
        "ii.starttime >=",
        "ii.starttime <=",
    ]
    if any(token in sql.lower() for token in forbidden_operator_tokens):
        raise RuntimeError(
            "Supplementary SQL contains unexpected time/semantic operator; "
            "manual recoding required"
        )

    updated = sample.copy()
    target = updated["pmcid"].eq("PMC12513587")
    if int(target.sum()) != 1:
        raise RuntimeError("Target supplement study not unique")
    before = updated.loc[
        target,
        [
            "named_native_table_reported",
            "database_identity_rule_reported",
            "event_semantics_reported",
            "time_origin_and_window_reported",
            "fully_executable_exposure_operator",
        ],
    ].iloc[0]
    if bool(before["named_native_table_reported"]) or bool(
        before["database_identity_rule_reported"]
    ):
        raise RuntimeError("Unexpected baseline code for supplement-updated study")

    updated.loc[target, "named_native_table_reported"] = True
    updated.loc[target, "database_identity_rule_reported"] = True
    updated.loc[target, "source_evidence"] = (
        "supplementary SQL uses mimiciv_icu.inputevents for the heparin construct"
    )
    updated.loc[target, "identity_evidence"] = (
        "supplementary SQL specifies inputevents itemid 225975 and explicit "
        "exclusion itemids"
    )
    updated["fully_executable_exposure_operator"] = (
        updated["named_native_table_reported"].astype(bool)
        & updated["database_identity_rule_reported"].astype(bool)
        & updated["time_origin_and_window_reported"].astype(bool)
        & updated["event_semantics_reported"].astype(bool)
    )
    updated = updated.merge(
        scope[
            [
                "pmcid",
                "main_text_reviewed",
                "supplements_linked_n",
                "supplements_retrieved_n",
                "supplement_status",
                "article_specific_repositories_linked_n",
                "article_specific_repositories_retrieved_n",
                "article_specific_repo_status",
            ]
        ],
        on="pmcid",
        how="left",
        validate="one_to_one",
    )
    updated["coding_stage"] = "main_text_plus_linked_supplements_and_repositories"
    updated["primary_coders_n"] = 1
    updated["independent_second_coder_complete"] = False

    diff = pd.DataFrame(
        [
            {
                "pmcid": "PMC12513587",
                "field": "named_native_table_reported",
                "main_text_code": False,
                "expanded_evidence_code": True,
                "evidence_source": "pone.0333795.s003.sql",
                "evidence_summary": "supplement names mimiciv_icu.inputevents",
            },
            {
                "pmcid": "PMC12513587",
                "field": "database_identity_rule_reported",
                "main_text_code": False,
                "expanded_evidence_code": True,
                "evidence_source": "pone.0333795.s003.sql",
                "evidence_summary": "supplement specifies heparin itemid 225975 and exclusion itemids",
            },
        ]
    )

    dimensions = [
        ("Named native medication table/source", "named_native_table_reported"),
        ("Database-executable identity rule", "database_identity_rule_reported"),
        ("Time origin and exposure window", "time_origin_and_window_reported"),
        ("Native event-state semantics", "event_semantics_reported"),
        ("Dose or route constraint", "dose_or_route_reported"),
        ("Fully executable operator", "fully_executable_exposure_operator"),
    ]
    reporting = pd.DataFrame(
        [
            {
                "reporting_dimension": label,
                "reported_n": int(updated[column].astype(bool).sum()),
                "sample_n": 40,
                "reported_percent": 100.0
                * float(updated[column].astype(bool).sum())
                / 40.0,
                "evidence_scope": "main text, linked supplements, and article-specific repositories",
            }
            for label, column in dimensions
        ]
    )
    expected_counts = {
        "Named native medication table/source": 7,
        "Database-executable identity rule": 2,
        "Time origin and exposure window": 35,
        "Native event-state semantics": 0,
        "Dose or route constraint": 30,
        "Fully executable operator": 0,
    }
    observed_counts = dict(
        zip(reporting["reporting_dimension"], reporting["reported_n"])
    )
    if observed_counts != expected_counts:
        raise RuntimeError(
            f"Expanded evidence reporting counts differ: {observed_counts}"
        )

    source = (
        updated.groupby("source_layer", dropna=False)
        .size()
        .rename("n")
        .reset_index()
        .sort_values(["n", "source_layer"], ascending=[False, True])
    )
    source["percent"] = 100.0 * source["n"] / 40.0

    outputs = {
        "expanded_sample": TABLES / "published_operator_landscape_expanded_evidence_sample.csv",
        "expanded_reporting": TABLES / "published_operator_landscape_expanded_reporting_summary.csv",
        "expanded_source": TABLES / "published_operator_landscape_expanded_source_summary.csv",
        "coding_diff": TABLES / "published_operator_landscape_evidence_scope_coding_diff.csv",
    }
    updated.to_csv(outputs["expanded_sample"], index=False, encoding="utf-8-sig")
    reporting.to_csv(outputs["expanded_reporting"], index=False, encoding="utf-8-sig")
    source.to_csv(outputs["expanded_source"], index=False, encoding="utf-8-sig")
    diff.to_csv(outputs["coding_diff"], index=False, encoding="utf-8-sig")

    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "script": Path(__file__).name,
        "script_sha256": sha256(Path(__file__)),
        "sample_n": 40,
        "primary_coders_n": 1,
        "independent_second_coder_complete": False,
        "supplement_files_linked_n": len(supplements),
        "supplement_files_retrieved_n": int(
            supplements["http_status"].eq(200).sum()
        ),
        "article_specific_repositories_reviewed_n": len(article_repos),
        "coding_changes_n": len(diff),
        "updated_reporting_counts": expected_counts,
        "outputs": {
            name: {
                "path": str(path.relative_to(PROJECT)),
                "sha256": sha256(path),
            }
            for name, path in outputs.items()
        },
    }
    (MANIFESTS / "38_published_operator_expanded_evidence_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (LOGS / "38_finalize_published_operator_evidence_scope.log").write_text(
        "\n".join(
            [
                f"{manifest['created_at']}\tPASS expanded evidence recoding",
                "changed_studies=1",
                "changed_fields=2",
                "native_source=7/40",
                "identity_rule=2/40",
                "event_semantics=0/40",
                "fully_executable=0/40",
                "second_coder_complete=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(reporting.to_string(index=False), flush=True)
    print(diff.to_string(index=False), flush=True)
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
