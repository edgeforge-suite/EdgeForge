package proof;

import __APP__;
import __JACKSON__.databind.ObjectMapper;
import com.appbuilder.kafka_proof.router.RouterJsonSchemaValidator;
import java.nio.charset.StandardCharsets;
import java.nio.ByteBuffer;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.apache.kafka.common.serialization.*;
import org.junit.jupiter.api.*;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.EmbeddedKafkaKraftBroker;
import static org.junit.jupiter.api.Assertions.*;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class KafkaWireTest {
    EmbeddedKafkaKraftBroker broker;
    ConfigurableApplicationContext app;
    KafkaConsumer<String, String> observer;
    KafkaProducer<String, String> producer;
    ObjectMapper mapper;
    List<Map<String, Object>> observations = new ArrayList<>();
    List<ConsumerRecord<String, String>> pending = new ArrayList<>();
    String[] topics = {"abc.payments.posted.v1", "xyz.ledger.entries.v1", "abc.payments.posted.v1.dlq",
        "abc.payments.reversed.v1", "xyz.ledger.reversals.v1", "abc.payments.reversed.v1.dlq",
        "hub.account.verify.request.v1", "core.account.verify.request.v1", "core.account.verify.reply.v1", "hub.account.verify.reply.v1",
        "hub.fraud.check.request.v1", "fraud.check.request.v1", "fraud.check.reply.v1", "hub.fraud.check.reply.v1",
        "u1-payment-request", "u2-payment-request", "d1-payment-request", "d1-payment-response",
        "d2-payment-request", "d2-payment-response", "proof-reply", "payment-router-nack", "payment-router-error"};

    @BeforeAll void start() throws Exception {
        broker = new EmbeddedKafkaKraftBroker(1, 1, topics);
        broker.afterPropertiesSet();
        Properties cp = new Properties();
        cp.put("bootstrap.servers", broker.getBrokersAsString());
        cp.put("group.id", "s3-observer");
        cp.put("auto.offset.reset", "earliest");
        cp.put("key.deserializer", StringDeserializer.class.getName());
        cp.put("value.deserializer", StringDeserializer.class.getName());
        observer = new KafkaConsumer<>(cp);
        observer.subscribe(Arrays.stream(topics).filter(t -> !t.equals("u1-payment-request") && !t.equals("u2-payment-request")
            && !t.startsWith("abc.payments.") || t.endsWith(".dlq")).toList());
        Properties pp = new Properties();
        pp.put("bootstrap.servers", broker.getBrokersAsString());
        pp.put("key.serializer", StringSerializer.class.getName());
        pp.put("value.serializer", StringSerializer.class.getName());
        producer = new KafkaProducer<>(pp);
        app = SpringApplication.run(__APP_CLASS__.class,
            "--server.port=0", "--spring.kafka.bootstrap-servers=" + broker.getBrokersAsString(),
            "--app.kafka.router.payment_router.reply-destination.allowed-topics=proof-reply",
            "--logging.level.root=WARN");
        mapper = app.getBean(ObjectMapper.class);
        long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
        KafkaListenerEndpointRegistry registry = app.getBean(KafkaListenerEndpointRegistry.class);
        while (registry.getListenerContainers().stream().anyMatch(c -> c.getAssignedPartitions() == null || c.getAssignedPartitions().isEmpty())) {
            if (System.nanoTime() > deadline) fail("Generated listeners did not obtain broker assignments");
            Thread.sleep(100);
        }
        while (observer.assignment().isEmpty()) {
            if (System.nanoTime() > deadline) fail("Observer did not obtain broker assignments");
            poll();
        }
        assertFalse(app.containsBean("dataSource"));
        assertFalse(app.containsBean("jobRepository"));
    }

    @AfterAll void stop() throws Exception {
        try {
            if (mapper != null) Files.writeString(Path.of("target/wire-observations.json"), mapper.writeValueAsString(observations));
        } finally {
            if (app != null) app.close();
            if (producer != null) producer.close();
            if (observer != null) observer.close();
            if (broker != null) broker.destroy();
        }
    }

    @Test @Order(1) void plainTransformDateDecimalNull() throws Exception {
        send("abc.payments.posted.v1", "plain-key", "{\"paymentId\":\"plain\",\"accountId\":\"A1\",\"amount\":12.34,\"currency\":null,\"businessDate\":\"2026-09-30\",\"note\":null}", Map.of());
        ConsumerRecord<String, String> result = receive("xyz.ledger.entries.v1", "entryId", "plain");
        Map<?, ?> payload = mapper.readValue(result.value(), Map.class);
        assertEquals(1234, ((Number)payload.get("amountMinorUnits")).intValue());
        assertEquals(List.of(2026, 9, 30), payload.get("businessDate"));
        assertTrue(payload.containsKey("note"));
        assertNull(payload.get("note"));
        assertNotNull(result.headers().lastHeader("__TypeId__"));
        record("plain", result);
    }

    @Test @Order(2) void plainRequestReply() throws Exception {
        send("hub.account.verify.request.v1", "account-key", "{\"paymentId\":\"account\",\"accountNumber\":\"A2\",\"amount\":23.45,\"countryCode\":\"UK\"}", Map.of("X-Correlation-ID", "account-correlation"));
        ConsumerRecord<String, String> request = receive("core.account.verify.request.v1", "requestId", "account");
        assertEquals("account-correlation", header(request, "X-Correlation-ID"));
        record("account-request", request);
        send("core.account.verify.reply.v1", "account-correlation", "{\"requestId\":\"account\",\"verified\":true,\"reason\":null,\"riskScore\":7}", Map.of("X-Correlation-ID", "account-correlation"));
        ConsumerRecord<String, String> response = receive("hub.account.verify.reply.v1", "paymentId", "account");
        assertEquals("account-correlation", header(response, "X-Correlation-ID"));
        record("account-reply", response);
    }

    @Test @Order(3) void routerHeaderExtractionAndRoundtrip() throws Exception {
        routerSend("roundtrip", valid("UK"), headers("roundtrip"));
        ConsumerRecord<String, String> request = receive("d1-payment-request", "transactionId", "roundtrip");
        assertEquals("roundtrip", request.key());
        assertEquals("roundtrip", header(request, "X-Correlation-ID"));
        record("router-request", request);
        send("d1-payment-response", "roundtrip", "{\"processorStatus\":\"ACCEPTED\"}", Map.of("X-Correlation-ID", "roundtrip"));
        ConsumerRecord<String, String> response = receive("proof-reply", "status", "APPROVED");
        assertEquals("roundtrip", response.key());
        assertEquals("roundtrip", header(response, "X-Correlation-ID"));
        record("router-reply", response);
    }

    @Test @Order(4) void routerBodyExtractionAndSecondTarget() throws Exception {
        String payload = valid("US").replace("}", ",\"sourceSystem\":\"body-source\",\"replyTopic\":\"proof-reply\",\"correlationId\":\"body\"}");
        send("u2-payment-request", "body-key", payload.replace("CASE_ID", "body"), Map.of());
        ConsumerRecord<String, String> request = receive("d2-payment-request", "transactionId", "body");
        assertEquals("body", request.key());
        record("body-request", request);
        send("d2-payment-response", "body", "{\"processorStatus\":\"REJECTED\"}", Map.of("X-Correlation-ID", "body"));
        ConsumerRecord<String, String> reply = receive("proof-reply", "status", "DECLINED");
        assertEquals("body", reply.key());
        record("body-reply", reply);
    }

    @Test @Order(5) void preValidationSourceAndReplyRejection() throws Exception {
        Map<String, String> source = new HashMap<>(headers("bad-source")); source.remove("X-Source-System");
        routerSend("bad-source", valid("UK"), source);
        nack("invalid-source", "payment-router-error", "bad-source", "INVALID_SOURCE_SYSTEM", "pre-v1");
        Map<String, String> reply = new HashMap<>(headers("bad-reply")); reply.put("X-Reply-To", "not-allowed");
        routerSend("bad-reply", valid("UK"), reply);
        nack("invalid-reply", "payment-router-error", "bad-reply", "INVALID_REPLY_DESTINATION", "pre-v1");
        absent("d1-payment-request", "transactionId", "bad-source");
        absent("d1-payment-request", "transactionId", "bad-reply");
    }

    @Test @Order(6) void v1Rejection() throws Exception {
        routerSend("v1", valid("UK").replace(",\"status\":\"APPROVED\"", ""), headers("v1"));
        nack("v1", "payment-router-nack", "v1", "V1_VALIDATION_FAILED", "V1");
        absent("d1-payment-request", "transactionId", "v1");
    }

    @Test @Order(7) void v2Rejection() throws Exception {
        routerSend("v2", valid("UK").replace("12.34", "0"), headers("v2"));
        nack("v2", "payment-router-nack", "v2", "V2_VALIDATION_FAILED", "V2");
        absent("d1-payment-request", "transactionId", "v2");
    }

    @Test @Order(8) void v3Rejection() throws Exception {
        routerSend("v3", valid("UK"), headers("v3")); receive("d1-payment-request", "transactionId", "v3");
        send("d1-payment-response", "v3", "{\"processorStatus\":\"INVALID\"}", Map.of("X-Correlation-ID", "v3"));
        nack("v3", "payment-router-nack", "v3", "V3_VALIDATION_FAILED", "V3");
    }

    @Test @Order(9) void v4Rejection() throws Exception {
        routerSend("v4", valid("UK"), headers("v4")); receive("d1-payment-request", "transactionId", "v4");
        send("d1-payment-response", "v4", "{\"processorStatus\":\"OTHER\"}", Map.of("X-Correlation-ID", "v4"));
        nack("v4", "payment-router-nack", "v4", "V4_VALIDATION_FAILED", "V4");
    }

    @Test @Order(10) void duplicateAndTimeout() throws Exception {
        routerSend("duplicate", valid("UK"), headers("duplicate")); receive("d1-payment-request", "transactionId", "duplicate");
        routerSend("duplicate", valid("UK"), headers("duplicate"));
        nack("duplicate", "payment-router-nack", "duplicate", "DUPLICATE_CORRELATION", "correlation");
        ConsumerRecord<String, String> timeout = receive("payment-router-nack", "errorCode", "CORRELATION_TIMEOUT");
        assertEquals("duplicate", mapper.readValue(timeout.value(), Map.class).get("correlationId"));
        record("timeout", timeout);
    }

    @Test @Order(11) void technicalFailureReachesDlqWithOriginalPayload() throws Exception {
        var sent = send("abc.payments.posted.v1", "technical-key", "not-json", Map.of("X-Correlation-ID", "technical"));
        ConsumerRecord<String, String> dlq = receiveRaw("abc.payments.posted.v1.dlq", "not-json");
        assertEquals("technical-key", dlq.key());
        assertEquals("technical", header(dlq, "X-Correlation-ID"));
        assertNotNull(dlq.headers().lastHeader("kafka_dlt-exception-fqcn"));
        assertEquals(sent.offset(), ByteBuffer.wrap(dlq.headers().lastHeader("kafka_dlt-original-offset").value()).getLong());
        assertEquals(sent.partition(), ByteBuffer.wrap(dlq.headers().lastHeader("kafka_dlt-original-partition").value()).getInt());
        assertEquals(sent.timestamp(), ByteBuffer.wrap(dlq.headers().lastHeader("kafka_dlt-original-timestamp").value()).getLong());
        assertEquals(sent.topic(), header(dlq, "kafka_dlt-original-topic"));
        record("technical-dlq", dlq);
    }

    @Test @Order(12) void secondPlainRoute() throws Exception {
        send("abc.payments.reversed.v1", "reversal-key", "{\"reversalId\":\"reversal\",\"originalPaymentId\":\"plain\",\"amountMinorUnits\":1234,\"reasonCode\":\"RETURN\"}", Map.of());
        ConsumerRecord<String, String> result = receive("xyz.ledger.reversals.v1", "entryId", "reversal");
        assertEquals(12.34, ((Number)mapper.readValue(result.value(), Map.class).get("amount")).doubleValue());
        record("reversal", result);
    }

    @Test @Order(13) void secondPlainRequestReply() throws Exception {
        send("hub.fraud.check.request.v1", "fraud-key", "{\"caseId\":\"fraud\",\"customerId\":\"C1\",\"amount\":12.34}", Map.of("X-Request-ID", "fraud-correlation"));
        ConsumerRecord<String, String> request = receive("fraud.check.request.v1", "investigationId", "fraud");
        assertEquals("fraud-correlation", header(request, "X-Request-ID"));
        record("fraud-request", request);
        send("fraud.check.reply.v1", "fraud-correlation", "{\"investigationId\":\"fraud\",\"clear\":true,\"decisionCode\":\"CLEAR\",\"reviewLevel\":2}", Map.of("X-Request-ID", "fraud-correlation"));
        ConsumerRecord<String, String> response = receive("hub.fraud.check.reply.v1", "caseId", "fraud");
        assertEquals("fraud-correlation", header(response, "X-Request-ID"));
        record("fraud-reply", response);
    }

    @Test @Order(14) void dialectFormatTypeAndPackagedReferencePolicy() {
        RouterJsonSchemaValidator validator = app.getBean(RouterJsonSchemaValidator.class);
        for (String name : List.of("draft7", "draft2020", "default")) {
            String schema = "proof/" + name + ".json";
            validator.validate("{\"date\":\"2026-09-30\",\"amount\":12.34}", schema, "V1");
            assertThrows(RuntimeException.class, () -> validator.validate("{\"date\":\"not-a-date\",\"amount\":12.34}", schema, "V1"));
            assertThrows(RuntimeException.class, () -> validator.validate("{\"date\":\"2026-09-30\",\"amount\":\"12.34\"}", schema, "V1"));
        }
    }

    void routerSend(String id, String payload, Map<String, String> headers) throws Exception {
        send("u1-payment-request", "input-" + id, payload.replace("CASE_ID", id), headers);
    }
    String valid(String country) { return "{\"paymentId\":\"CASE_ID\",\"amount\":12.34,\"country\":\"" + country + "\",\"status\":\"APPROVED\"}"; }
    Map<String, String> headers(String id) { return Map.of("X-Correlation-ID", id, "X-Source-System", "source", "X-Reply-To", "proof-reply"); }
    RecordMetadata send(String topic, String key, String payload, Map<String, String> headers) throws Exception {
        ProducerRecord<String, String> record = new ProducerRecord<>(topic, key, payload);
        headers.forEach((k,v) -> record.headers().add(new RecordHeader(k, v.getBytes(StandardCharsets.UTF_8))));
        return producer.send(record).get();
    }
    void poll() { for (ConsumerRecord<String, String> record : observer.poll(Duration.ofMillis(100))) pending.add(record); }
    ConsumerRecord<String, String> receive(String topic, String field, String value) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();
        do {
            for (Iterator<ConsumerRecord<String, String>> it = pending.iterator(); it.hasNext();) {
                ConsumerRecord<String, String> r = it.next();
                if (r.topic().equals(topic) && Objects.equals(mapper.readValue(r.value(), Map.class).get(field), value)) { it.remove(); return r; }
            }
            poll();
        } while (System.nanoTime() < deadline);
        throw new AssertionError("Missing " + topic + "/" + field + "=" + value + "; pending=" + pending);
    }
    ConsumerRecord<String, String> receiveRaw(String topic, String value) {
        long deadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();
        do {
            for (Iterator<ConsumerRecord<String, String>> it = pending.iterator(); it.hasNext();) {
                ConsumerRecord<String, String> r = it.next();
                if (r.topic().equals(topic) && r.value().equals(value)) { it.remove(); return r; }
            }
            poll();
        } while (System.nanoTime() < deadline);
        throw new AssertionError("Missing raw " + topic);
    }
    void absent(String topic, String field, String value) throws Exception {
        long deadline = System.nanoTime() + Duration.ofMillis(500).toNanos();
        do {
            poll();
            for (ConsumerRecord<String, String> r : pending)
                if (r.topic().equals(topic)) assertNotEquals(value, mapper.readValue(r.value(), Map.class).get(field));
        } while (System.nanoTime() < deadline);
    }
    void nack(String caseId, String topic, String id, String code, String boundary) throws Exception {
        ConsumerRecord<String, String> record = receive(topic, "correlationId", id);
        Map<?, ?> body = mapper.readValue(record.value(), Map.class);
        assertEquals(code, body.get("errorCode")); assertEquals(boundary, body.get("validationBoundary"));
        assertFalse(((String)body.get("errorReason")).isBlank());
        Instant.parse((String)body.get("timestamp"));
        record(caseId, record);
    }
    String header(ConsumerRecord<String, String> record, String name) {
        return record.headers().lastHeader(name) == null ? null : new String(record.headers().lastHeader(name).value(), StandardCharsets.UTF_8);
    }
    void record(String caseId, ConsumerRecord<String, String> record) throws Exception {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("case", caseId); row.put("topic", record.topic()); row.put("key", record.key());
        row.put("payload", caseId.equals("technical-dlq") ? record.value() : mapper.readValue(record.value(), Map.class));
        Map<String, List<String>> headers = new TreeMap<>();
        record.headers().forEach(h -> headers.computeIfAbsent(h.key(), k -> new ArrayList<>()).add(Base64.getEncoder().encodeToString(h.value())));
        row.put("headers_base64", headers); observations.add(row);
    }
}
