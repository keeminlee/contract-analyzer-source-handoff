from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from tools.dynamic_chunker import build_chunks, rank_chunks
from tools.spine_resolver import resolve_spine

DOC_TYPES = ("nda", "msa", "credit_agreement", "loan_agreement")
MODES = ("overview", "precision")
PROFILES = ("classification_only", "obligation_probe", "playbook_diff")

_DOC_PATTERNS: dict[str, tuple[str, ...]] = {
    "nda": (
        r"\bnda\b",
        r"\bnon[- ]?disclosure\b",
        r"\bconfidential information\b",
        r"\bdisclosing party\b",
        r"\breceiving party\b",
    ),
    "msa": (
        r"\bmsa\b",
        r"\bmaster services? agreement\b",
        r"\bstatement of work\b",
        r"\bsow\b",
        r"\bservice levels?\b",
        r"\bchange order\b",
    ),
    "credit_agreement": (
        r"\bcredit agreement\b",
        r"\brevolving (?:credit )?facility\b",
        r"\bconditions precedent\b",
        r"\bfinancial covenants?\b",
        r"\bevents? of default\b",
        r"\bcross default\b",
        r"\badministrative agent\b",
        r"\bsecurity interest\b",
        r"\bcollateral\b",
    ),
    "loan_agreement": (
        r"\bloan agreement\b",
        r"\bterm loan\b",
        r"\bprincipal amount\b",
        r"\bamorti[sz]ation\b",
        r"\brepayment schedule\b",
        r"\bmaturity date\b",
        r"\bpromissory note\b",
        r"\binstallments?\b",
        r"\bguarant(?:y|ee)\b",
    ),
}

_QUERY_MODE_PATTERNS = {
    "overview": re.compile(r"\b(summary|summarize|overview|high[- ]?level|quick scan)\b", re.IGNORECASE),
    "precision": re.compile(
        r"\b(quote|citation|cite|span|compare|baseline|diff|deviation|gap|evidence|pinpoint)\b",
        re.IGNORECASE,
    ),
}

_QUERY_PROFILE_PATTERNS = {
    "classification_only": re.compile(r"\b(classify|what type|overview|summary)\b", re.IGNORECASE),
    "obligation_probe": re.compile(r"\b(obligation|shall|must|covenant|duty|payment)\b", re.IGNORECASE),
    "playbook_diff": re.compile(r"\b(compare|baseline|diff|deviation|risk|missing|required)\b", re.IGNORECASE),
}

_FINANCE_TERMS = re.compile(
    r"\b(borrower|lender|interest|principal|events? of default|covenant|collateral|security interest|acceleration)\b",
    re.IGNORECASE,
)


def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def _safe(text: str | None) -> str:
    return (text or "").strip()


def _select_doc_type(requested_doc_type: str, query: str, text: str) -> tuple[str, dict[str, float], list[str]]:
    reasons: list[str] = []
    normalized = requested_doc_type.lower()
    if normalized in DOC_TYPES:
        return normalized, {normalized: 1.0}, ["doc_type explicitly provided"]

    search_text = f"{query}\n{text}"
    scores: dict[str, float] = {doc_type: 0.0 for doc_type in DOC_TYPES}

    for doc_type, patterns in _DOC_PATTERNS.items():
        for pattern in patterns:
            hits = _count(pattern, search_text)
            if hits:
                scores[doc_type] += float(hits)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_doc, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if top_score == 0.0:
        reasons.append("no doc-type keywords found; defaulting to nda")
        return "nda", scores, reasons

    if top_doc in {"credit_agreement", "loan_agreement"} and abs(top_score - second_score) <= 1.0:
        credit_terms = _count(r"\b(conditions precedent|financial covenants?|administrative agent|revolving)\b", search_text)
        loan_terms = _count(r"\b(term loan|amortization|repayment schedule|maturity date|promissory note)\b", search_text)
        if credit_terms >= loan_terms:
            reasons.append("finance tie-breaker chose credit_agreement")
            return "credit_agreement", scores, reasons
        reasons.append("finance tie-breaker chose loan_agreement")
        return "loan_agreement", scores, reasons

    reasons.append(f"doc_type selected by keyword score ({top_doc}={top_score:.1f})")
    return top_doc, scores, reasons


