# EdgeForge Quickstart

Generate and locally run the independently authored [Workspace/Item example](../examples/input-projects/workspace-items/README.md).
Revised 2026-11-01. The original June 8 walkthrough used a different, privately
retained external application; its dated results do not validate this example.
See [publication preparation](public-content-preparation.md) for current proof.

## 1. Prerequisites

Use Python 3.11+, JDK 17 and Maven 3.9+. The example targets Java 17/H2.
`make setup` downloads Python packages; Maven may download from Central. An
offline build requires an already populated compatible cache. Do not call a
package-only or skipped-test build executed-test proof.

```bash
python3 --version
java -version
mvn -version
make setup
```

## 2. Generate

From the repository root:

```bash
make generate-sample
```

The Make target writes `/tmp/edgeforge-sample-app`. Schema validation is a CLI
option, not a Make option. To choose a separate output and validate the manifest:

```bash
.venv/bin/python -m appbuilder.cli generate \
  --manifest examples/input-projects/workspace-items/app-definition.yaml \
  --output /tmp/edgeforge-workspace-items \
  --validate-schema
```

Expect a generated project and `Harness: PASSED (static compatibility checks)`.
That static result is not compilation or runtime acceptance.
Use an absent output directory for this fresh-generation walkthrough. Regeneration
preserves existing migrations; it does not repair SQL already retained in an older
generated application.

## 3. Build And Run Locally

```bash
cd /tmp/edgeforge-sample-app
mvn clean verify
java -jar target/*.jar --server.address=127.0.0.1 --server.port=8080
```

Keep tests enabled and check the actual test count/results. Diagnose test
failures rather than routinely adding `-DskipTests`. The generated application
is standalone: EdgeForge, Studio, KS and MCP are not needed at runtime.

In another terminal:

```bash
curl --fail http://127.0.0.1:8080/actuator/health
```

Expect `status: UP`. The local console is at <http://127.0.0.1:8080/> and offers
Workspace and Item cards. Its live-data demo handlers remain disabled by
default; ordinary create/get/list cards do not require enabling them.

## 4. Exercise The Contracts

```bash
WORKSPACE=$(curl --fail -s http://127.0.0.1:8080/workspaces \
  -H 'Content-Type: application/json' -d '{"title":"Shared desk","state":"OPEN"}')
WID=$(printf '%s' "$WORKSPACE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["workspaceId"])')
curl --fail "http://127.0.0.1:8080/workspaces/$WID"
curl --fail -s http://127.0.0.1:8080/items \
  -H 'Content-Type: application/json' \
  -d "{\"workspaceId\":\"$WID\",\"label\":\"Draft outline\",\"priority\":3}"
curl --fail http://127.0.0.1:8080/items
```

Both creates return 201 and server-generated identities. Use the actual returned
identity, not a sample response ID. A missing workspace reference, too-short
title/label or priority outside 1..5 is rejected. GET uses the generated generic
CRUD routes; the authored contract declares only the two POST operations.
Explicit rules carry the sample's bounds/defaults and relationship. This is not
a claim that every OpenAPI schema constraint is enforced.

Stop the JVM with Ctrl+C when finished; the sample data is disposable/in-memory.

## Deployment Boundary

This walkthrough is local development/testing only. Authentication does not
restrict method/path exposure by itself. Supported deployment requires an
authenticated TLS gateway exposing only explicitly approved operations, with
the application port inaccessible except through that gateway. Review the full
emitted generic CRUD/demo/batch surface. Business/object/tenant authorization
remains adopter-owned; this example is not production certification.

## Next Steps

`make mcp` starts the local stdio Engine MCP server. See the
[root README](../README.md) for client configuration and the
[Suite architecture](suite-architecture.md) for repository responsibilities.
