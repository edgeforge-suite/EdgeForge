# Dependency Evidence — SBOM, Audit, and License Inventory

> **Import-gate G4.** Dependency evidence an import / compliance reviewer asks
> for first: Python SBOM + vulnerability audit + transitive license inventory,
> plus representative generated-app Maven dependency/license evidence. Part of
> the handover-evidence set (the G10 index links these; the index is a separate
> item).
>
> **Snapshots:** The root Python artifacts below are historical evidence from
> **2026-06-28**. The active Python reference assessment lives in
> [`python-current/`](python-current/); its provenance records the actual scan
> time. Generated-app Maven evidence was refreshed separately. Python and
> Maven assessment remain independent slices of M2.

The **2026-11-02** Python reference scan covers all **76** selected third-party
packages and reports **zero findings at scan time**, after a bounded joserfc
1.7.6 lock-only correction. The existing Authlib/dnspython selections and Python
3.11 floor remain unchanged. The September23, October20, October25 and October29 snapshots remain under
[`python-current/history/`](python-current/history/), with their original
declarations and provenance, not relabeled as fresh proof. See the
[current correction rationale](python-dependency-policy.md#bounded-correction-on-2026-11-02).
The license
inventory flags `certifi` (MPL-2.0) for separate review; this PR makes no
license-selection or release-clearance decision. See the actual UTC time and
tool/input provenance in [`python-current/provenance.json`](python-current/provenance.json).

## Artifacts

| Artifact | What it is | Tool |
|---|---|---|
| [`requirements-lock.txt`](../../requirements-lock.txt) | Selected 76-package CPython 3.11.15 / Debian 12 x86_64 reference closure, enforced by the Python CI install and audit. Not a cross-platform universal lock. | Exact inventory reconciliation after a clean constrained install in the pinned reference image |
| [`python-current/`](python-current/) | Active Python SBOM, audit, license inventory and provenance. Every inventory is checked against the installed reference environment and selected lock before publication. | `cyclonedx-bom` **7.3.0**, `pip-licenses` **5.5.5**, `pip-audit` **2.9.0** |
| [`sbom.cdx.json`](sbom.cdx.json), [`dependency-licenses.md`](dependency-licenses.md), [`pip-audit.md`](pip-audit.md) | Historical Python evidence, including the recorded pytest advisory. Retained without relabeling or rewriting. | Tools and date recorded in those artifacts |
| [`generated-app-dependencies.md`](generated-app-dependencies.md) | Representative generated-app Maven dependency tree + third-party license report. | Maven `dependency:tree`; `org.codehaus.mojo:license-maven-plugin` **2.5.0** |
| [Per-app Maven assessment](generated-maven-assessment.md) | Separate post-generation SBOM, complete-inventory check, live advisory assessment and pending findings; does not replace the historical artifacts above. | CycloneDX Maven **2.9.1**, Maven dependency plugin **3.8.1**, OSV-Scanner **2.3.8** |
| [Generated Docker image assessment](generated-image-assessment.md) | Actual build/runtime surfaces, case-to-artifact coverage and OS/JDK/packaged/native findings, separate from release clearance. | Pinned tools/database identities in the image evidence |

The new assessment lane's dated baseline and machine-readable reports are linked
from [generated-maven-assessment.md](generated-maven-assessment.md). This is an
assessment/tooling slice, not vulnerability remediation or completion of M2.

## Regeneration

The Python reference command updates **only** `python-current/`; it does not
refresh the lock or touch generated-app Maven evidence. Run it only after
reviewing the selected lock and authorizing the PyPI advisory requests described
in [the Python policy](python-dependency-policy.md):

```bash
make sbom

# Re-resolve the reference lock separately (review the diff before scanning)
make lock

# Generated-app Maven evidence only
scripts/generate-generated-app-dependency-evidence.sh [SNAPSHOT_DATE] [MAVEN_LICENSE_PLUGIN_VERSION]
```

The earlier `scripts/generate-dependency-evidence.sh` now refuses to run: its
unconstrained host resolution could overwrite both the selected lock and the
dated historical evidence. The commands above are the supported refresh paths.
The Python command uses the pinned Linux image and isolated pinned assessment
tools; exact input hashes,
package counts, tool versions and UTC assessment time are in
[`python-current/provenance.json`](python-current/provenance.json).

## Scope (read this)

- **Declared Python dependencies remain the source of truth.** The selected
  reference lock constrains CI's Python 3.11 Linux install. Engine v5 requires
  Python 3.11+; other supported local environments resolve the exact direct
  declarations separately. Historical Python 3.10 receipts remain dated.
- **All reference third-party packages are enumerated.** The local Engine
  distribution and installer bootstrap tools are excluded explicitly; they are
  not silently called scanned. The separate Maven and image surfaces are not
  covered by this Python audit.
- **Findings and licenses are facts, not approvals.** The dated historical
  pytest result remains linked above. The fresh reference audit reports zero
  known advisories, while `certifi` remains an MPL-2.0 license-review item.
  Neither observation establishes release acceptance.
- **Generated-app Maven evidence is representative.** Each generated app is a
  standalone Maven project whose dependency surface depends on the manifest. This
  pack regenerates the canonical CI smoke fixture and records its dependency/license
  surface; it is not a universal statement about every possible future manifest.

## This is third-party licenses — not EdgeForge's own license

This inventory is the licenses of EdgeForge's **third-party dependencies**. It is
**distinct from EdgeForge's own selected Apache-2.0 license**. This dependency
inventory does not accept third-party terms or establish authority to publish
(the remaining maintainer-owned G1 gate).

## Python audit gate

The existing required **Python test suite** CI job now installs against the
reference lock and runs the Python vulnerability audit after tests. Findings,
scanner/network failures, malformed or incomplete reports, version drift and
missing packages fail that job. This does not establish a license-selection gate
or complete the separate Maven, image and overall M2 work.
