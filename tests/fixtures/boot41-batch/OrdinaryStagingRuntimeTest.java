package @PACKAGE@;

import static org.junit.jupiter.api.Assertions.*;
import java.net.URI;
import java.net.http.*;
import java.time.LocalDate;
import java.util.UUID;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import @PORT_IMPORT@;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"server.address=127.0.0.1", "app.eod.chunk-size=1"})
class OrdinaryStagingRuntimeTest {
    @LocalServerPort int port;
    @Autowired JdbcTemplate jdbc;
    @Test void bodylessLegacyJobPreservesActualStagingValues() throws Exception {
        var id = UUID.fromString("00000000-0000-0000-0000-000000000099");
        jdbc.update("INSERT INTO widget(widget_id,payload_key) VALUES (?,?)", id.toString(), "ordinary-proof");
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/batch/run/widgetEodJob"))
                .POST(HttpRequest.BodyPublishers.noBody()).build();
        var response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode(), response.body());
        assertTrue(response.body().contains("COMPLETED"), response.body());
        var rows = jdbc.queryForList("SELECT * FROM widget_staging WHERE payload_key='ordinary-proof'");
        assertEquals(1, rows.size());
        var row = rows.get(0);
        assertEquals(id.toString(), row.get("widget_id").toString());
        assertEquals("READY", row.get("staging_status"));
        assertEquals(LocalDate.now().toString(), row.get("business_date").toString());
        assertNotNull(row.get("created_at"));
        assertEquals(UUID.fromString(row.get("staging_row_id").toString()).toString(), row.get("staging_row_id").toString());
        long instanceId = Long.parseLong(row.get("run_id").toString());
        assertTrue(instanceId > 0);
        var responseId = Pattern.compile("\"jobId\"\\s*:\\s*(\\d+)").matcher(response.body());
        assertTrue(responseId.find(), response.body());
        assertEquals(instanceId, Long.parseLong(responseId.group(1)));
        assertEquals(instanceId, jdbc.queryForObject("SELECT job_instance_id FROM batch_job_execution WHERE status='COMPLETED'", Long.class));
        assertEquals(1L, jdbc.queryForObject("SELECT COUNT(*) FROM batch_job_execution_params WHERE parameter_name='run.at' AND identifying='Y'", Long.class));
        assertEquals(1L, jdbc.queryForObject("SELECT COUNT(*) FROM batch_job_execution WHERE status='COMPLETED'", Long.class));
        jdbc.update("DELETE FROM widget WHERE widget_id=?", id.toString());
    }
}