def _select_mode(requested_mode: str, doc_type: str, query: str, text: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    normalized = requested_mode.lower()
    if normalized in MODES:
        return normalized, ["mode explicitly provided"]

    if _QUERY_MODE_PATTERNS["precision"].search(query):
        reasons.append("query contains precision/evidence keywords")
        return "precision", reasons

    if "confidentiality" in query.lower():
        reasons.append("confidentiality-focused query defaults to precision")
        return "precision", reasons

    if _QUERY_MODE_PATTERNS["overview"].search(query):
        reasons.append("query contains overview keywords")
        return "overview", reasons

    if doc_type in {"credit_agreement", "loan_agreement"}:
        reasons.append("finance doc type defaults to precision")
        return "precision", reasons

    if len(_FINANCE_TERMS.findall(text)) >= 3:
        reasons.append("document has dense risk/finance signals")
        return "precision", reasons

    reasons.append("defaulting to overview")
    return "overview", reasons


def _select_profile(mode: str, query: str, text: str) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if mode == "overview":
        if _QUERY_PROFILE_PATTERNS["obligation_probe"].search(query):
            reasons.append("overview + obligation query => obligation_probe")
            return "obligation_probe", reasons
        reasons.append("overview default => classification_only")
        return "classification_only", reasons

    if _QUERY_PROFILE_PATTERNS["playbook_diff"].search(query):
        reasons.append("precision + compare/risk query => playbook_diff")
        return "playbook_diff", reasons

    if _QUERY_PROFILE_PATTERNS["obligation_probe"].search(query):
        reasons.append("precision + obligation query => obligation_probe")
        return "obligation_probe", reasons

    if len(_FINANCE_TERMS.findall(text)) >= 4:
        reasons.append("precision + risk-dense doc => playbook_diff")
        return "playbook_diff", reasons

    reasons.append("precision default => obligation_probe")
    return "obligation_probe", reasons


def decide_mock_flow(
    query: str | None,
    document_text: str,
    requested_mode: str = "auto",
    requested_doc_type: str = "auto",
) -> dict[str, Any]:
    safe_query = _safe(query)
    safe_text = _safe(document_text)

    doc_type, doc_scores, doc_reasons = _select_doc_type(requested_doc_type, safe_query, safe_text)
    mode, mode_reasons = _select_mode(requested_mode, doc_type, safe_query, safe_text)
    profile, profile_reasons = _select_profile(mode, safe_query, safe_text)

    sorted_scores = dict(sorted(doc_scores.items(), key=lambda item: item[1], reverse=True))
    top = list(sorted_scores.values())[0] if sorted_scores else 0.0
    second = list(sorted_scores.values())[1] if len(sorted_scores) > 1 else 0.0
    confidence = 0.65 if top == 0 else min(0.97, 0.70 + ((top - second) / max(1.0, top)) * 0.2)

    return {
        "query": safe_query,
        "doc_type_scores": sorted_scores,
        "doc_type": doc_type,
        "mode": mode,
        "subtree_profile": profile,
        "reasons": [*doc_reasons, *mode_reasons, *profile_reasons],
        "confidence": round(confidence, 3),
    }


def choose_subtree_steps(profile: str, available_step_ids: list[str], mode: str) -> list[str]:
    profile_normalized = profile if profile in PROFILES else "classification_only"
    mode_normalized = mode if mode in MODES else "overview"

    if mode_normalized == "overview":
        if profile_normalized == "classification_only":
            requested = ["detect_headings", "detect_numbered_clauses", "clause_classifier"]
        elif profile_normalized == "obligation_probe":
            requested = [
                "detect_headings",
                "detect_numbered_clauses",
                "extract_definitions",
                "clause_classifier",
                "obligation_extractor",
            ]
        else:
            requested = [
                "detect_headings",
                "detect_numbered_clauses",
                "extract_definitions",
                "clause_classifier",
                "playbook_compare",
            ]
    else:
        if profile_normalized == "classification_only":
            requested = ["detect_headings", "detect_numbered_clauses", "extract_definitions", "clause_classifier"]
        elif profile_normalized == "obligation_probe":
            requested = [
                "detect_headings",
                "detect_numbered_clauses",
                "extract_definitions",
                "clause_classifier",
                "obligation_extractor",
            ]
        else:
            requested = [
                "detect_headings",
                "detect_numbered_clauses",
                "extract_definitions",
                "clause_classifier",
                "obligation_extractor",
                "playbook_compare",
            ]

    available = set(available_step_ids)
    return [step for step in requested if step in available]


def resolve_dynamic_retrieval(
    query: str | None,
    doc_path: str | Path,
    doc_type: str,
    mode: str,
    bronze_path: str | Path | None = None,
    silver_path: str | Path | None = None,
    k: int = 3,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_query = _safe(query)
    spine_doc = resolve_spine(
        doc_path=doc_path,
        doc_type=doc_type,
        mode=mode,
        bronze_path=bronze_path,
        silver_path=silver_path,
    )
    chunk_graph = build_chunks(spine_doc.nodes, params=params or {"window": 6})
    hits = rank_chunks(chunk_graph, resolved_query, k=k)

    return {
        "spine_source": spine_doc.spine_source,
        "retrieval": {
            "method": "dynamic_chunking_naive_mass_strength",
            "chunks": [hit.to_dict() for hit in hits],
            "chunk_count": len(chunk_graph.chunks),
            "params": chunk_graph.params,
        },
    }
