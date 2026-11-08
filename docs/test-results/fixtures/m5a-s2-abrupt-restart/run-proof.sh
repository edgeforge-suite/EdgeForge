#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POSTGRES_IMAGE="postgres@sha256:e62fbf9d3e2b49816a32c400ed2dba83e3b361e6833e624024309c35d334b412"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/edgeforge-m5a-s2-feasibility-XXXXXXXX")"
CONTAINER_NAME="edgeforge-m5a-s2-proof-$$"
JDBC_PROBE_TIMEOUT_SECONDS=2
INITIAL_PID=""

cleanup() {
  if [[ -n "${INITIAL_PID}" ]] && kill -0 "${INITIAL_PID}" 2>/dev/null; then
    kill -9 "${INITIAL_PID}" 2>/dev/null || true
    wait "${INITIAL_PID}" 2>/dev/null || true
  fi
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

cp "${SCRIPT_DIR}/pom.xml" "${WORK_DIR}/pom.xml"
cp -R "${SCRIPT_DIR}/src" "${WORK_DIR}/src"

(
  cd "${WORK_DIR}"
  mvn -q package dependency:build-classpath -Dmdep.outputFile=target/classpath.txt
  mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.7.1:copy \
    -Dartifact=com.h2database:h2:2.2.224 \
    -DoutputDirectory=target/proof-deps
)
CLASSPATH="${WORK_DIR}/target/classes:$(cat "${WORK_DIR}/target/classpath.txt")"
H2_JAR="${WORK_DIR}/target/proof-deps/h2-2.2.224.jar"
BATCH_CORE_JAR="$(tr ':' '\n' <"${WORK_DIR}/target/classpath.txt" \
  | grep '/spring-batch-core-5.1.2.jar$')"
mkdir -p "${WORK_DIR}/target/h2-batch-schema"
(
  cd "${WORK_DIR}/target/h2-batch-schema"
  jar xf "${BATCH_CORE_JAR}" org/springframework/batch/core/schema-h2.sql
)
H2_BATCH_SCHEMA="${WORK_DIR}/target/h2-batch-schema/org/springframework/batch/core/schema-h2.sql"

docker run --detach --name "${CONTAINER_NAME}" \
  --env POSTGRES_DB=proofdb \
  --env POSTGRES_USER=proof \
  --env POSTGRES_PASSWORD=proof \
  --publish 127.0.0.1::5432 \
  "${POSTGRES_IMAGE}" >/dev/null

HOST_PORT="$(docker port "${CONTAINER_NAME}" 5432/tcp | sed -n 's/.*://p' | tail -n 1)"
JDBC_URL="jdbc:postgresql://127.0.0.1:${HOST_PORT}/proofdb?connectTimeout=${JDBC_PROBE_TIMEOUT_SECONDS}&socketTimeout=${JDBC_PROBE_TIMEOUT_SECONDS}"

run_java() {
  JDBC_URL="${JDBC_URL}" JDBC_USER=proof JDBC_PASSWORD=proof \
    JDBC_PROBE_TIMEOUT_SECONDS="${JDBC_PROBE_TIMEOUT_SECONDS}" \
    java -cp "${CLASSPATH}" proof.AbruptRestartProof "$@"
}

postgres_jdbc_ready() {
  run_java probe | grep -Fxq 'POSTGRES_JDBC_READY'
}

for _ in $(seq 1 60); do
  if postgres_jdbc_ready >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
postgres_jdbc_ready >/dev/null

query() {
  docker exec "${CONTAINER_NAME}" psql -v ON_ERROR_STOP=1 -U proof -d proofdb \
    -At -F '|' -c "$1"
}

assert_equal() {
  if [[ "$1" != "$2" ]]; then
    printf 'assertion failed: expected %s, got %s\n' "$2" "$1" >&2
    exit 1
  fi
}

expect_running_refusal() {
  local date="$1"
  local log="$2"
  local status
  set +e
  run_java launch RUN-001 "${date}" >"${log}" 2>&1
  status=$?
  set -e
  assert_equal "${status}" "23"
  grep -Fq 'JobExecutionAlreadyRunningException' "${log}"
  grep -Fq 'id=1' "${log}"
}

run_java init

assert_equal "$(query "SELECT character_maximum_length
FROM information_schema.columns
WHERE table_name = 'batch_job_execution_params'
  AND column_name = 'parameter_value'")" "2500"

java -cp "${H2_JAR}" org.h2.tools.Shell \
  -url 'jdbc:h2:mem:h2_batch_schema' -user sa -password '' \
  -sql "RUNSCRIPT FROM '${H2_BATCH_SCHEMA}';
        SELECT CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'BATCH_JOB_EXECUTION_PARAMS'
          AND COLUMN_NAME = 'PARAMETER_VALUE';" \
  >"${WORK_DIR}/h2-batch-schema.log" 2>&1
grep -Eq '^2500[[:space:]]*$' "${WORK_DIR}/h2-batch-schema.log"

java -cp "${H2_JAR}" org.h2.tools.Shell \
  -url 'jdbc:h2:mem:h2_length_reject' -user sa -password '' \
  -sql "CREATE TABLE h2_utf16 (v VARCHAR(1));
        INSERT INTO h2_utf16 VALUES (STRINGDECODE('\\ud83d\\ude00'));" \
  >"${WORK_DIR}/h2-utf16-reject.log" 2>&1
grep -Fq 'Value too long for column "V CHARACTER VARYING(1)"' \
  "${WORK_DIR}/h2-utf16-reject.log"
grep -Fq "(2)" "${WORK_DIR}/h2-utf16-reject.log"

java -cp "${H2_JAR}" org.h2.tools.Shell \
  -url 'jdbc:h2:mem:h2_length_accept' -user sa -password '' \
  -sql "CREATE TABLE h2_utf16 (v VARCHAR(2));
        INSERT INTO h2_utf16 VALUES (STRINGDECODE('\\ud83d\\ude00'));" \
  >"${WORK_DIR}/h2-utf16-accept.log" 2>&1
if grep -Fq 'Error:' "${WORK_DIR}/h2-utf16-accept.log"; then
  cat "${WORK_DIR}/h2-utf16-accept.log" >&2
  exit 1
fi
grep -Fq '(Update count: 1' "${WORK_DIR}/h2-utf16-accept.log"

query "CREATE TABLE run_id_char_equivalence (
  run_id CHAR(8) NOT NULL,
  dedup_key INTEGER NOT NULL,
  UNIQUE (run_id, dedup_key)
);" >/dev/null
query "INSERT INTO run_id_char_equivalence (run_id, dedup_key) VALUES ('RUN-1', 1);" >/dev/null
set +e
query "INSERT INTO run_id_char_equivalence (run_id, dedup_key) VALUES ('RUN-1 ', 1);" \
  >"${WORK_DIR}/char-equivalence.log" 2>&1
