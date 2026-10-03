# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately. Do not open a public GitHub
issue for an unfixed security problem.

Use GitHub's private vulnerability reporting on this repository:

**Security → Report a vulnerability**

If that option is unavailable, open a regular issue that contains only a short
note asking for a private contact channel, with no technical detail.

Include, if available:

- the affected version or commit (V1 is tagged `v1.0.0`)
- the certified contract SHA-256 you verified
- reproduction steps or a failing test
- the expected and observed behaviour

## Scope

EchoLineage V1 analyses caller-supplied URLs for a caller-supplied claim. The
most security-relevant surfaces are:

- URL input validation (`_normalize_url`, `_validate_inputs`)
- prompt-injection resistance in retrieved page text (`_fence`)
- validator agreement on decision-bearing fields (`_project`, `_same_consensus`)
- failure handling and error classes

## Note on the deployed contract

V1 is deployed and immutable on GenLayer Studionet. A report against the
deployed instance cannot be patched in place; confirmed issues are addressed in
a later version.
