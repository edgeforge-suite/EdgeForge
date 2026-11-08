package proof;

import __APP__;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import org.apache.kafka.clients.consumer.*;
import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.boot.SpringApplication;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;

/** Runs only in the generated application's own non-root linux/amd64 image. */
public class Lz4ContainerProof {
    private static void require(boolean condition, String detail) {
        if (!condition) throw new AssertionError(detail);
    }

    public static void main(String[] args) throws Exception {
        require(System.getProperty("os.name").equals("Linux"), "Linux required");
        require(System.getProperty("os.arch").equals("amd64"), "amd64 required");
        int uid = ((Number) Files.getAttribute(Path.of("/proc/self"), "unix:uid")).intValue();
        require(uid != 0, "Root cannot count as proof");
        // File.createTempFile can cache java.io.tmpdir before main (notably on
        // Java 21). The non-root container entrypoint creates it exclusively and
        // passes the property at JVM startup, before any native extraction.
        Path temp = Path.of(System.getProperty("java.io.tmpdir"));
        require(temp.getFileName().toString().startsWith("ef-lz4-native."), "Owned startup temp directory required");
        require(Files.isDirectory(temp, LinkOption.NOFOLLOW_LINKS), "Owned temp directory missing");
        require(((Number) Files.getAttribute(temp, "unix:uid")).intValue() == uid, "Wrong temp directory owner");
        System.setProperty("lz4java.jnilib.temp.keep", "true");
        // LZ4 is a runtime-scoped Kafka dependency; inspect it without changing
        // the generated POM's compile/runtime boundaries for this probe.
        Class<?> nativeClass = Class.forName("net.jpountz.util.Native");
        Class<?> lz4Class = Class.forName("net.jpountz.lz4.LZ4Factory");
        Class<?> xxhashClass = Class.forName("net.jpountz.xxhash.XXHashFactory");
        require(!(Boolean) nativeClass.getMethod("isLoaded").invoke(null),
                "Native library unexpectedly loaded before observation");
        try (var paths = Files.list(temp)) {
            require(paths.findAny().isEmpty(), "Extraction directory must start empty");
        }
        String origin = lz4Class.getProtectionDomain().getCodeSource().getLocation().toString();
        require(origin.contains("lz4-java-1.11.4.jar"), "Unexpected resolved LZ4 artifact: " + origin);
        // Boot's nested-JAR loader is not the system loader. Explicitly exercise
        // Native.load for this native scenario; do not credit an ordinary Java
        // fallback as native evidence or claim that deployment defaults force JNI.
        nativeClass.getMethod("load").invoke(null);
        var lz4 = lz4Class.getMethod("fastestInstance").invoke(null);
        var xxhash = xxhashClass.getMethod("fastestInstance").invoke(null);
        var compressor = lz4Class.getMethod("fastCompressor").invoke(lz4);
        var hash32 = xxhashClass.getMethod("hash32").invoke(xxhash);
        require((Boolean) nativeClass.getMethod("isLoaded").invoke(null), "Native load failed");
        require(compressor.getClass().getName().contains("JNI"), "LZ4 Java fallback");
        require(hash32.getClass().getName().contains("JNI"), "XXHash Java fallback");
        List<Path> libraries;
        try (var paths = Files.list(temp)) { libraries = paths.toList(); }
        require(libraries.size() == 1, "Exactly one newly extracted JNI library required");
        Path library = libraries.get(0);
        require(library.getFileName().toString().matches("liblz4-java-.+\\.so"), "Unexpected native file");
        require(Files.isRegularFile(library, LinkOption.NOFOLLOW_LINKS), "Native file must not be a symlink");
        var attrs = Files.readAttributes(library, "unix:uid,gid,ino,mode,size,nlink", LinkOption.NOFOLLOW_LINKS);
        require(((Number) attrs.get("uid")).intValue() == uid, "Extraction ownership differs from process");
        require(((Number) attrs.get("nlink")).intValue() == 1, "Unexpected hard link");
        byte[] resource;
        try (var input = nativeClass.getResourceAsStream("/net/jpountz/util/linux/amd64/liblz4-java.so")) {
            require(input != null, "Bundled native resource missing");
            resource = input.readAllBytes();
        }
        var sha = MessageDigest.getInstance("SHA-256");
        String digest = HexFormat.of().formatHex(sha.digest(Files.readAllBytes(library)));
        require(digest.equals(HexFormat.of().formatHex(sha.digest(resource))), "Extracted bytes differ from bundled resource");
        List<String> mappings = Files.readAllLines(Path.of("/proc/self/maps")).stream()
                .filter(line -> line.contains(library.toString())).toList();
        require(!mappings.isEmpty(), "No actual native mapping observed");
        System.out.println("LZ4_NATIVE_PROOF java=" + System.getProperty("java.version") + " uid=" + uid
                + " lz4=" + lz4 + " compressor=" + compressor.getClass().getName()
                + " xxhash=" + xxhash + " hash32=" + hash32.getClass().getName()
                + " tempInitiallyEmpty=true library=" + library + " attributes=" + attrs
                + " origin=" + origin + " sha256=" + digest + " mappings=" + mappings);

        Class<?> kafkaLz4 = Class.forName("org.apache.kafka.common.compress.Lz4BlockOutputStream");
        try (var stream = (java.io.OutputStream) kafkaLz4.getConstructor(java.io.OutputStream.class, int.class, boolean.class)
                .newInstance(new java.io.ByteArrayOutputStream(), -1, false)) {
            for (String fieldName : List.of("compressor", "checksum")) {
                var field = kafkaLz4.getDeclaredField(fieldName);
                field.setAccessible(true);
                String implementation = field.get(stream).getClass().getName();
                require(implementation.contains("JNI"), "Kafka actual " + fieldName + " used Java fallback");
                System.out.println("KAFKA_LZ4_IMPLEMENTATION " + fieldName + "=" + implementation);
            }
            stream.write("native-kafka-lz4-proof".repeat(100).getBytes(java.nio.charset.StandardCharsets.UTF_8));
        }

        String bootstrap = System.getenv("KAFKA_BOOTSTRAP_SERVERS");
        Properties producerProps = new Properties();
        producerProps.put("bootstrap.servers", bootstrap);
        producerProps.put("key.serializer", StringSerializer.class.getName());
        producerProps.put("value.serializer", StringSerializer.class.getName());
        producerProps.put("compression.type", "lz4");
        producerProps.put("acks", "all");
        producerProps.put("delivery.timeout.ms", "30000");
        producerProps.put("request.timeout.ms", "10000");
        producerProps.put("linger.ms", "0");
        Properties consumerProps = new Properties();
        consumerProps.put("bootstrap.servers", bootstrap);
        consumerProps.put("group.id", "lz4-proof-" + UUID.randomUUID());
        consumerProps.put("auto.offset.reset", "earliest");
        consumerProps.put("key.deserializer", StringDeserializer.class.getName());
        consumerProps.put("value.deserializer", StringDeserializer.class.getName());
        try (var app = SpringApplication.run(__APP_CLASS__.class,
                "--server.port=0", "--logging.level.root=WARN",
                "--spring.kafka.producer.compression-type=lz4");
             var producer = new KafkaProducer<String, String>(producerProps);
             var consumer = new KafkaConsumer<String, String>(consumerProps)) {
            require(!app.containsBean("dataSource"), "Kafka must stay datasource-free");
            var registry = app.getBean(KafkaListenerEndpointRegistry.class);
            long deadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
            while (registry.getListenerContainers().stream().anyMatch(c -> c.getAssignedPartitions() == null || c.getAssignedPartitions().isEmpty())) {
                require(System.nanoTime() < deadline, "Listener assignment timeout");
                Thread.sleep(100);
            }
            consumer.subscribe(List.of("xyz.ledger.entries.v1"));
            String key = "lz4-" + UUID.randomUUID();
            String payload = "{\"paymentId\":\"" + key + "\",\"accountId\":\"A1\",\"amount\":12.34}";
            var sent = producer.send(new ProducerRecord<>("abc.payments.posted.v1", key, payload)).get();
            boolean observed = false;
            while (!observed && System.nanoTime() < deadline) {
                for (var record : consumer.poll(Duration.ofMillis(200))) {
                    var body = app.getBean(tools.jackson.databind.ObjectMapper.class).readTree(record.value());
                    if (body.get("entryId").stringValue().equals(key)) {
                        require(body.get("amountMinorUnits").intValue() == 1234, "Money contract mismatch");
                        require(body.get("accountRef").stringValue().equals("A1"), "Account contract mismatch");
                        observed = true;
                        System.out.println("LZ4_ROUNDTRIP_PROOF compression.type=lz4 input=" + sent
                                + " output=" + record.topic() + ":" + record.partition() + ":" + record.offset()
                                + " payload=" + record.value());
                    }
                }
            }
            require(observed, "No LZ4 generated-app broker roundtrip");
        }
    }
}
