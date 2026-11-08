package @PACKAGE@;

import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.UUID;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"server.address=127.0.0.1", "app.eod.chunk-size=1"})
class BatchPreviewRuntimeTest {
    @LocalServerPort int port;
    @Autowired JdbcTemplate jdbc;
    @Autowired Flyway flyway;
    @Autowired JobRepository repository;
    @Autowired @HISTORY_TYPE@ history;
    private final HttpClient http = HttpClient.newHttpClient();

    private HttpResponse<String> post(String job, String body) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/batch/run/" + job))
                .header("Content-Type", "application/json");
        return http.send(builder.POST(body == null ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> run(String id, String date) throws Exception {
        return post("widgetEodJob", "{\"runId\":\"" + id + "\",\"businessDate\":\"" + date + "\"}");
    }

    private long count(String table) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Long.class);
    }

    @Test void jdbcAndSingleSchemaOwner() {
        assertTrue(repository.getClass().getName().contains("Proxy")
                || repository.getClass().getName().contains("SimpleJobRepository"));
        assertEquals(0, flyway.migrate().migrationsExecuted);
        assertEquals(0, flyway.migrate().migrationsExecuted);
        assertEquals(2500L, jdbc.queryForObject("SELECT character_maximum_length FROM information_schema.columns "
                + "WHERE UPPER(table_name)='BATCH_JOB_EXECUTION_PARAMS' AND UPPER(column_name)='PARAMETER_VALUE'", Long.class));
        assertEquals(1L, jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.sequences "
                + "WHERE UPPER(sequence_name)='@INSTANCE_SEQUENCE@'", Long.class));
        assertEquals(0L, jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.sequences "
                + "WHERE UPPER(sequence_name)='@ABSENT_SEQUENCE@'", Long.class));
    }

    @Test void closedHttpRequestAndExactUtf16Bound() throws Exception {
        long before = count("batch_job_instance");
        for (String bad : new String[] {null, "{}", "[]", "{\"runId\":4,\"businessDate\":\"2026-09-27\"}",
                "{\"runId\":\" R\",\"businessDate\":\"2026-09-27\"}",
                "{\"runId\":\"R \",\"businessDate\":\"2026-09-27\"}",
                "{\"runId\":\"\\u2003R\",\"businessDate\":\"2026-09-27\"}",
                "{\"runId\":\"R\",\"businessDate\":\"invalid\"}",
                "{\"runId\":\"R\",\"businessDate\":\"2026-09-27\",\"extra\":true}"}) {
            var response = post("widgetEodJob", bad);
            assertEquals(400, response.statusCode(), response.body());
            assertTrue(response.body().contains("invalid_batch_request"));
        }
        assertEquals(400, run("x".repeat(65), "2026-09-27").statusCode());
        assertEquals(400, run("\uD83D\uDE00".repeat(33), "2026-09-27").statusCode());
        assertEquals(before, count("batch_job_instance"));
        String exact = "\uD83D\uDE00".repeat(32);
        assertEquals(200, run(exact, "2026-09-27").statusCode());
        assertEquals(exact, jdbc.queryForObject("SELECT parameter_value FROM batch_job_execution_params "
                + "WHERE parameter_name='runId' AND parameter_value=?", String.class, exact));
        assertEquals(409, run(exact, "2026-09-28").statusCode());
        assertEquals(before + 1, count("batch_job_instance"));
        String serialized = jdbc.queryForObject("SELECT c.short_context FROM batch_job_execution_context c "
                + "JOIN batch_job_execution_params p ON p.job_execution_id=c.job_execution_id "
                + "WHERE p.parameter_name='runId' AND p.parameter_value=?", String.class, exact);
        byte[] javaStream = java.util.Base64.getDecoder().decode(serialized);
        assertArrayEquals(new byte[] {(byte) 0xac, (byte) 0xed, 0, 5},
                java.util.Arrays.copyOf(javaStream, 4), "Default context must remain Java serialization");
        try (var input = new java.io.ObjectInputStream(new java.io.ByteArrayInputStream(javaStream))) {
            assertInstanceOf(java.util.Map.class, input.readObject());
        }
    }

    @Test void failedRestartFrozenDateAndIdempotentStaging() throws Exception {
        // Only this isolated test database is modified. Source rows stay immutable
        // from first launch through restart; a transient sink failure is removed.
        jdbc.execute("ALTER TABLE widget_staging ADD CONSTRAINT proof_sink_failure CHECK(payload_key <> 'FAIL')");
        for (int i=1; i<=3; i++) {
            jdbc.update("INSERT INTO widget(widget_id,payload_key) VALUES (?,?)",
                    UUID.fromString("00000000-0000-0000-0000-00000000000" + i), i == 2 ? "FAIL" : "OK" + i);
        }
        String id = "restart-" + UUID.randomUUID();
        var failed = run(id, "2026-09-27");
        assertEquals(200, failed.statusCode(), failed.body());
        assertTrue(failed.body().contains("FAILED"), failed.body());
        assertEquals(1L, jdbc.queryForObject("SELECT COUNT(*) FROM widget_staging WHERE run_id=?", Long.class, id));
        long rows = count("widget_staging");
        jdbc.execute("ALTER TABLE widget_staging DROP CONSTRAINT proof_sink_failure");
        var mismatch = run(id, "2026-09-28");
        assertTrue(mismatch.body().contains("FAILED"), mismatch.body());
        assertEquals(rows, count("widget_staging"));
        assertTrue(jdbc.queryForObject("SELECT exit_message FROM batch_job_execution ORDER BY job_execution_id DESC LIMIT 1",
                String.class).contains("businessDate mismatch"));
        var complete = run(id, "2026-09-27");
        assertTrue(complete.body().contains("COMPLETED"), complete.body());
        assertEquals(3L, jdbc.queryForObject("SELECT COUNT(*) FROM widget_staging WHERE run_id=?", Long.class, id));
        assertEquals(1L, jdbc.queryForObject("SELECT COUNT(DISTINCT job_instance_id) FROM batch_job_execution e "
                + "JOIN batch_job_execution_params p ON p.job_execution_id=e.job_execution_id WHERE p.parameter_name='runId' AND p.parameter_value=?",
                Long.class, id));
        assertEquals(0L, jdbc.queryForObject("SELECT COUNT(*) FROM batch_job_execution_params p "
                + "JOIN batch_job_execution_params r ON r.job_execution_id=p.job_execution_id "
                + "WHERE r.parameter_name='runId' AND r.parameter_value=? AND "
                + "((p.parameter_name='businessDate' AND p.identifying<>'N') OR p.parameter_name='run.at')", Long.class, id));
        assertEquals(409, run(id, "2026-09-27").statusCode());
        jdbc.update("DELETE FROM widget WHERE payload_key IN ('OK1','FAIL','OK3')");
    }

    @ParameterizedTest
    @ValueSource(strings = {"missing-date", "string-date", "malformed-date", "missing-runId", "conflicting-context", "malformed-context"})
    void corruptedOriginalRemainsRetainedAndRefusesBeforeStaging(String fault) throws Exception {
        String id = "corrupt-" + UUID.randomUUID();
        String constraint = "proof_corrupt_" + UUID.randomUUID().toString().replace("-", "");
        UUID sourceId = UUID.randomUUID();
        jdbc.update("INSERT INTO widget(widget_id,payload_key) VALUES (?,?)", sourceId, "corrupt-control");
        jdbc.execute("ALTER TABLE widget_staging ADD CONSTRAINT " + constraint + " CHECK(run_id <> '" + id + "')");
        var failed = run(id, "2026-09-27");
        assertTrue(failed.body().contains("FAILED"), failed.body());
        jdbc.execute("ALTER TABLE widget_staging DROP CONSTRAINT " + constraint);
        long executionId = jdbc.queryForObject("SELECT job_execution_id FROM batch_job_execution_params WHERE parameter_name='runId' AND parameter_value=?", Long.class, id);
        if (fault.equals("missing-date")) {
            jdbc.update("DELETE FROM batch_job_execution_params WHERE job_execution_id=? AND parameter_name='businessDate'", executionId);
        } else if (fault.equals("string-date")) {
            jdbc.update("UPDATE batch_job_execution_params SET parameter_type='java.lang.String' WHERE job_execution_id=? AND parameter_name='businessDate'", executionId);
        } else if (fault.equals("malformed-date")) {
            jdbc.update("UPDATE batch_job_execution_params SET parameter_value='invalid' WHERE job_execution_id=? AND parameter_name='businessDate'", executionId);
        } else if (fault.equals("missing-runId")) {
            jdbc.update("DELETE FROM batch_job_execution_params WHERE job_execution_id=? AND parameter_name='runId'", executionId);
        } else {
            var original = history.getJobExecution(executionId);
            if (fault.equals("conflicting-context")) original.getExecutionContext().putString("frozenBusinessDate", "2026-09-28");
            else original.getExecutionContext().put("frozenBusinessDate", 42L);
            repository.updateExecutionContext(original);
        }
        var retainedParameters = jdbc.queryForList("SELECT * FROM batch_job_execution_params WHERE job_execution_id=? ORDER BY parameter_name", executionId);
        var retainedContext = jdbc.queryForList("SELECT * FROM batch_job_execution_context WHERE job_execution_id=?", executionId);
        var source = jdbc.queryForList("SELECT * FROM widget ORDER BY widget_id");
        var staging = jdbc.queryForList("SELECT * FROM widget_staging ORDER BY staging_row_id");
        var rejected = run(id, "2026-09-27");
        assertTrue(rejected.statusCode() == 500 || (rejected.statusCode() == 200 && rejected.body().contains("FAILED")), rejected.body());
        assertEquals(retainedParameters, jdbc.queryForList("SELECT * FROM batch_job_execution_params WHERE job_execution_id=? ORDER BY parameter_name", executionId));
        assertEquals(retainedContext, jdbc.queryForList("SELECT * FROM batch_job_execution_context WHERE job_execution_id=?", executionId));
        assertEquals(source, jdbc.queryForList("SELECT * FROM widget ORDER BY widget_id"));
        assertEquals(staging, jdbc.queryForList("SELECT * FROM widget_staging ORDER BY staging_row_id"));
        System.out.println("CORRUPT_HISTORY_CONTROL " + fault + " originalExecution=" + executionId
                + " response=" + rejected.statusCode() + ":" + rejected.body() + " retainedParameters=" + retainedParameters
                + " retainedContext=" + retainedContext);
        jdbc.update("DELETE FROM widget WHERE widget_id=?", sourceId.toString());
    }
}
