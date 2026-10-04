"""EchoLineage V1.0.1 — validator consensus regression suite.

These tests encode the V1.0.1 rejection fix: evidence identity (url/domain)
must be bound to the validated caller inputs in the validator comparison, and
persistence must derive stored identity from those inputs rather than from
leader output.

Every assertion below runs the real contract through GenLayer Direct Mode.
Prose fields (title, declared_origin, lineage_basis, relation basis) are
intentionally non-consensus and must stay that way.
"""

from __future__ import annotations

import json

from conftest import (
    BODY_A,
    BODY_B,
    CLAIM,
    CONTRACT,
    URL_A,
    URL_B,
    clone,
    host_of,
    last_leader_result,
    normalized,
    prime,
)
from gltest.direct.pytest_plugin import *  # noqa: F401,F403  (fixtures)

ATTACKER_URL = "https://attacker.example.net/forged-evidence"
ATTACKER_DOMAIN = "attacker.example.net"

# A prose variant: identical evidence identities and consensus-critical values,
# only the non-consensus wording differs.
PROSE_VARIANT = json.dumps(
    {
        "sources": [
            {
                "index": 0,
                "title": "Official record of the March 12 council vote",
                "claim_relevance": "RELEVANT",
                "role": "PRIMARY_EVIDENCE",
                "declared_origin": "the office of the city clerk",
                "lineage_basis": "This page is the primary record itself.",
            },
            {
                "index": 1,
                "title": "Daily paper recounts approval of the transit levy",
                "claim_relevance": "RELEVANT",
                "role": "ORIGINAL_REPORTING",
                "declared_origin": "the city clerk's published minutes",
                "lineage_basis": "It explicitly credits the clerk minutes upstream.",
            },
        ],
        "relations": [
            {
                "a": 0,
                "b": 1,
                "relation": "RIGHT_DERIVES_LEFT",
                "subtype": "QUOTATION",
                "basis": "The newspaper quotes the minutes recorded by source 0.",
            }
        ],
    }
)


def _analyze_capture(direct_vm, direct_deploy, urls=None):
    """Run one full analyze lifecycle and return (contract, leader_result, urls)."""
    if urls is None:
        urls = [URL_A, URL_B]
    prime(direct_vm, urls=urls)
    contract = direct_deploy(CONTRACT)
    contract.analyze(CLAIM, json.dumps(urls))
    return contract, last_leader_result(direct_vm), normalized(urls)


# --------------------------------------------------------------------------
# TEST A — normal agreement
# --------------------------------------------------------------------------
def test_validator_accepts_normal_agreement(direct_vm, direct_deploy):
    _c, _leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    assert direct_vm.run_validator() is True


