import java.io.ByteArrayInputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

/** Test-only reader for the synthetic fixture's persisted, string-valued context. */
public class ReadBatchContext {
    public static void main(String[] args) throws Exception {
        byte[] input = System.in.readNBytes(65537);
        if (input.length > 65536) {
            throw new IllegalArgumentException("Context exceeds proof bound");
        }
        try (var stream = new ObjectInputStream(new ByteArrayInputStream(Base64.getDecoder().decode(input)))) {
            stream.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
                "maxdepth=16;maxrefs=256;maxbytes=65536;java.util.HashMap;java.util.Map$Entry;java.lang.String;!*"));
            Map<?, ?> context = (Map<?, ?>) stream.readObject();
            for (String key : new String[] {"runId", "frozenBusinessDate"}) {
                Object value = context.get(key);
                if (value != null && !(value instanceof String)) {
                    throw new IllegalArgumentException("Expected a string context value");
                }
                System.out.println(value == null ? "-" : Base64.getEncoder().encodeToString(
                    ((String) value).getBytes(StandardCharsets.UTF_8)));
            }
        }
    }
}
