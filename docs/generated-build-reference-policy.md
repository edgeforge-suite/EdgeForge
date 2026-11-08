# Generated Build References

The versioned mapping in `appbuilder/generation/container_policy.py` owns the
reviewed Java 17/21 Noble builder and runtime references. Both build emitters use
the same `ef-v5-noble-1` mapping. Recipes pin the multi-platform **index**, not an
architecture-specific child. The mapping records the selected linux/amd64 child
and configuration separately; it does not certify ARM64 or other platforms.

Engine owns review before release and after material security changes. There is
no automatic refresh, periodic service commitment or risk acceptance. A moved
tag fails collection before application builds. Changing a published selection
requires a new reviewed mapping and corresponding proof, not silent substitution.

## Build And Application Scopes

`ef-v5-plugin-realms-1` in `appbuilder/generation/plugin_policy.py` targets only
confirmed introducing plugin realms inherited from the existing parent:

| Realm | Explicit build-only dependencies |
| --- | --- |
| Clean | Plexus Utils 4.0.3 |
| Compiler | Commons IO 2.14.0; Plexus Utils 4.0.3 |
| Resources | Plexus Utils 3.6.1 |
| Boot packaging | Commons Lang3 3.18.0; Plexus Utils 3.6.1; Jackson core/databind 3.1.7 |

The distribution's Plexus Utils 3.6.1 comes from the selected Maven 3.9.16
builder, not a POM override or manually replaced JAR. Application policy
`ef-v5-maven-1`, Boot 4.1.1, manifest 2.0 and packaged application dependencies
are unchanged. Application dependency management cannot repair plugin realms.

The current shared policy adds Plexus Utils 4.0.3 only to the inherited Clean
Plugin realm (qualified plugin 3.5.0); it does not change the plugin version,
other realms, Maven distribution, application dependencies or base references.
Both build emitters consume that policy. Do not apply an application-wide
override or delete cache entries as remediation.

The October 20 clean-plugin 4.0.2 finding remains unchanged in its historical
ledger. The subsequent [clean-plugin overlay](handover-evidence/clean-plugin-plexus-2026-10-24/README.md)
records executed clean/verify and replacement-copy proof for four new builder
artifacts on Java 17/21, separately from configuration coverage of 30 cases.
It does not establish that the 30 historical builders were rebuilt, close other
findings or clear M2. Realm inclusion proves loading, not vulnerable-function use.

## Proof Boundaries

Fresh exact-toolchain generated tests, preservation/determinism checks and
effective POM/descriptor/lifecycle realm receipts are required. Docker's
`-DskipTests clean package` gives no executed-test credit. Native host Maven proof
does not qualify the selected Linux Maven/JDK images. If exact-toolchain CI does
not supply the necessary coverage, exercise representative CRUD, SOAP,
passthrough and Kafka tests on Java 17/21 with the selected builder images.

Keep the existing 30-case/60-stage image contract, without assumed equivalence.
The three production startup checks do not establish Kafka LZ4 traffic. Fresh
default-LZ4 observer and forced-JNI Java 17/21 helpers are separate proof images,
not the actual scanned production images. Their additive instrumentation must
leave production POM, configuration and recipe unchanged. Noble's libc change
requires fresh applicable native proof; ordinary Java launch is not forced JNI.

Retain all old findings and physical-copy identities. New image absence is not
historical closure; scanner/feed disagreements and native gaps remain explicit.
Five positive LZ4 feed records require current packaged 1.11.4 identity before
per-ID adoption; no LZ4 upgrade or new inventory query is implied. The Jackson
source contradiction remains OPEN pending an authoritative resolution.

## Collection And Retention

The existing collector/publisher accept only the complete current mapping or the
explicit historical four-reference policy. Historical declarations with no
reference fields retain their exact previous reference contract. Mixed policies,
arbitrary references and mismatched selected child/config/index identities fail.
Normalized plans retain validated `build_base`, `runtime_base` and
`base_reference_policy` fields through publication; omission does not silently
turn a Noble declaration into the historical policy. Implicit historical plans
retain their previous shape and exact references.
Old replay receipts and fixed historical acceptance tests remain unchanged.

Do not start a campaign below the unchanged 26 GiB per-case entry requirement,
lower the hard 20 GiB floor, or download large scanner databases without storage
readiness. Run one consolidated campaign after the implementation settles.
Exit 1 retains complete findings; exit 2 remains incomplete, never clean.

Reuse the core/private-archive split with a **new** manifest and dynamically
verified counts. The old bundle's 161/1,997 counts are historical assertions,
not new-bundle requirements. The existing read-only verifier accepts explicit
`--manifest` and root-relative `--evidence-dir` arguments; default invocation
continues to verify the original October 17 core. Full sanitized evidence belongs
in a verified durable private archive, not a raw Git commit. Integrity verification
is not independent review, M2 completion, release clearance or risk acceptance.