# --------------------------------------------------------------------------
# TEST B — leader URL tamper
# --------------------------------------------------------------------------
def test_validator_rejects_leader_url_tamper(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["sources"][0]["url"] = ATTACKER_URL
    assert direct_vm.run_validator(leader_result=tampered) is False


# --------------------------------------------------------------------------
# TEST C — leader domain tamper
# --------------------------------------------------------------------------
def test_validator_rejects_leader_domain_tamper(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["sources"][0]["domain"] = ATTACKER_DOMAIN
    assert direct_vm.run_validator(leader_result=tampered) is False


# --------------------------------------------------------------------------
# TEST D — URL + domain tamper
# --------------------------------------------------------------------------
def test_validator_rejects_url_and_domain_tamper(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["sources"][0]["url"] = ATTACKER_URL
    tampered["sources"][0]["domain"] = ATTACKER_DOMAIN
    assert direct_vm.run_validator(leader_result=tampered) is False


# --------------------------------------------------------------------------
# TEST E — source identity swap
# --------------------------------------------------------------------------
def test_validator_rejects_source_identity_swap(direct_vm, direct_deploy):
    _c, leader, urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["sources"][0]["url"] = urls[1]
    tampered["sources"][0]["domain"] = host_of(urls[1])
    tampered["sources"][1]["url"] = urls[0]
    tampered["sources"][1]["domain"] = host_of(urls[0])
    assert direct_vm.run_validator(leader_result=tampered) is False


# --------------------------------------------------------------------------
# TEST F — duplicate source index
# --------------------------------------------------------------------------
def test_validator_rejects_duplicate_source_index(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    # index 0 twice, index 1 omitted
    tampered["sources"][1] = clone(tampered["sources"][0])
    assert direct_vm.run_validator(leader_result=tampered) is False


# --------------------------------------------------------------------------
# TEST G — missing source
# --------------------------------------------------------------------------
def test_validator_rejects_missing_source(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["sources"] = tampered["sources"][:1]
    assert direct_vm.run_validator(leader_result=tampered) is False


# --------------------------------------------------------------------------
# TEST H — out-of-range index
# --------------------------------------------------------------------------
def test_validator_rejects_out_of_range_source_index(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["sources"][0]["index"] = 5
    assert direct_vm.run_validator(leader_result=tampered) is False


# --------------------------------------------------------------------------
# TEST I — prose-only difference must still be accepted
# --------------------------------------------------------------------------
def test_validator_accepts_prose_only_difference(direct_vm, direct_deploy):
    prime(direct_vm)
    contract = direct_deploy(CONTRACT)
    contract.analyze(CLAIM, json.dumps([URL_A, URL_B]))

    # The validator re-runs the leader path under the *variant* prose mock.
    direct_vm.clear_mocks()
    prime(direct_vm)
    direct_vm.mock_llm(r".*", PROSE_VARIANT)
    assert direct_vm.run_validator() is True


# --------------------------------------------------------------------------
# TEST J — persistence cannot trust leader identity
# --------------------------------------------------------------------------
def test_persistence_cannot_trust_leader_identity(direct_vm, direct_deploy):
    """Tamper an accepted result's url/domain and prove storage ignores them.

    The stored identity must equal the validated normalized caller input and
    the deterministic derived domain, NOT the tampered leader values.
    """
    contract, leader, urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["sources"][0]["url"] = ATTACKER_URL
    tampered["sources"][0]["domain"] = ATTACKER_DOMAIN

    contract._persist(CLAIM, urls, tampered)
    stored = contract.get_source(1, 0)
    assert stored["url"] == urls[0]
    assert stored["domain"] == host_of(urls[0])
    assert stored["url"] != ATTACKER_URL
    assert stored["domain"] != ATTACKER_DOMAIN


# --------------------------------------------------------------------------
# Malformed / relation / root manipulation (preserved V1 gates)
# --------------------------------------------------------------------------
def test_validator_rejects_relation_tamper(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["relations"][0]["relation"] = "INDEPENDENT"
    tampered["relations"][0]["subtype"] = "NONE"
    tampered["groups"] = [[0], [1]]
    tampered["independent_root_count"] = 2
    tampered["diversity_bps"] = 10000
    tampered["redundancy_bps"] = 0
    tampered["classification"] = "INDEPENDENT"
    assert direct_vm.run_validator(leader_result=tampered) is False


def test_validator_rejects_root_tamper(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["groups"] = [[0], [1]]
    tampered["independent_root_count"] = 2
    assert direct_vm.run_validator(leader_result=tampered) is False


def test_validator_rejects_malformed_leader_result(direct_vm, direct_deploy):
    _c, _leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    assert direct_vm.run_validator(leader_result={"sources": [], "relations": []}) is False
    assert direct_vm.run_validator(leader_result="not a dict") is False


def test_validator_rejects_bad_classification_enum(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["classification"] = "TRUTH_SCORE_99"
    assert direct_vm.run_validator(leader_result=tampered) is False


def test_validator_rejects_relation_self_loop(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["relations"][0]["b"] = tampered["relations"][0]["a"]
    assert direct_vm.run_validator(leader_result=tampered) is False


def test_validator_rejects_relation_out_of_range(direct_vm, direct_deploy):
    _c, leader, _urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    tampered["relations"][0]["b"] = 9
    assert direct_vm.run_validator(leader_result=tampered) is False


# --------------------------------------------------------------------------
# Reviewer-finding unit assertion (locatable by name)
# --------------------------------------------------------------------------
def test_reviewer_regression_source_url_domain_are_consensus_bound(
    direct_vm, direct_deploy
):
    """Regression test for QIntelligent Contracts review:
    consensus must bind evidence identity.

    A leader must not be able to keep every lineage enum identical while
    changing which evidence URL/domain a source index claims.
    """
    _c, leader, urls = _analyze_capture(direct_vm, direct_deploy)

    # Baseline: honest result is accepted.
    assert direct_vm.run_validator() is True

    # Tamper only identity; keep index, role, relations, groups, metrics,
    # classifications identical.
    tampered = clone(leader)
    tampered["sources"][0]["url"] = ATTACKER_URL
    tampered["sources"][0]["domain"] = ATTACKER_DOMAIN
    assert direct_vm.run_validator(leader_result=tampered) is False

    # Tamper only domain (URL stays correct).
    domain_only = clone(leader)
    domain_only["sources"][0]["domain"] = ATTACKER_DOMAIN
    assert direct_vm.run_validator(leader_result=domain_only) is False

    # Tamper only URL (domain stays correct).
    url_only = clone(leader)
    url_only["sources"][0]["url"] = ATTACKER_URL
    assert direct_vm.run_validator(leader_result=url_only) is False


def test_reviewer_regression_persistence_derives_identity_from_inputs(
    direct_vm, direct_deploy
):
    """Regression test for QIntelligent Contracts review:
    consensus must bind evidence identity.

    Persistence must derive stored url/domain from the validated caller input.
    """
    contract, leader, urls = _analyze_capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    for source in tampered["sources"]:
        source["url"] = ATTACKER_URL
        source["domain"] = ATTACKER_DOMAIN
    contract._persist(CLAIM, urls, tampered)

    for index, url in enumerate(urls):
        stored = contract.get_source(1, index)
        assert stored["url"] == url
        assert stored["domain"] == host_of(url)
        assert stored["url"] != ATTACKER_URL
        assert stored["domain"] != ATTACKER_DOMAIN