package __PACKAGE__.proof;

import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.record.CompressionType;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/** Proof-only addition, discovered by the unchanged generated main's component scan.
 * No production bean, factory selection, launcher, or JVM property is replaced.
 */
@Component
public final class Lz4DefaultObserver implements ApplicationListener<ApplicationReadyEvent> {
    private static void require(boolean condition, String detail) {
        if (!condition) throw new IllegalStateException(detail);
    }

    private static String origin(Class<?> type) {
        return type.getProtectionDomain().getCodeSource().getLocation().toString();
    }

    private static Map<String, Object> position(String topic, int partition, long offset) {
        return Map.of("topic", topic, "partition", partition, "offset", offset);
    }

    private static OutputStream kafkaDefaultLz4Stream(OutputStream output) throws ReflectiveOperationException {
        // The int is a compression level, not a default sentinel. Kafka's builder uses this constant.
        return (OutputStream) Class.forName("org.apache.kafka.common.compress.Lz4BlockOutputStream")
                .getConstructor(OutputStream.class, int.class, boolean.class)
                .newInstance(output, CompressionType.LZ4.defaultLevel(), false);
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        var app = event.getApplicationContext();
        try {
            require(System.getProperty("os.name").equals("Linux"), "Linux required");
            require(System.getProperty("os.arch").equals("amd64"), "amd64 required");
            int uid = ((Number) Files.getAttribute(Path.of("/proc/self"), "unix:uid")).intValue();
            require(uid != 0, "Non-root process required");
            require(System.getProperty("sun.java.command").equals("/app/app.jar"), "Ordinary java-jar required");
            var jvmArgs = ManagementFactory.getRuntimeMXBean().getInputArguments();
            require(jvmArgs.isEmpty(), "Unexpected JVM arguments: " + jvmArgs);
            require(!app.containsBean("dataSource"), "Kafka must remain datasource-free");
            ClassLoader loader = getClass().getClassLoader();
            require(loader.getClass().getName().equals("org.springframework.boot.loader.launch.LaunchedClassLoader"),
                    "Boot nested classloader required");
            require(Class.forName("__APP__").getClassLoader() == loader, "Generated main loader differs");
            var mapper = app.getBean(JsonMapper.class);
            var registry = app.getBean(KafkaListenerEndpointRegistry.class);
            require(!registry.getListenerContainers().isEmpty(), "Generated listener missing");
            long deadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
            while (registry.getListenerContainers().stream().anyMatch(c ->
                    c.getAssignedPartitions() == null || c.getAssignedPartitions().isEmpty())) {
                require(System.nanoTime() < deadline, "Listener assignment timeout");
                Thread.sleep(100);
            }

            String bootstrap = System.getenv("KAFKA_BOOTSTRAP_SERVERS");
            require(bootstrap != null && !bootstrap.isBlank(), "Real broker required");
            Properties producerProps = new Properties();
            producerProps.put("bootstrap.servers", bootstrap);
            producerProps.put("key.serializer", StringSerializer.class.getName());
            producerProps.put("value.serializer", StringSerializer.class.getName());
            producerProps.put("compression.type", "lz4");
            producerProps.put("acks", "all");
            producerProps.put("delivery.timeout.ms", "30000");
            producerProps.put("request.timeout.ms", "10000");
            producerProps.put("max.block.ms", "30000");
            Properties consumerProps = new Properties();
            consumerProps.put("bootstrap.servers", bootstrap);
            consumerProps.put("group.id", "default-lz4-" + UUID.randomUUID());
            consumerProps.put("auto.offset.reset", "earliest");
            consumerProps.put("key.deserializer", StringDeserializer.class.getName());
            consumerProps.put("value.deserializer", StringDeserializer.class.getName());
            consumerProps.put("default.api.timeout.ms", "30000");
            String key = "default-lz4-" + UUID.randomUUID();
            String payload = "{\"paymentId\":\"" + key + "\",\"accountId\":\"A1\",\"amount\":12.34}";
            Map<String, Object> roundtrip = new LinkedHashMap<>();
            try (var producer = new KafkaProducer<String, String>(producerProps);
                 var consumer = new KafkaConsumer<String, String>(consumerProps)) {
                consumer.subscribe(List.of("xyz.ledger.entries.v1"));
                var sent = producer.send(new ProducerRecord<>("abc.payments.posted.v1", key, payload))
                        .get(30, TimeUnit.SECONDS);
                roundtrip.put("input_position", position(sent.topic(), sent.partition(), sent.offset()));
                roundtrip.put("key", key);
                roundtrip.put("input_partition_key", key);
                roundtrip.put("input", mapper.readTree(payload));
                roundtrip.put("input_compression", "lz4");
                // Generated outbound producer configuration is intentionally not overridden.
                roundtrip.put("output_compression", "unchanged generated default; not claimed as LZ4");
                deadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
                boolean observed = false;
                while (!observed && System.nanoTime() < deadline) {
                    for (var record : consumer.poll(Duration.ofMillis(200))) {
                        var body = mapper.readTree(record.value());
                        if (!body.has("entryId") || !key.equals(body.get("entryId").stringValue())) continue;
                        // This fixture omits partition_key: the generated round_robin route publishes null.
                        require(record.key() == null, "Partition key contract mismatch: expected null for round_robin, actual="
                                + record.key());
                        require(body.size() == 4 && body.get("entryId").isString()
                                && body.get("accountRef").isString() && body.get("accountRef").stringValue().equals("A1")
                                && body.get("amountMinorUnits").isIntegralNumber()
                                && body.get("amountMinorUnits").intValue() == 1234
                                && body.get("channel").isString() && body.get("channel").stringValue().equals("KAFKA_HUB"),
                                "Output values/types differ from reviewed mapping");
                        roundtrip.put("output", body);
                        roundtrip.put("output_partition_key_strategy", "round_robin");
                        roundtrip.put("output_partition_key", record.key());
                        roundtrip.put("output_position", position(record.topic(), record.partition(), record.offset()));
                        observed = true;
                    }
                }
                require(observed, "No real Kafka generated-listener roundtrip");
            }

            // Observe only after real traffic has exercised Kafka's default selection.
            Class<?> lz4Type = Class.forName("net.jpountz.lz4.LZ4Factory");
            Class<?> hashType = Class.forName("net.jpountz.xxhash.XXHashFactory");
            Class<?> nativeType = Class.forName("net.jpountz.util.Native");
            Class<?> streamType = Class.forName("org.apache.kafka.common.compress.Lz4BlockOutputStream");
            for (Class<?> type : List.of(lz4Type, hashType, nativeType, streamType)) {
                require(type.getClassLoader() == loader, "Dependency did not use Boot nested loader");
            }
            boolean nativeAfterTraffic = (Boolean) nativeType.getMethod("isLoaded").invoke(null);
            var lz4 = lz4Type.getMethod("fastestInstance").invoke(null);
            var hash = hashType.getMethod("fastestInstance").invoke(null);
            var compressor = lz4Type.getMethod("fastCompressor").invoke(lz4);
            var checksum = hashType.getMethod("hash32").invoke(hash);
            Map<String, Object> implementations = new LinkedHashMap<>();
            implementations.put("lz4_factory", lz4.toString());
            implementations.put("xxhash_factory", hash.toString());
            implementations.put("compressor", compressor.getClass().getName());
            implementations.put("checksum", checksum.getClass().getName());
            implementations.put("native_loaded_after_traffic", nativeAfterTraffic);
            implementations.put("observation_scope", "post-roundtrip Kafka default stream; not in-flight producer internals");
            implementations.put("kafka_default_compression_level", CompressionType.LZ4.defaultLevel());
            implementations.put("kafka_compression_level_source", "CompressionType.LZ4.defaultLevel()");
            try (var stream = kafkaDefaultLz4Stream(new ByteArrayOutputStream())) {
                for (String name : List.of("compressor", "checksum")) {
                    var field = streamType.getDeclaredField(name);
                    field.setAccessible(true);
                    String actual = field.get(stream).getClass().getName();
                    require(actual.equals(implementations.get(name)), "Kafka default " + name + " differs: expected="
                            + implementations.get(name) + ", actual=" + actual);
                    implementations.put("kafka_" + name, actual);
                }
                stream.write(payload.repeat(100).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            }
            implementations.put("native_loaded_after_observation", nativeType.getMethod("isLoaded").invoke(null));
            require(origin(lz4Type).contains("lz4-java-1.11.4.jar"), "Unexpected LZ4 artifact");
            require(origin(streamType).contains("kafka-clients-4.2.1.jar"), "Unexpected Kafka artifact");
            Map<String, Object> receipt = new LinkedHashMap<>();
            receipt.put("observer", "proof-only additive component; production sources/config/POM/recipe unchanged");
            receipt.put("java", System.getProperty("java.version"));
            receipt.put("uid", uid);
            receipt.put("os", System.getProperty("os.name"));
            receipt.put("arch", System.getProperty("os.arch"));
            receipt.put("java_command", System.getProperty("sun.java.command"));
            receipt.put("jvm_args", jvmArgs);
            receipt.put("classloader", loader.getClass().getName());
            receipt.put("lz4_origin", origin(lz4Type));
            receipt.put("xxhash_origin", origin(hashType));
            receipt.put("kafka_origin", origin(streamType));
            receipt.put("implementations", implementations);
            receipt.put("roundtrip", roundtrip);
            System.out.println("LZ4_DEFAULT_PROOF " + mapper.writeValueAsString(receipt));
            app.close();
        } catch (Exception exception) {
            throw new IllegalStateException("Default LZ4 proof unavailable; retain runtime log", exception);
        }
    }
}
