"""Shared fixtures and helpers for the EchoLineage test suite.

Every test in this suite runs the *real* contract through GenLayer Direct
Mode (`genlayer-test`). Nothing here reimplements contract logic: helpers only
mock the outside world (web fetches, model output) so that the leader path is
deterministic and a validator can be re-run with an arbitrary leader result.
"""

from __future__ import annotations

import copy
import json
from urllib.parse import urlsplit

CONTRACT = "contracts/EchoLineage.py"

CLAIM = "City council approved the transit levy on 12 March"

# Two distinct, safe, public HTTPS sources.
URL_A = "https://council.example.gov/records/2024/levy-vote"
URL_B = "https://herald.example.org/news/transit-levy-approved"

BODY_A = (
    "The city council voted 7-2 on 12 March to approve the transit levy. "
    "The measure funds two bus rapid transit lines. Clerk minutes record the vote."
)
BODY_B = (
    "Council members approved the transit levy on 12 March, according to "
    "minutes published by the city clerk. The levy adds 0.4 percent to transit fares."
)

MODEL_JSON = json.dumps(
    {
        "sources": [
            {
                "index": 0,
                "title": "Council minutes, 12 March",
                "claim_relevance": "RELEVANT",
                "role": "PRIMARY_EVIDENCE",
                "declared_origin": "City clerk minutes",
                "lineage_basis": "Primary record of the vote.",
            },
            {
                "index": 1,
                "title": "Herald report on the levy vote",
                "claim_relevance": "RELEVANT",
                "role": "ORIGINAL_REPORTING",
                "declared_origin": "Clerk minutes",
                "lineage_basis": "Names the clerk minutes as its upstream.",
            },
        ],
        "relations": [
            {
                "a": 0,
                "b": 1,
                "relation": "RIGHT_DERIVES_LEFT",
                "subtype": "QUOTATION",
                "basis": "Source 1 quotes the clerk minutes in source 0.",
            }
        ],
    }
)


def host_of(url: str) -> str:
    """Deterministic hostname derivation, mirroring the contract."""
    return urlsplit(url).hostname or ""


def normalized(urls) -> list:
    """Normalize URLs the same way the contract's _normalize_url does.

    Only the transformations _validate_inputs applies are reproduced here so a
    test can pass a deliberately messy caller URL and still assert on the
    canonical stored form.
    """
    out = []
    for raw in urls:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower().rstrip(".")
        path = parts.path or "/"
        while "//" in path:
            path = path.replace("//", "/")
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        out.append(f"https://{host}{path}")
    return out


def prime(
    direct_vm,
    urls=None,
    bodies=None,
    model: str = None,
) -> list:
    """Mock every source and the model so a full analyze lifecycle succeeds.

    Returns the URL list as given (normalization is applied by the contract).
    ``bodies`` overrides the default page text per source; an empty body makes
    that source come back UNAVAILABLE. ``model`` overrides the default model
    JSON. Pass an explicit ``model`` whenever the test asserts on lineage
    semantics — the default model fixture only satisfies a happy-path run.
    """
    if urls is None:
        urls = [URL_A, URL_B]
    if bodies is None:
        bodies = [BODY_A, BODY_B]
    for index, url in enumerate(urls):
        body = bodies[index] if index < len(bodies) else bodies[-1]
        direct_vm.mock_web(
            r"^" + url.replace(".", r"\.") + r".*$", {"status": 200, "body": body}
        )
    direct_vm.mock_llm(r".*", model if model is not None else MODEL_JSON)
    return list(urls)


def last_leader_result(direct_vm) -> dict:
    """The leader result captured by the most recent run_nondet_unsafe call."""
    return direct_vm._captured_validators[-1][0]


def clone(value):
    return copy.deepcopy(value)


def run_analyze(direct_deploy, claim: str = CLAIM, urls=None):
    """Deploy, analyze, and return (contract, normalized_urls)."""
    if urls is None:
        urls = [URL_A, URL_B]
    contract = direct_deploy(CONTRACT)
    contract.analyze(claim, json.dumps(urls))
    return contract, normalized(urls)