# Security Policy

## Private vulnerability reporting

Use this repository's GitHub
[Report a vulnerability](https://github.com/edgeforge-suite/EdgeForge/security/advisories/new)
form **when available**, or the designated email **security@edgeforgesuite.com**.
If neither private route is available, request a private maintainer channel
without including vulnerability details in a public issue or pull request.
Share reproduction details and sensitive material only through an available
private route; never disclose an undisclosed vulnerability in a public issue/PR.
Route selection alone does not establish delivery or replies. The
[source-release policy](docs/v5-release-readiness.md) requires email receipt/reply
checks before public exposure and PVR enablement and verification at public cutover.

Accountable maintainer: Santosh Hommaradi, responsible for private triage and
coordinated disclosure. No response-time SLA or guaranteed fix is promised.
Report component, exact version/commit, reproduction and impact; omit credentials
and production/customer data. For ordinary project questions, use the
[documentation and issue guidance](README.md#project-intent-and-community).
The designated `contact@edgeforgesuite.com` address is for project administration,
not sales or implementation enquiries.

## Supported boundaries

Security fixes target the current supported baseline; older tags are not
separately maintained. v5 distribution is source and separately authorized tags
for self-managed builds, not an official binary/container distribution, hosted
product service or production certification.
Selected-source technical acceptance is recorded in the
[November 10 results](docs/handover-evidence/v5-acceptance-2026-11-10.md).
It does not authorize tags or publication. See the
[source-release policy](docs/v5-release-readiness.md) for retained checks,
known limitations and publication requirements.

Generated applications are standalone. Their dependencies, adopter business
logic and object/tenant/row authorization remain separate responsibilities.
Supported deployment requires an authenticated TLS gateway exposing only
explicitly approved methods/routes and an application port inaccessible except
through that gateway. Authentication alone is not endpoint exposure control.
Required payment headers are transport delivery, not replay/signature enforcement.

Engine owns manifest 2.0; Studio authors it; optional local KS supplies evidence.
Report against the affected core repository. Do not commit secrets or private
inputs. Historical findings remain OPEN at their dated scope; disclosure does
not repair an actual supported-behavior defect or excuse a failed required check.

References to pre-v5 commits, pull requests, issues and workflow runs point to the private development archive and may be inaccessible to public readers.