CHAR_COLLISION_STATUS=$?
set -e
if [[ "${CHAR_COLLISION_STATUS}" -eq 0 ]]; then
  printf 'assertion failed: PostgreSQL CHAR trailing-space variant did not collide\n' >&2
  exit 1
fi
grep -Fq 'duplicate key value violates unique constraint' "${WORK_DIR}/char-equivalence.log"
query "DROP TABLE run_id_char_equivalence;" >/dev/null

run_java launch RUN-001 2026-08-17 >"${WORK_DIR}/initial.log" 2>&1 &
INITIAL_PID=$!

for _ in $(seq 1 60); do
  if grep -Fq 'DATA_STEP_WAITING' "${WORK_DIR}/initial.log"; then
    break
  fi
  if ! kill -0 "${INITIAL_PID}" 2>/dev/null; then
    cat "${WORK_DIR}/initial.log" >&2
    exit 1
  fi
  sleep 1
done
grep -Fq 'IDENTITY_STEP_ACCEPTED=2026-08-17' "${WORK_DIR}/initial.log"
grep -Fq 'DATA_STEP_WAITING' "${WORK_DIR}/initial.log"

kill -9 "${INITIAL_PID}"
wait "${INITIAL_PID}" 2>/dev/null || true
INITIAL_PID=""

