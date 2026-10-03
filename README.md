# EchoLineage

Claim-scoped source provenance for GenLayer.

EchoLineage is a standalone GenLayer Intelligent Contract that determines how many genuinely independent evidentiary origins exist behind a caller-supplied set of web sources for one specific claim.

> 10 URLs do not necessarily represent 10 independent sources.

## What it does

Several pages can quote one wire, reprint one press release, or syndicate one article. Counting links overstates how much independent evidence a claim actually has. EchoLineage persists that lineage on-chain so a later reader can inspect the roots, not just the URL list.

Lineage is claim-scoped. The same publisher can be independent for one claim and derivative for another, so domain names are not treated as roots.

An **evidentiary root** is the smallest identifiable upstream origin of claim-relevant information: a filing, dataset, announcement, interview, paper, wire, or original report. The contract does not crawl beyond the URLs it was given. A page may name an upstream source; V1 does not fetch that source.

## Why source independence matters

Any downstream consumer — a reader, an agent, another contract — needs to distinguish broad *coverage* from genuine *corroboration*. Ten copies of one press release is one origin, not ten. Encoding that distinction on-chain makes the difference auditable and reusable.

## How it works

```text
Claim + 2–8 HTTPS URLs
→ independent web retrieval
→ claim-relevant evidence extraction
→ pairwise provenance analysis
→ dependency graph
→ evidentiary root groups
→ deterministic diversity metrics
→ immutable on-chain case
```

## Consensus

EchoLineage uses custom GenLayer consensus primitives:

- custom `leader_fn`
- custom `validator_fn`
- `gl.vm.run_nondet_unsafe`
- independent validator-side evidence retrieval
- consensus over decision-bearing structured fields
- deterministic post-consensus graph construction

Validators do **not** merely check JSON format. Web pages and model output vary across validators, so:

The leader, inside the non-deterministic block, fetches each submitted URL, asks a model for claim relevance, source role, and one relation per usable pair, and returns bounded structured data. It does not write storage.

The validator does not accept the leader because the JSON is well formed. It fetches the same URLs, runs the same extraction, canonicalizes enums and indexes, rebuilds the dependency graph, and compares decision-bearing fields:

- availability, claim relevance, and role
- pairwise relation and, where the relation is a dependency, its subtype
- canonical root groups
- usable source count, independent root count, uncertain-relation count
- classification and basis-point metrics

Titles, declared origins, and explanations may differ between validators. Those strings are not compared.

Natural-language page text is fenced as untrusted evidence. Instructions embedded in a page cannot change the task.

Accepted dependency edges are `SHARED_ROOT`, `LEFT_DERIVES_RIGHT`, `RIGHT_DERIVES_LEFT`, and `COMMON_UPSTREAM`. `INDEPENDENT` and `UNCERTAIN` do not create edges. Root groups are the connected components, sorted by source index. If any usable pair is `UNCERTAIN`, or fewer than two sources are usable, the classification is `INCONCLUSIVE`. Uncertainty is never recorded as independence.

## Classification

When the matrix is complete and nothing is uncertain:

| Condition | Classification |
| --- | --- |
| root count equals usable sources | `INDEPENDENT` |
| one root and at least two usable sources | `SINGLE_ORIGIN` |
| more than one root, but fewer than the usable sources | `PARTIALLY_DEPENDENT` |

`INCONCLUSIVE` is reported when any usable pair is uncertain, or when fewer than two sources are usable.

## Deterministic metrics

Metrics are integers computed after consensus, never by the model:

```text
diversity_bps  = independent_root_count * 10000 // usable_source_count
redundancy_bps = 10000 - diversity_bps
```

Both are `0` when there are no usable sources. A usable source is `AVAILABLE` and either `RELEVANT` or `PARTIAL`.

## Contract API

Write:

```text
analyze(claim, urls_json)
```

`urls_json` is a JSON array of 2 to 8 HTTPS URLs. The claim is trimmed and must be 1 to 500 characters. HTTP, duplicates, credentials in the URL, non-standard ports, and obvious local or private hosts are rejected.

Read methods:

```text
get_version
get_case_count
get_case
get_source
get_sources
get_relation
get_root_count
get_root_group
get_dependency_matrix
get_diversity_bps
get_redundancy_bps
get_classification
```

Views do not modify state. An unknown case, source, relation, or root group reverts with `EXPECTED_INPUT`. `get_relation` accepts either argument order and returns the canonical pair (`source_a` < `source_b`). Sources that are not in a root group report `root_group` 255.

Cases are immutable. A later analysis of the same claim allocates the next case id, starting at 0.

## Deployment

Network: GenLayer Studionet  
Chain ID: 61999  
Contract: `0x0038aBb76A08e8E7a830dD385E82650827EaeF33`  
Explorer: <https://explorer-studio.genlayer.com/address/0x0038aBb76A08e8E7a830dD385E82650827EaeF33>  
Deployment transaction: `0xbb21aa7266ad2fc74c5a4ecc6dffd8a9d581683863288049a3234cfe081d5316`  
Version: `1.0.0`

Certified source SHA-256 (`contracts/EchoLineage.py`):

```text
b1d3dc2f1bb1a7c2f7622aa26f1fffddb3fa091c656e15880731a11ebea952d8
```

## Verified lifecycle

V1 was deployed successfully on Studionet. The deployment finalized with execution SUCCESS, and all frozen read methods were exercised against the deployed contract. Two real `analyze` transactions then ran with validators, not leader-only mode; the explorer records all three transactions (deploy plus both analyses) as FINALIZED.

## Tests

Pinned toolchain, installed from `requirements.txt`:

```text
genlayer-test 0.29.2
genvm-linter 0.11.0
genlayer-py 0.16.3
```

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
GENVM_VERSION=v0.3.0-rc7 .venv/bin/genvm-lint check contracts/EchoLineage.py
```

The lint command runs the static checks and the SDK-reflection validation pass, reporting the contract name and its method count.

`GENVM_VERSION` pins the GenVM runner bundle. Without it the linter resolves a runner that does not contain the hash pinned in the contract header, and validation fails on SDK load rather than on the contract.

Local Studio integration and `gltest` require Docker and a running validator network; they were not part of this publication. Studionet is the deployment target.

## V1 scope

EchoLineage does **not** determine whether a claim is true. It records independence and provenance only.

It does not provide:

- publisher reputation
- truth scoring
- political bias scoring
- recursive crawling
- plagiarism detection

Other V1 limits:

- At most eight caller-supplied URLs.
- Private and local hosts are filtered by pattern, not by a full DNS check.
- Validators must agree on enums, so ambiguous pages can fail consensus instead of storing a guess.
- `INCONCLUSIVE` still reports the component count of accepted edges. Read the classification before treating `diversity_bps` as a finding of independence.

## License

MIT. See [LICENSE](LICENSE).
