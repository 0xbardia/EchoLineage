# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately. Do not open a public GitHub
issue for an unfixed security problem.

Use GitHub's private vulnerability reporting on this repository:

**Security → Report a vulnerability**

If that option is unavailable, open a regular issue that contains only a short
note asking for a private contact channel, with no technical detail.

Include, if available:

- the affected version or commit (V1 is tagged `v1.0.0`, V1.0.1 is `v1.0.1`)
- the certified contract SHA-256 you verified
- reproduction steps or a failing test
- the expected and observed behaviour

## Scope

EchoLineage V1 analyses caller-supplied URLs for a caller-supplied claim. The
most security-relevant surfaces are:

- URL input validation (`_normalize_url`, `_validate_inputs`)
- prompt-injection resistance in retrieved page text (`_fence`)
- evidence-identity binding (`_host_of`, `_project`, `_same_consensus`)
- persistence of source identity (`_persist`)
- failure handling and error classes

## Note on the deployed contract

V1.0.0 (`0x0038aBb76A08e8E7a830dD385E82650827EaeF33`) was reviewed, not
accepted, and is superseded by V1.0.1. Deployed contracts are immutable; a
report against a deployed instance cannot be patched in place. Confirmed issues
are addressed in a later version.
