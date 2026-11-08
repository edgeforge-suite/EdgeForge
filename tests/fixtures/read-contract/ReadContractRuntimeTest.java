package com.appbuilder.reads;

import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"server.address=127.0.0.1"})
class ReadContractRuntimeTest {
    @LocalServerPort int port;
    @Autowired JdbcTemplate jdbc;
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10)).build();

    @BeforeEach void overlappingKeysAndDifferentOwners() {
        jdbc.update("DELETE FROM account");
        jdbc.update("INSERT INTO account(id,customer_id) VALUES (?,?)", "ACC-7", "CUST-1");
        jdbc.update("INSERT INTO account(id,customer_id) VALUES (?,?)", "CUST-1", "CUST-9");
    }

    private HttpResponse<String> get(String path) throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(15)).header("X-Correlation-Id", "proof-only")
                .GET().build(), HttpResponse.BodyHandlers.ofString());
    }

    @Test void ownIdReturnsTheIntendedRecordNotAnOwnerMatch() throws Exception {
        var intended = get("/accounts/ACC-7");
        assertEquals(200, intended.statusCode(), intended.body());
        assertTrue(intended.body().contains("\"id\":\"ACC-7\""), intended.body());
        assertTrue(intended.body().contains("\"customerId\":\"CUST-1\""), intended.body());
        assertFalse(intended.body().contains("CUST-9"), intended.body());
        var overlapping = get("/accounts/CUST-1");
        assertEquals(200, overlapping.statusCode(), overlapping.body());
        assertTrue(overlapping.body().contains("\"customerId\":\"CUST-9\""), overlapping.body());
    }

    @Test void missingOwnIdIsNotAnArbitraryFirstRecord() throws Exception {
        assertEquals(404, get("/accounts/MISSING").statusCode());
    }

    @Test void computedReadAcceptsClassifiedMetadataWithoutChangingSelection() throws Exception {
        var result = get("/accounts/ACC-7/summary");
        assertEquals(200, result.statusCode(), result.body());
        assertTrue(result.body().contains("\"id\":\"ACC-7\""), result.body());
        assertTrue(result.body().contains("\"customerId\":\"CUST-1\""), result.body());
        assertFalse(result.body().contains("CUST-9"), result.body());
        assertEquals(404, get("/accounts/MISSING/summary").statusCode());
    }

    @Test void collectionHasHonestUnfilteredAndBoundedPageBehavior() throws Exception {
        var all = get("/accounts/history");
        assertEquals(200, all.statusCode(), all.body());
        assertTrue(all.body().contains("CUST-9"), all.body());
        assertTrue(all.body().contains("ACC-7"), all.body());
        if (@PAGEABLE@) {
            var page = get("/accounts/history?page=0&size=1");
            assertEquals(200, page.statusCode(), page.body());
            assertTrue(page.body().contains("\"totalElements\":2"), page.body());
            assertTrue(page.body().contains("\"numberOfElements\":1"), page.body());
            assertEquals(400, get("/accounts/history?page=0&size=201").statusCode());
            assertEquals(400, get("/accounts/history?page=50001&size=1").statusCode());
        }
        // Mixed CRUD retains POST /accounts, so GET is method-not-allowed there.
        assertEquals(@MIXED@ ? 405 : 404, get("/accounts").statusCode());
        // The refused owner route is not a hidden alternate generated endpoint.
        assertEquals(404, get("/customers/CUST-1").statusCode());
        assertEquals(2L, jdbc.queryForObject("SELECT COUNT(*) FROM account", Long.class));
    }
}
