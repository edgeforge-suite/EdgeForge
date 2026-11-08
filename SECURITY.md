# Security Policy

## Private reporting and activation

GitHub Private Vulnerability Reporting (PVR) is the selected primary route for
the currently private `edgeforge-suite/EdgeForge` repository after public cutover.
The private import is complete; PVR must be enabled and
verified immediately at public cutover, before the launch announcement.
The selected email route is **security@edgeforgesuite.com**; configure and test
monitored receipt and replies before the public flip. **Neither PVR activation
nor email delivery is verified by this preparation PR.** Do not send sensitive
reports to an unverified route or open a public issue/PR. Until activation,
coordinate privately with the maintainer through an already verified private
channel; do not assume an unlisted address.

Accountable maintainer: Santosh Hommaradi, responsible for private triage and
coordinated disclosure. No response-time SLA or guaranteed fix is promised.
Report component, exact version/commit, reproduction and impact; omit credentials
and production/customer data. For ordinary project questions, use the
[documentation and issue guidance](README.md#project-intent-and-community).
The selected `contact@edgeforgesuite.com` route is for project administration,
not sales or implementation enquiries; operational verification remains pending.

## Supported boundaries

Security fixes target the current supported baseline; older tags are not
separately maintained. v5 is a tested source-and-tags release, not an official
binary/container distribution, hosted product service or production certification.
It is not yet accepted or published. See the
[source-release policy](docs/v5-release-readiness.md) for retained checks,
known limitations and outstanding publication gates.

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
