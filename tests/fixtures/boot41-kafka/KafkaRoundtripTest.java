package proof;

import __APP__;
import __JACKSON__.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.apache.kafka.common.serialization.*;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.EmbeddedKafkaKraftBroker;
import static org.junit.jupiter.api.Assertions.*;

class KafkaRoundtripTest {
    @Test void standaloneRoundtrip() throws Exception {
        boolean router = __ROUTER__;
        String input = router ? "u1-payment-request" : "abc.payments.posted.v1";
        String output = router ? "d1-payment-request" : "xyz.ledger.entries.v1";
        EmbeddedKafkaKraftBroker broker = new EmbeddedKafkaKraftBroker(1, 1, input, output, "d1-payment-response", "proof-reply");
        broker.afterPropertiesSet();
        try {
            Properties props = new Properties();
            props.put("bootstrap.servers", broker.getBrokersAsString());
            props.put("key.serializer", StringSerializer.class.getName());
            props.put("value.serializer", StringSerializer.class.getName());
            Properties consumerProps = new Properties();
            consumerProps.put("bootstrap.servers", broker.getBrokersAsString());
            consumerProps.put("group.id", "roundtrip-observer");
            consumerProps.put("auto.offset.reset", "earliest");
            consumerProps.put("key.deserializer", StringDeserializer.class.getName());
            consumerProps.put("value.deserializer", StringDeserializer.class.getName());
            try (var producer = new KafkaProducer<String, String>(props);
                 var consumer = new KafkaConsumer<String, String>(consumerProps);
                 var app = SpringApplication.run(__APP_CLASS__.class, "--server.port=0", "--spring.kafka.bootstrap-servers=" + broker.getBrokersAsString(), "--app.kafka.router.payment_router.reply-destination.allowed-topics=proof-reply", "--logging.level.root=WARN")) {
                assertFalse(app.containsBean("dataSource"));
                assertFalse(app.containsBean("jobRepository"));
                consumer.subscribe(List.of(output, "proof-reply"));
                var registry = app.getBean(KafkaListenerEndpointRegistry.class);
                long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
                while (registry.getListenerContainers().stream().anyMatch(c -> c.getAssignedPartitions() == null || c.getAssignedPartitions().isEmpty())) {
                    assertTrue(System.nanoTime() < deadline, "Listener assignment timeout");
                    Thread.sleep(100);
                }
                String payload = router ? "{\"paymentId\":\"probe\",\"amount\":12.34,\"country\":\"UK\",\"status\":\"APPROVED\"}" : "{\"paymentId\":\"probe\",\"accountId\":\"A1\",\"amount\":12.34}";
                ProducerRecord<String, String> request = new ProducerRecord<>(input, "probe", payload);
                if (router) Map.of("X-Correlation-ID", "probe", "X-Source-System", "source", "X-Reply-To", "proof-reply").forEach((k,v) -> request.headers().add(new RecordHeader(k, v.getBytes(StandardCharsets.UTF_8))));
                producer.send(request).get();
                ObjectMapper mapper = app.getBean(ObjectMapper.class);
                boolean requestSeen = false, replySeen = !router;
                while (!(requestSeen && replySeen) && System.nanoTime() < deadline) {
                    for (var record : consumer.poll(Duration.ofMillis(100))) {
                        Map<?, ?> body = mapper.readValue(record.value(), Map.class);
                        if (record.topic().equals(output)) {
                            assertEquals("probe", body.get(router ? "transactionId" : "entryId"));
                            if (router) {
                                assertEquals("probe", record.key());
                                assertEquals("probe", new String(record.headers().lastHeader("X-Correlation-ID").value(), StandardCharsets.UTF_8));
                                ProducerRecord<String, String> reply = new ProducerRecord<>("d1-payment-response", "probe", "{\"processorStatus\":\"ACCEPTED\"}");
                                reply.headers().add(new RecordHeader("X-Correlation-ID", "probe".getBytes(StandardCharsets.UTF_8)));
                                producer.send(reply).get();
                            } else assertEquals(1234, ((Number)body.get("amountMinorUnits")).intValue());
                            requestSeen = true;
                        } else {
                            assertEquals("APPROVED", body.get("status"));
                            assertEquals("probe", record.key());
                            replySeen = true;
                        }
                    }
                }
                assertTrue(requestSeen && replySeen, "No broker roundtrip");
            }
        } finally { broker.destroy(); }
    }
}
