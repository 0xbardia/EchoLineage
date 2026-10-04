"""Differential proof that the V1.0.0 evidence-identity flaw is closed.

This file pins the exact historical V1.0.0 source
(`tests/fixtures/EchoLineage_v1_0_0.py`, SHA-256
b1d3dc2f1bb1a7c2f7622aa26f1fffddb3fa091c656e15880731a11ebea952d8) and runs the
reviewer's exploit against BOTH it and the current contract.

Against V1.0.0 the exploit succeeds: the validator accepts a leader result
whose evidence identity differs from the validated caller inputs, and the
attacker URL/domain actually reaches storage. Against V1.0.1 both fail.

Each exploit therefore appears as a `_on_v1_0_0` test (vulnerable, proving the
reproduction is real and the fixture is the reviewed source) and a matching
`_on_v1_0_1` test (blocked, proving the rejection is closed).

Note on structure: GenVM allows one Contract subclass per SDK import, so the
two versions cannot be deployed inside a single test. They are paired by name
instead — `*_v1_0_0` and `*_v1_0_1` are the same exploit against each source.
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

VULNERABLE = "tests/fixtures/EchoLineage_v1_0_0.py"

ATTACKER_URL = "https://attacker.example.net/forged-evidence"
ATTACKER_DOMAIN = "attacker.example.net"


def _capture(direct_vm, direct_deploy, path):
    """Run one analyze lifecycle against `path`; return (contract, leader)."""
    prime(direct_vm)
    contract = direct_deploy(path)
    contract.analyze(CLAIM, json.dumps([URL_A, URL_B]))
    return contract, last_leader_result(direct_vm)


def test_v1_0_0_fixture_is_the_reviewed_source():
    """The pinned fixture must be byte-identical to the rejected release."""
    import hashlib
    import pathlib

    digest = hashlib.sha256(pathlib.Path(VULNERABLE).read_bytes()).hexdigest()
    assert digest == "b1d3dc2f1bb1a7c2f7622aa26f1fffddb3fa091c656e15880731a11ebea952d8"


# -- exploit: leader URL tamper -------------------------------------------
def test_leader_url_tamper_is_accepted_on_v1_0_0(direct_vm, direct_deploy):
    _contract, leader = _capture(direct_vm, direct_deploy, VULNERABLE)
    tampered = clone(leader)
    tampered["sources"][0]["url"] = ATTACKER_URL
    assert direct_vm.run_validator(leader_result=tampered) is True


def test_leader_url_tamper_is_rejected_on_v1_0_1(direct_vm, direct_deploy):
    _contract, leader = _capture(direct_vm, direct_deploy, CONTRACT)
    tampered = clone(leader)
    tampered["sources"][0]["url"] = ATTACKER_URL
    assert direct_vm.run_validator(leader_result=tampered) is False


# -- exploit: leader domain tamper ----------------------------------------
def test_leader_domain_tamper_is_accepted_on_v1_0_0(direct_vm, direct_deploy):
    _contract, leader = _capture(direct_vm, direct_deploy, VULNERABLE)
    tampered = clone(leader)
    tampered["sources"][0]["domain"] = ATTACKER_DOMAIN
    assert direct_vm.run_validator(leader_result=tampered) is True


def test_leader_domain_tamper_is_rejected_on_v1_0_1(direct_vm, direct_deploy):
    _contract, leader = _capture(direct_vm, direct_deploy, CONTRACT)
    tampered = clone(leader)
    tampered["sources"][0]["domain"] = ATTACKER_DOMAIN
    assert direct_vm.run_validator(leader_result=tampered) is False


# -- exploit: source identity swap ----------------------------------------
def _swap(result, urls):
    tampered = clone(result)
    tampered["sources"][0]["url"] = urls[1]
    tampered["sources"][0]["domain"] = host_of(urls[1])
    tampered["sources"][1]["url"] = urls[0]
    tampered["sources"][1]["domain"] = host_of(urls[0])
    return tampered


def test_source_identity_swap_is_accepted_on_v1_0_0(direct_vm, direct_deploy):
    urls = normalized([URL_A, URL_B])
    _contract, leader = _capture(direct_vm, direct_deploy, VULNERABLE)
    assert direct_vm.run_validator(leader_result=_swap(leader, urls)) is True


def test_source_identity_swap_is_rejected_on_v1_0_1(direct_vm, direct_deploy):
    urls = normalized([URL_A, URL_B])
    _contract, leader = _capture(direct_vm, direct_deploy, CONTRACT)
    assert direct_vm.run_validator(leader_result=_swap(leader, urls)) is False


# -- exploit: persistence stores leader identity --------------------------
def test_persistence_stores_leader_identity_on_v1_0_0(direct_vm, direct_deploy):
    contract, leader = _capture(direct_vm, direct_deploy, VULNERABLE)
    tampered = clone(leader)
    tampered["sources"][0]["url"] = ATTACKER_URL
    tampered["sources"][0]["domain"] = ATTACKER_DOMAIN
    contract._persist(CLAIM, tampered)
    stored = contract.get_source(1, 0)
    assert stored["url"] == ATTACKER_URL
    assert stored["domain"] == ATTACKER_DOMAIN


def test_persistence_stores_validated_identity_on_v1_0_1(direct_vm, direct_deploy):
    urls = normalized([URL_A, URL_B])
    contract, leader = _capture(direct_vm, direct_deploy, CONTRACT)
    tampered = clone(leader)
    tampered["sources"][0]["url"] = ATTACKER_URL
    tampered["sources"][0]["domain"] = ATTACKER_DOMAIN
    contract._persist(CLAIM, urls, tampered)
    stored = contract.get_source(1, 0)
    assert stored["url"] == urls[0]
    assert stored["domain"] == host_of(urls[0])
    assert stored["url"] != ATTACKER_URL
    assert stored["domain"] != ATTACKER_DOMAIN