assert_equal "$(query "SELECT status FROM batch_job_execution WHERE job_execution_id = 1")" "STARTED"
assert_equal "$(query "SELECT status FROM batch_step_execution WHERE step_execution_id = 1")" "COMPLETED"
assert_equal "$(query "SELECT status FROM batch_step_execution WHERE step_execution_id = 2")" "STARTED"

expect_running_refusal 2026-08-17 "${WORK_DIR}/same-date.log"
expect_running_refusal 2026-08-18 "${WORK_DIR}/changed-date.log"
assert_equal "$(query 'SELECT count(*) FROM batch_job_instance')" "1"
assert_equal "$(query 'SELECT count(*) FROM batch_job_execution')" "1"
assert_equal "$(query 'SELECT count(*) FROM batch_step_execution')" "2"

query "BEGIN;
UPDATE batch_step_execution
SET status = 'FAILED', exit_code = 'FAILED',
    exit_message = 'operator classified stale after owner confirmation',
    end_time = CURRENT_TIMESTAMP, last_updated = CURRENT_TIMESTAMP,
    version = version + 1
WHERE step_execution_id = 2 AND status = 'STARTED';
UPDATE batch_job_execution
SET status = 'FAILED', exit_code = 'FAILED',
    exit_message = 'operator classified stale after owner confirmation',
    end_time = CURRENT_TIMESTAMP, last_updated = CURRENT_TIMESTAMP,
    version = version + 1
WHERE job_execution_id = 1 AND status = 'STARTED';
COMMIT;" >/dev/null

run_java launch RUN-001 2026-08-18 >"${WORK_DIR}/classified-relaunch.log" 2>&1
grep -Fq 'businessDate mismatch: frozen=2026-08-17, supplied=2026-08-18' \
  "${WORK_DIR}/classified-relaunch.log"
grep -Fq 'LAUNCH_RETURNED=FAILED' "${WORK_DIR}/classified-relaunch.log"
assert_equal "$(query 'SELECT count(*) FROM batch_job_instance')" "1"
assert_equal "$(query 'SELECT count(*) FROM batch_job_execution')" "2"
assert_equal "$(query 'SELECT count(*) FROM batch_step_execution')" "3"
assert_equal "$(query "SELECT count(*) FROM batch_step_execution WHERE job_execution_id = 2 AND step_name = 'dataStep'")" "0"

printf '%s\n' \
  'M5A_S2_FEASIBILITY=PASS' \
  'POSTGRES_JDBC_ENDPOINT_READY=PROVEN' \
  'POSTGRES_JDBC_TIMEOUTS_SECONDS=2' \
  'POSTGRES_BATCH_PARAMETER_VALUE_MAX=2500' \
  'H2_BATCH_PARAMETER_VALUE_MAX=2500' \
  'H2_UTF16_VARCHAR1_SUPPLEMENTARY=REJECTED' \
  'H2_UTF16_VARCHAR2_SUPPLEMENTARY=ACCEPTED' \
  'POSTGRES_CHAR_TRAILING_SPACE_COLLISION=PROVEN' \
  'ABRUPT_JOB_STATUS=STARTED' \
  'IDENTITY_STEP_STATUS=COMPLETED' \
  'DATA_STEP_STATUS=STARTED' \
  'SAME_DATE_RELAUNCH=JobExecutionAlreadyRunningException' \
  'CHANGED_DATE_RELAUNCH=JobExecutionAlreadyRunningException' \
  'POST_CLASSIFICATION_RELAUNCH=FAILED_DATE_MISMATCH' \
  'FINAL_JOB_INSTANCES=1' \
  'FINAL_JOB_EXECUTIONS=2' \
  'FINAL_STEP_EXECUTIONS=3'
