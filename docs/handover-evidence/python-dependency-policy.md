# Engine Python Reference Dependency Policy

This is the Python reference-dependency assessment and enforcement policy. It does not cover generated Maven
applications, container images, license acceptance, or the whole Suite.

## Selected environment

The reviewed reference is **CPython 3.11.15 on Debian 12 x86_64**, image
`python:3.11.15-bookworm@sha256:a8f8fbe1a0edc9e4dddafa64ba73f7e04be7be5ebc23f332362e779e0a2e4e52`.
`requirements.txt` and the runtime/dev declarations in `pyproject.toml` retain
the exact direct pins. `requirements-lock.txt` selects their complete third-party
closure in that environment and is applied with `-c` in CI. `pip check` and the
audit compare all normalized installed names and versions to the lock. The
local Engine package and `pip`, `setuptools`, `wheel` bootstrap tools are
outside this third-party lock and explicitly excluded from this audit.

This reference lock is **not universal across Python or OS versions**. Engine v5
requires **Python 3.11+**, approved by the maintainer on October 28, 2026. Python
3.10 compatibility receipts below remain dated evidence, not current support
claims. Other supported environments may resolve different compatible transitives. Linux-only keyring
dependencies (`jeepney`, `SecretStorage`) are present in the reference closure;
other operating systems may add or omit conditional packages. Local development
can still use `make setup` / `pip install -r requirements.txt`.

## Reproduce and interpret

`make lock` re-resolves in the pinned image; review that diff before selecting
it. `make sbom` runs a clean constrained install, installs
`cyclonedx-bom==7.3.0`, `pip-licenses==5.5.5`, and `pip-audit==2.9.0` in a
**separate** virtual environment, checks all inventory coverage, and writes only
[`python-current/`](python-current/). It never runs Maven. The assessment
records actual UTC time, source revision, declared/lock digests, actual Python
and tool versions, package counts, scanner exit, SBOM, audit and licenses.

The audit uses `pip-audit --no-deps --disable-pip --strict` against the exact
lock and PyPI's JSON advisory endpoint
`https://pypi.org/pypi/<normalized-name>/<version>/json`. Only the selected
third-party package names and versions are queried; no Engine source or local
package is sent. The query requires explicit approval before a local evidence
refresh. The same outbound dependency-metadata query occurs in CI. The
vulnerability service is a live external dependency; its response may change
without a lock change. Scanner errors are not clean results.

Complete findings also emit deterministic JSON lines on **stderr**, identifying
`package`, `installed_version` and `advisory_id` after all coverage and exit-status
checks pass. The existing stdout aggregate JSON and exits 0/1/2 are unchanged.
Use the existing `--output` option to retain a detailed private diagnostic report;
raw advisory bodies, source and credentials are not printed to CI.

## Bounded correction on 2026-11-02

PR #338's required audit at `e6b59f8` reported `joserfc==1.7.5` /
`GHSA-9pg5-8c7x-5hfx`, one finding across 76 packages, exit 1. The
[compact correction receipt](python-audit-correction-2026-11-02.json) retains that
failure, source URLs/hashes, artifact qualification and proof boundaries.

Select only **joserfc 1.7.6** in the reference lock. Other 75 pins, direct
requirements and Engine's Python >=3.11 floor are unchanged. Authlib 1.9.1
requires `joserfc>=1.6.8`; FastMCP's `fastmcp-slim[server]` extra also directly
requires `joserfc>=1.1.0`. Both routes are satisfied by 1.7.6. This second route
is a November 2 review clarification from retained installed metadata, not a new
assessment or a change to the recorded source/time. The selected wheel requires Python >=3.10 and
`cryptography>=45.0.1`, satisfied by the unchanged 50.0.1 pin. Optional drafts
dependencies are not enabled. No new direct dependency or resolver refresh.

