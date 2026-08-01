from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "outputs" / "jamia_prereview_upgrade_v1_0"
TABLES = OUTPUT / "tables"
LOGS = OUTPUT / "logs"
MANIFESTS = OUTPUT / "manifests"
RAW = OUTPUT / "literature_raw"
ENVIRONMENT = PROJECT / "environment"
CONTRACT = (
    PROJECT
    / "contracts"
    / "jamia_prereview_upgrade_addendum_v1.0_2026-07-31.md"
)
EXPECTED_CONTRACT_SHA256 = (
    "0a851a99c9176c16deda2cde9e30fded7f2b5131a5a3f64ac7f050ebd8f81d9d"
)
QUERY = (
    '("MIMIC-IV"[Title/Abstract]) AND '
    '(drug[Title/Abstract] OR medication[Title/Abstract] OR '
    'pharmaco*[Title/Abstract] OR antibiotic*[Title/Abstract] OR '
    'insulin[Title/Abstract] OR anticoag*[Title/Abstract] OR '
    'heparin[Title/Abstract] OR "proton pump"[Title/Abstract] OR '
    'PPI[Title/Abstract])'
)
QUERY_DATE = "2026-07-31"
SEED = 20260731
FULL_TEXT_RETRIEVAL_N = 240
USER_AGENT = "N1-MIMIC-medication-provenance-audit/1.0"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MIN_SECONDS_BETWEEN_CALLS = 0.34
STARTED = time.time()


for directory in (TABLES, LOGS, MANIFESTS, RAW, ENVIRONMENT):
    directory.mkdir(parents=True, exist_ok=True)

LOG_PATH = LOGS / "31_retrieve_published_operator_landscape.log"


def log(message: str) -> None:
    line = f"{datetime.now().astimezone().isoformat()}\t{message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def request_bytes(url: str, attempts: int = 5) -> tuple[int, bytes]:
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as error:
            if error.code in (429, 500, 502, 503, 504) and attempt < attempts:
                time.sleep(min(60, 2**attempt))
                continue
            return int(error.code), str(error).encode("utf-8")
        except Exception as error:
            if attempt < attempts:
                time.sleep(min(30, 2**attempt))
                continue
            return 0, repr(error).encode("utf-8")
    raise AssertionError("unreachable")


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def pubmed_metadata(xml_bytes: bytes) -> list[dict[str, object]]:
    root = ET.fromstring(xml_bytes)
    records: list[dict[str, object]] = []
    for article in root.findall(".//PubmedArticle"):
        citation = article.find("MedlineCitation")
        if citation is None:
            continue
        article_node = citation.find("Article")
        if article_node is None:
            continue
        pmid = element_text(citation.find("PMID"))
        title = element_text(article_node.find("ArticleTitle"))
        abstract = " ".join(
            element_text(node)
            for node in article_node.findall("Abstract/AbstractText")
        ).strip()
        journal = element_text(article_node.find("Journal/Title"))
        language = "|".join(
            element_text(node) for node in article_node.findall("Language")
        )
        publication_types = "|".join(
            element_text(node)
            for node in article_node.findall("PublicationTypeList/PublicationType")
        )
        year = element_text(
            article_node.find("Journal/JournalIssue/PubDate/Year")
        ) or element_text(
            article_node.find("Journal/JournalIssue/PubDate/MedlineDate")
        )
        identifiers: dict[str, str] = {}
        for identifier in article.findall("PubmedData/ArticleIdList/ArticleId"):
            kind = identifier.attrib.get("IdType", "")
            identifiers[kind] = element_text(identifier)
        records.append(
            {
                "pmid": pmid,
                "pmcid": identifiers.get("pmc", ""),
                "doi": identifiers.get("doi", ""),
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "publication_year": year,
                "language": language,
                "publication_types": publication_types,
            }
        )
    return records


def section_records(root: ET.Element) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    for section in root.findall(".//body//sec"):
        title = element_text(section.find("title"))
        paragraphs = [element_text(p) for p in section.findall(".//p")]
        text = " ".join(value for value in paragraphs if value)
        if text:
            records.append((title, text))
    return records


