"""V1.0.1 security invariant — the §24 questions, executed as tests.

Each test corresponds to one question from the certification checklist, so the
security claims are verified rather than asserted in prose.
"""

from __future__ import annotations

import json

from conftest import (
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


def _capture(direct_vm, direct_deploy):
    prime(direct_vm)
    contract = direct_deploy(CONTRACT)
    contract.analyze(CLAIM, json.dumps([URL_A, URL_B]))
    return contract, last_leader_result(direct_vm), normalized([URL_A, URL_B])


def _persisted_via_tamper(direct_vm, direct_deploy, mutate):
    """Persist a leader result mutated by `mutate`, return stored source rows."""
    contract, leader, urls = _capture(direct_vm, direct_deploy)
    tampered = clone(leader)
    mutate(tampered)
    contract._persist(CLAIM, urls, tampered)
    case = contract.get_case(0)
    rows = [contract.get_source(0, i) for i in range(int(case["source_count"]))]
    return urls, rows


def test_can_a_malicious_leader_change_persisted_url(direct_vm, direct_deploy):
    """Expected answer: NO."""
    urls, rows = _persisted_via_tamper(
        direct_vm,
        direct_deploy,
        lambda r: r["sources"][0].update(url=ATTACKER_URL),
    )
    assert all(row["url"] != ATTACKER_URL for row in rows)
    assert [row["url"] for row in rows] == urls


def test_can_a_malicious_leader_change_persisted_domain(direct_vm, direct_deploy):
    """Expected answer: NO."""
    urls, rows = _persisted_via_tamper(
        direct_vm,
        direct_deploy,
        lambda r: r["sources"][0].update(domain=ATTACKER_DOMAIN),
    )
    assert all(row["domain"] != ATTACKER_DOMAIN for row in rows)
    assert [row["domain"] for row in rows] == [host_of(u) for u in urls]


def test_can_a_malicious_leader_swap_evidence_identities_by_index(
    direct_vm, direct_deploy
):
    """Expected answer: NO."""
    def swap(result):
        for i in range(2):
            result["sources"][i]["url"] = ATTACKER_URL
            result["sources"][i]["domain"] = ATTACKER_DOMAIN
        # Keep indexes, roles, relations, groups and metrics plausible and equal.
        result["sources"][0]["url"], result["sources"][1]["url"] = (
            result["sources"][1]["url"],
            result["sources"][0]["url"],
        )

    urls, rows = _persisted_via_tamper(direct_vm, direct_deploy, swap)
    assert [row["url"] for row in rows] == urls
    assert [row["source_index"] for row in rows] == list(range(len(urls)))


def test_can_enums_stay_identical_while_identity_changes_and_pass(direct_vm, direct_deploy):
    """Expected answer: NO. Lineage enums are untouched; only identity differs."""
    _contract, leader, _urls = _capture(direct_vm, direct_deploy)

    def flip(result, index):
        result["sources"][index]["url"] = ATTACKER_URL
        result["sources"][index]["domain"] = ATTACKER_DOMAIN

    for index in (0, 1):
        tampered = clone(leader)
        flip(tampered, index)
        # Everything else is byte-identical to the honest leader result.
        for key in ("relations", "groups", "source_count", "usable_source_count",
                    "independent_root_count", "uncertain_relation_count",
                    "classification", "diversity_bps", "redundancy_bps"):
            assert tampered[key] == leader[key]
        for i, source in enumerate(tampered["sources"]):
            if i != index:
                assert source == leader["sources"][i]
        assert direct_vm.run_validator(leader_result=tampered) is False


def test_are_stored_identities_derived_from_validated_inputs(direct_vm, direct_deploy):
    """Expected answer: YES — even when every leader identity field is hostile."""

    def hostile(result):
        for source in result["sources"]:
            source["url"] = ATTACKER_URL
            source["domain"] = ATTACKER_DOMAIN
        for relation in result["relations"]:
            relation["basis"] = "rewritten"

    urls, rows = _persisted_via_tamper(direct_vm, direct_deploy, hostile)
    for index, row in enumerate(rows):
        assert row["url"] == urls[index]
        assert row["domain"] == host_of(urls[index])


def test_does_the_validator_independently_analyze_the_same_validated_urls(
    direct_vm, direct_deploy
):
    """Expected answer: YES — the validator's own run fetches the same inputs."""
    prime(direct_vm)
    contract = direct_deploy(CONTRACT)
    contract.analyze(CLAIM, json.dumps([URL_A, URL_B]))
    stored = {row["url"] for row in contract.get_sources(0)}
    assert stored == {URL_A, URL_B}
    # Honest agreement still holds with the real leader path re-run.
    assert direct_vm.run_validator() is True


def test_identity_binding_survives_every_single_field_tamper(direct_vm, direct_deploy):
    """Sweep: no single identity field mutation can pass validation."""
    _contract, leader, urls = _capture(direct_vm, direct_deploy)

    mutations = {
        "url_attacker": lambda r, i: r["sources"][i].update(url=ATTACKER_URL),
        "url_empty": lambda r, i: r["sources"][i].update(url=""),
        "url_wrong_valid": lambda r, i: r["sources"][i].update(url=urls[1 - i]),
        "url_scheme": lambda r, i: r["sources"][i].update(url="http://insecure.example.gov/x"),
        "domain_attacker": lambda r, i: r["sources"][i].update(domain=ATTACKER_DOMAIN),
        "domain_empty": lambda r, i: r["sources"][i].update(domain=""),
        "domain_subdomain": lambda r, i: r["sources"][i].update(domain="evil." + host_of(urls[i])),
        "domain_case": lambda r, i: r["sources"][i].update(domain=host_of(urls[i]).upper()),
    }
    for name, mutate in mutations.items():
        for index in (0, 1):
            tampered = clone(leader)
            mutate(tampered, index)
            verdict = direct_vm.run_validator(leader_result=tampered)
            assert verdict is False, f"{name} on source {index} was accepted"