The [repository advisory](https://github.com/authlib/joserfc/security/advisories/GHSA-9pg5-8c7x-5hfx)
claims `<=1.7.4`, patched in 1.7.5, while the
[reviewed advisory](https://github.com/advisories/GHSA-9pg5-8c7x-5hfx)
reports `<1.7.6`, patched in 1.7.6. Both observations remain recorded. The
[1.7.6 release](https://github.com/authlib/joserfc/releases/tag/1.7.6), resolved
tag `c54d9cce33e5de65b7684478193f6633279cf90e`, and published wheel/sdist contain
the early compact-input size guard before splitting. All 55 wheel Python files
are byte-identical to both the source distribution and tagged source; published
artifact SHA-256 values match PyPI. This is source/artifact binding, not a signing
or universal exploitability claim. Only this first candidate needed evaluation.

A 38-byte canary with tiny configured limits fails if splitting occurs before
the size error: installed 1.7.5 fails that control, 1.7.6 passes. Valid HMAC
signatures still verify; wrong keys fail. No memory-exhaustion benchmark, custom
security patch or scanner suppression. Full advisory responses remain private.

The clean pinned CPython 3.11.15 / Debian12 x86_64 installation passes `pip check`
and complete installed-inventory reconciliation. One strict candidate audit,
reused for the existing SBOM/license/provenance outputs, covers **76/76 packages,
zero findings, no omissions/skips, exit 0** at `2026-11-02T04:32:27.996978Z`.
Actual assessed input commit: `c85998355dcc5ee23944bfa055e4001ebde96c97`;
later evidence/PR/CI heads are separate identities. The preceding October29
records and their declarations are preserved byte-for-byte in
[`python-current/history/2026-10-29/`](python-current/history/2026-10-29/).

Focused reference checks pass (78 tests, no skips), including all seven MCP tools,
real in-process catalog calls and fixed-clock CLI/MCP generation equality.
Generator/example bytes, Java dependencies and Docker recipes are unchanged from
`e6b59f8`; prior SQL-isolation, Java/H2, SQL, HTTP and content proof remains dated
at its actual identities. No manual Maven/runtime/image/L5 campaign was repeated.
Final-head automatic CI and external Claude review remain separate requirements;
this point-in-time Python correction is not M2, risk or publication clearance.

## Bounded correction on 2026-10-29

PR #337's October 28 CI audit at `e07550f` reported **seven findings across
76 packages**: six Authlib 1.8.0 matches and one dnspython 2.8.0 match. The
[compact correction receipt](python-audit-correction-2026-10-29.json) enumerates
all seven advisory IDs, ranges, primary sources and artifact hashes. Select
**Authlib 1.9.1** and **dnspython 2.9.0** only; all other 74 pins stay fixed.
These remain transitives of FastMCP/slim and email-validator, not new direct
requirements. dnspython 2.9.0 requires Python >=3.11. Engine's approved v5
minimum is now 3.11; this does not migrate or change generated Java applications.

The Authlib repository advisory for
[GHSA-8m4g-j4wp-wgcg](https://github.com/authlib/authlib/security/advisories/GHSA-8m4g-j4wp-wgcg)
still reports `<=1.7.2` and no patch, while the
[reviewed database](https://github.com/advisories/GHSA-8m4g-j4wp-wgcg)
reports `<1.9.1`, patched in 1.9.1. Neither claim is silently overwritten.
The [tagged 1.9.1 release notes](https://github.com/authlib/authlib/blob/v1.9.1/docs/upgrades/changelog.rst),
checksum-verified wheel/sdist/tag source equality and executed empty raw/JWK
HMAC rejection support the selected release. HS256/384/512 valid signatures
still verify and wrong signatures fail. The old wheels fail all four new
offline controls, including dnspython's excessive compression-pointer chain;
the corrected versions reject that chain and preserve valid names.
This is bounded library proof, not a finding of prior Engine exploitability
or certification of every OAuth/DNS deployment. Authlib's legacy JOSE API emits
its existing deprecation warning; no authentication feature is introduced.

The clean pinned CPython 3.11.15 / Debian 12 x86_64 constrained install passed
`pip check`. One candidate strict audit, reused for SBOM/licenses, covered
**76/76 packages, zero matches, no omissions/skips, exit 0** at
`2026-10-29T01:09:06.352054Z`, actual input commit
`c76287d220e8a9cad3d9c36e46e175b6ca5e390b`. Later evidence/PR commits are not
that assessment's source. The six dated October29 snapshot records match that lock/environment.
The previous October25 records and their original declarations are preserved
byte-for-byte in [`python-current/history/2026-10-25/`](python-current/history/2026-10-25/).

Focused Python 3.11 tests passed (84, no skips), including all seven MCP tool
registrations and two real in-process catalog calls. Outside-checkout install
and CLI/metadata proof passed; wheel/sdist retain Apache-2.0 LICENSE and NOTICE.
Sync/async HTTPX mock OAuth clients and email syntax checks pass without external
services. One installed-wheel DDA generation passed schema/static harness checks
with networking disabled. Engine implementation, Java dependencies and recipes
are unchanged from `e07550f`; no manual Maven, image, runtime or L5 proof was
rerun. Full-suite and generated-app execution belong to automatic final-head CI.
The original seven-finding CI result remains a failed historical observation.
M2 findings, ownership/publication authority and reporting activation remain
separate; no risk or release clearance is implied.

## Bounded correction on 2026-10-25

This historical correction preserved the then-supported Python 3.10 floor;
the October 28 decision above supersedes that support policy, not its results.

The required audit at PR #336's `47150f9` reported two matches across 74 packages
but retained no identities. A fresh pinned-reference diagnostic also reported
two matches, now identified as `fastmcp==3.2.3` / `GHSA-7xgj-8392-5q4r` and
`opentelemetry-api==1.44.0` / `GHSA-xcq7-p3pf-p88h` (`CVE-2026-114603`). Counts
agree; exact identity equality with the earlier unnamed CI result is unprovable.

The upstream advisories and PyPI release metadata select existing-major fixes
**FastMCP 3.4.10** and **OpenTelemetry API 1.45.1**, both declaring Python >=3.10.
Only FastMCP's direct declaration changes. OpenTelemetry remains transitive.
The 3.4.10 distribution requires `fastmcp-slim[client,server]==3.4.10`, whose
server extra introduces `griffelib>=2.0.0`; select compatible `griffelib==2.0.0`.
The clean reference closure therefore contains **76** packages. All other
selected versions are unchanged; no general resolver refresh or major4 move.
Use a clean virtual environment for reproduction; this proof does not certify
in-place upgrades across FastMCP's distribution split.

One candidate audit, reused by the existing SBOM/license evidence generator,
completed with 76/76 packages, zero matches and exit0 at
`2026-10-25T02:09:11.727726Z`. Its actual source is
`aecb3f15956cc805139d488a08380f60aa657391`. The SBOM, license inventory and
provenance match the installed constrained environment and lock. This is a
point-in-time reference result, not all-platform or broader M2 clearance.

Executed **CPython 3.10.21** checks installed the exact corrected packages,
passed `pip check`, registered all seven Engine MCP tools and called two catalog
tools through an in-process client. Valid trace-context propagation and an
oversized-header rejection passed. Focused MCP/audit tests: 59 passed, one
stdlib-TOML skip. These are consumer compatibility checks, not a full3.10 suite,
stdio/session-authorization certification, DoS benchmark or platform-wide audit.

Neither changed dependency is directly used by application generation: FastMCP
serves Engine's local MCP entrypoint; OpenTelemetry is its telemetry dependency.
With networking disabled, the old and corrected environments generated all
30 configurations identically: **1,044 file hashes**, including POMs and recipes.
Generator implementation bytes remain unchanged. This justifies carrying forward
the four clean-plugin build/image proofs at actual generator `b7c48b5`; no manual
Maven, image or runtime campaign was repeated and later commits are not relabeled
as their assessed source. See the [compact receipt](python-audit-correction-2026-10-25.json)
for source hashes, ranges, inputs, private report bindings and proof boundaries.

Primary sources: [FastMCP advisory](https://github.com/PrefectHQ/fastmcp/security/advisories/GHSA-7xgj-8392-5q4r),
[OpenTelemetry advisory](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-xcq7-p3pf-p88h),
[FastMCP metadata](https://pypi.org/pypi/fastmcp/3.4.10/json),
[slim metadata](https://pypi.org/pypi/fastmcp-slim/3.4.10/json),
[OpenTelemetry metadata](https://pypi.org/pypi/opentelemetry-api/1.45.1/json).
Full retrieved bodies and detailed diagnostic reports remain private, not in Git.

## Bounded correction on 2026-10-20

A fresh pinned-reference reproduction of the existing lock reported one match:
`certifi==2026.7.22`, advisory `GHSA-6q48-6c7w-9gw2`, scanner exit 1 with
complete coverage of the 74 selected packages. Public PyPI version metadata,
retrieved on **2026-10-20 UTC**, recommends `2026.10.19`. The upstream advisory
names `2026.10.18` as patched: that release removed the affected CA roots, while
PyPI describes `2026.10.19` restoring unaffected roots. These sources differ on
the fix floor; `2026.10.19` is the selected available, non-yanked release that
satisfies the live scanner recommendation, not a universal earliest-fix claim.
The correction selects only `certifi==2026.10.19` in the reference lock. Direct
requirements, scanner/tool pins, exclusions and fail-closed checks are unchanged;
no suppression or risk acceptance is introduced. The package count is observed,
not a target to preserve by adding dependencies.

The selected release metadata declares Python `>=3.7`, no dependencies, and a
`py3-none-any` wheel. An executed check on **CPython 3.10.21** in the existing
official Python reference image
`python@sha256:0a06143d04e5207c0561a9803a007af1d3e7941634fd1a7f801079dca3644bf5`
installed `certifi==2026.10.19` with `httpx==0.28.1`, passed `pip check`, loaded
the bundle into an SSL context (120 CA roots), verified the affected root was
absent, and initialized/closed an HTTP client without a network request. This
is executed minimum-Python coverage of the affected package and its consumer,
not a full Python 3.10 suite or a universal cross-platform reference-lock claim.

A fresh corrected reference install passed `pip check` and the unchanged strict
audit with complete coverage of 74 packages, zero findings and exit 0 on
2026-10-20 UTC. This is a point-in-time Python-only result, not broader M2
closure or release approval.

Public advisory metadata: [affected release](https://pypi.org/pypi/certifi/2026.7.22/json)
and [selected release / compatibility metadata](https://pypi.org/pypi/certifi/2026.10.19/json).
The [official upstream advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2)
records the CA-root-removal facts and its `2026.10.18` patch floor.
Detailed original and corrected scanner output is retained in task-private
scratch. The coordinated lock-only source commit is
`232d7d6ccc9458970ee6b7efa8a7189d84b9cdd3`; that dated evidence refresh used
that real source identity and matching requirements/lock digests, not the
pre-correction starting revision. Evidence-tool implementations and direct
requirements are unchanged from that commit.

The compact [correction receipt](python-audit-correction-2026-10-20.json)
records source identities, authoritative-source body hashes, before/after raw
report hashes, inventory results and executed minimum-Python scope. Its private
retention references are archive-relative; maintainer archive persistence is a
separate parent-owned action.

## Historical evidence

The previous `python-current` snapshot is preserved byte-for-byte under
[`python-current/history/2026-09-23/`](python-current/history/2026-09-23/), with
its original provenance, timestamp, inventories, and matching requirements and
lock. Its zero-finding result describes that historical scan, not a fresh audit
of the old dependencies. The October reproduction above does not rewrite it.

The October20 snapshot is also preserved byte-for-byte under
[`python-current/history/2026-10-20/`](python-current/history/2026-10-20/), with
its matching requirements/lock and actual original provenance. The later live
findings do not rewrite that earlier zero-match observation.

The October25 snapshot is retained in the same history directory with its
matching original requirements/lock. Its Python 3.10 checks describe the policy
and environment at that date, not today's supported interpreter range.

The old root-level [SBOM](sbom.cdx.json), [audit](pip-audit.md) and
[license inventory](dependency-licenses.md) remain the dated historical record,
including the earlier pytest advisory. The fresh assessment does not backdate
or erase them. A scan with no reported advisory is not a claim of safety,
exploitability review, or release acceptance. Maven, images and overall M2
remain separate.