def operator_context(sections: list[tuple[str, str]]) -> str:
    patterns = re.compile(
        r"prescription|pharmacy|\bpoe\b|poe_id|\bemar\b|inputevents|"
        r"chartevents|medication|drug exposure|administration|administered|"
        r"treatment group|within \d+ (?:hour|day)|ICU admission|dose|route",
        flags=re.IGNORECASE,
    )
    contexts: list[str] = []
    for title, text in sections:
        title_lower = title.lower()
        if not any(
            token in title_lower
            for token in (
                "method",
                "material",
                "cohort",
                "exposure",
                "treatment",
                "definition",
                "data",
                "variable",
            )
        ):
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            if patterns.search(sentence):
                contexts.append(sentence[:1500])
            if len(contexts) >= 30:
                break
        if len(contexts) >= 30:
            break
    return "\n".join(contexts)


def heuristic_codes(title: str, abstract: str, context: str) -> dict[str, object]:
    combined = " ".join([title, abstract, context]).lower()
    likely_outcome = bool(
        re.search(
            r"mortality|death|survival|outcome|length of stay|bleed|"
            r"acute kidney|renal|delirium|ventilat|infection|readmission|"
            r"adverse|complication",
            combined,
        )
    )
    likely_exposure = bool(
        re.search(
            r"exposure|treatment|therapy|received|use of|administration|"
            r"administered|antibiotic|insulin|heparin|anticoagul|"
            r"proton pump|ppi|drug",
            combined,
        )
    )
    prediction_only_risk = bool(
        re.search(r"prediction model|machine learning|deep learning|nomogram", combined)
    ) and not bool(re.search(r"propensity|hazard ratio|odds ratio|cox", combined))
    sources: list[str] = []
    for label, pattern in (
        ("eMAR", r"\bemar\b"),
        ("prescriptions", r"\bprescriptions?\b"),
        ("POE", r"\bpoe(?:_id)?\b"),
        ("pharmacy", r"\bpharmacy\b"),
        ("inputevents", r"\binputevents\b"),
        ("chartevents", r"\bchartevents\b"),
    ):
        if re.search(pattern, context, flags=re.IGNORECASE):
            sources.append(label)
    identity_reported = bool(
        re.search(r"poe_id|pharmacy_id|emar_id|linked? .*order", context,
                  flags=re.IGNORECASE)
    )
    time_reported = bool(
        re.search(
            r"within \d+ (?:hour|day)|first \d+ (?:hour|day)|"
            r"after ICU admission|from ICU admission|during (?:the )?ICU stay|"
            r"before ICU admission",
            context,
            flags=re.IGNORECASE,
        )
    )
    semantic_reported = bool(
        re.search(
            r"event_txt|not given|held|refused|flushed|administered event|"
            r"complete_dose_not_given",
            context,
            flags=re.IGNORECASE,
        )
    )
    dose_route_reported = bool(
        re.search(r"\bdose\b|\broute\b|subcutaneous|intravenous", context,
                  flags=re.IGNORECASE)
    )
    return {
        "auto_likely_exposure_outcome": likely_outcome
        and likely_exposure
        and not prediction_only_risk,
        "auto_prediction_only_risk": prediction_only_risk,
        "auto_source_tables": "|".join(sources) if sources else "not reported",
        "auto_identity_rule_reported": identity_reported,
        "auto_time_origin_or_window_reported": time_reported,
        "auto_event_semantics_reported": semantic_reported,
        "auto_dose_or_route_reported": dose_route_reported,
    }


def main() -> None:
    observed_contract_hash = sha256(CONTRACT)
    if observed_contract_hash != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError("Prereview-upgrade contract hash mismatch")
    params = {
        "db": "pubmed",
        "term": QUERY,
        "retmax": "1000",
        "retmode": "json",
        "datetype": "pdat",
        "maxdate": "2026/07/31",
    }
    esearch_url = BASE + "/esearch.fcgi?" + urllib.parse.urlencode(params)
    status, payload = request_bytes(esearch_url)
    if status != 200:
        raise RuntimeError(f"PubMed ESearch failed: HTTP {status}")
    esearch = json.loads(payload.decode("utf-8"))["esearchresult"]
    pmids = list(esearch["idlist"])
    log(f"PUBMED query_count={esearch['count']} ids_retrieved={len(pmids)}")
    (RAW / "pubmed_esearch.json").write_text(
        json.dumps(
            {
                "query_date": QUERY_DATE,
                "query": QUERY,
                "endpoint": esearch_url,
                "http_status": status,
                "response": {**esearch, "idlist": pmids},
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    metadata_records: list[dict[str, object]] = []
    for start in range(0, len(pmids), 200):
        batch = pmids[start : start + 200]
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
        }
        fetch_url = BASE + "/efetch.fcgi?" + urllib.parse.urlencode(fetch_params)
        status, xml_bytes = request_bytes(fetch_url)
        if status != 200:
            raise RuntimeError(f"PubMed EFetch failed: HTTP {status}")
        metadata_records.extend(pubmed_metadata(xml_bytes))
        log(
            f"CHECKPOINT PubMed metadata={len(metadata_records)}/{len(pmids)}"
        )
        time.sleep(MIN_SECONDS_BETWEEN_CALLS)
    metadata = pd.DataFrame(metadata_records)
    metadata["query_date"] = QUERY_DATE
    metadata["query"] = QUERY
    metadata.to_csv(
        TABLES / "published_operator_pubmed_search_results.csv",
        index=False,
        encoding="utf-8-sig",
    )

    open_candidates = metadata.loc[
        metadata["pmcid"].fillna("").ne("")
        & metadata["language"].str.contains("eng", case=False, na=False)
        & ~metadata["publication_types"].str.contains(
            "Review|Meta-Analysis|Editorial|Letter|Protocol", case=False,
            na=False,
        )
    ].copy()
    records = open_candidates.to_dict("records")
    random.Random(SEED).shuffle(records)
    records = records[: min(FULL_TEXT_RETRIEVAL_N, len(records))]
    log(
        f"OPEN_FULL_TEXT pool={len(open_candidates)} retrieval_target={len(records)}"
    )

    candidate_rows: list[dict[str, object]] = []
    context_path = RAW / "operator_contexts.jsonl"
    last_call = 0.0
    with context_path.open("w", encoding="utf-8") as context_handle:
        for rank, record in enumerate(records, start=1):
            xml_path = RAW / f"{record['pmcid']}.xml"
            if xml_path.exists():
                status, xml_bytes = 200, xml_path.read_bytes()
            else:
                wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - last_call)
                if wait > 0:
                    time.sleep(wait)
                fetch_params = {
                    "db": "pmc",
                    "id": str(record["pmcid"]),
                    "retmode": "xml",
                }
                url = BASE + "/efetch.fcgi?" + urllib.parse.urlencode(fetch_params)
                status, xml_bytes = request_bytes(url)
                last_call = time.monotonic()
            context = ""
            retrieval_error = ""
            if status == 200:
                try:
                    root = ET.fromstring(xml_bytes)
                    sections = section_records(root)
                    context = operator_context(sections)
                    xml_path.write_bytes(xml_bytes)
                except Exception as error:
                    retrieval_error = repr(error)
            else:
                retrieval_error = f"HTTP {status}: {xml_bytes[:200]!r}"
            codes = heuristic_codes(
                str(record["title"]), str(record["abstract"]), context
            )
            candidate_rows.append(
                {
                    "random_rank": rank,
                    **record,
                    "full_text_http_status": status,
                    "full_text_retrieved": status == 200 and not retrieval_error,
                    "retrieval_error": retrieval_error,
                    **codes,
                }
            )
            context_handle.write(
                json.dumps(
                    {
                        "random_rank": rank,
                        "pmid": record["pmid"],
                        "pmcid": record["pmcid"],
                        "title": record["title"],
                        "operator_context": context,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            if rank % 20 == 0 or rank == len(records):
                log(f"CHECKPOINT PMC full_text={rank}/{len(records)}")

    candidates = pd.DataFrame(candidate_rows)
    candidates.to_csv(
        TABLES / "published_operator_randomized_open_fulltext_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    manifest = {
        "script_sha256": sha256(Path(__file__)),
        "contract_sha256": observed_contract_hash,
        "query": QUERY,
        "query_date": QUERY_DATE,
        "pubmed_query_count": int(esearch["count"]),
        "pubmed_records_retrieved": len(metadata),
        "eligible_open_fulltext_pool_before_content_screen": len(open_candidates),
        "random_seed": SEED,
        "fulltexts_requested": len(records),
        "fulltexts_retrieved": int(candidates["full_text_retrieved"].sum()),
        "elapsed_seconds": time.time() - STARTED,
    }
    (MANIFESTS / "31_published_operator_retrieval_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (ENVIRONMENT / "Python_sessionInfo_operator_landscape.txt").write_text(
        "\n".join(
            [
                f"timestamp={datetime.now().astimezone().isoformat()}",
                f"python={sys.version}",
                f"pandas={pd.__version__}",
                f"script_sha256={manifest['script_sha256']}",
                f"contract_sha256={observed_contract_hash}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    log(
        "COMPLETE "
        f"fulltexts={manifest['fulltexts_retrieved']}/{len(records)} "
        f"elapsed_seconds={time.time() - STARTED:.3f}"
    )


if __name__ == "__main__":
    main()
