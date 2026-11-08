package proof;

// Proof-supplied tests for the pristine kafka-integration fixture, not Engine output.
import com.appbuilder.payment_mediation.config.KafkaConsumerConfig;
import com.appbuilder.payment_mediation.config.KafkaProducerConfig;
import com.appbuilder.payment_mediation.consumer.BalanceUpdatedConsumer;
import com.appbuilder.payment_mediation.consumer.PaymentInitiatedConsumer;
import com.appbuilder.payment_mediation.dto.outbound.LedgerUpdate;
import com.appbuilder.payment_mediation.dto.outbound.SettlementRequest;
import com.appbuilder.payment_mediation.producer.BalanceUpdatedProducer;
import com.appbuilder.payment_mediation.producer.PaymentInitiatedProducer;
import com.appbuilder.payment_mediation.transform.BalanceUpdatedTransformer;
import com.appbuilder.payment_mediation.transform.PaymentInitiatedTransformer;
import java.math.BigDecimal;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.serializer.JacksonJsonSerializer;
import org.springframework.test.util.ReflectionTestUtils;
import tools.jackson.databind.json.JsonMapper;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class KafkaGeneratedContractTest {
    private static final String PAYMENT_IN = "abc.payments.initiated.v1";
    private static final String PAYMENT_OUT = "xyz.settlement.request.v1";
    private static final String BALANCE_IN = "abc.balance.updated.v1";
    private static final String BALANCE_OUT = "xyz.ledger.update.v1";
    private final JsonMapper mapper = JsonMapper.builder().build();
    private KafkaTemplate<String, Object> template;
    private Acknowledgment acknowledgment;
    private PaymentInitiatedConsumer payment;
    private BalanceUpdatedConsumer balance;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void prepareRealRoutesWithMockedTransport() {
        template = mock(KafkaTemplate.class);
        acknowledgment = mock(Acknowledgment.class);
        PaymentInitiatedProducer paymentProducer = new PaymentInitiatedProducer(template);
        BalanceUpdatedProducer balanceProducer = new BalanceUpdatedProducer(template);
        ReflectionTestUtils.setField(paymentProducer, "topic", PAYMENT_OUT);
        ReflectionTestUtils.setField(balanceProducer, "topic", BALANCE_OUT);
        payment = new PaymentInitiatedConsumer(new PaymentInitiatedTransformer(), paymentProducer, mapper);
        balance = new BalanceUpdatedConsumer(new BalanceUpdatedTransformer(), balanceProducer, mapper);
    }

    @AfterEach
    void processingDoesNotLeakRecordLoggingContext() {
        assertNull(MDC.get("sourceTopic"));
        assertNull(MDC.get("partition"));
        assertNull(MDC.get("offset"));
    }

    @Test
    void paymentMapsTypedValuesAndUsesAccountKeyBeforeAcknowledgment() {
        payment.consume(record(PAYMENT_IN, "ignored-upstream-key",
                "{\"paymentId\":\"PAY-not-the-key\",\"accountId\":\"ACC-42\","
                + "\"amount\":125.50,\"currency\":\"USD\"}"), acknowledgment);
        ArgumentCaptor<SettlementRequest> message = ArgumentCaptor.forClass(SettlementRequest.class);
        InOrder order = inOrder(template, acknowledgment);
        order.verify(template).send(eq(PAYMENT_OUT), eq("ACC-42"), message.capture());
        order.verify(acknowledgment).acknowledge();
        order.verifyNoMoreInteractions();
        SettlementRequest result = message.getValue();
        assertEquals("ACC-42", result.getAccountReference());
        assertInstanceOf(String.class, result.getAccountReference());
        assertEquals(new BigDecimal("125.50"), result.getSettlementAmount());
        assertInstanceOf(BigDecimal.class, result.getSettlementAmount());
        assertEquals("USD", result.getSettlementCurrency());
        assertNull(result.getSettlementId(), "The fixture declares no settlementId mapping");
    }

    @Test
    void balanceMapsTypedValuesAndKeepsRoundRobinNullKey() {
        balance.consume(record(BALANCE_IN, "must-not-propagate",
                "{\"accountId\":\"BAL-9\",\"availableBalance\":9876.125,\"currency\":\"EUR\"}"), acknowledgment);
        ArgumentCaptor<LedgerUpdate> message = ArgumentCaptor.forClass(LedgerUpdate.class);
        InOrder order = inOrder(template, acknowledgment);
        order.verify(template).send(eq(BALANCE_OUT), isNull(), message.capture());
        order.verify(acknowledgment).acknowledge();
        order.verifyNoMoreInteractions();
        LedgerUpdate result = message.getValue();
        assertEquals("BAL-9", result.getLedgerAccountId());
        assertInstanceOf(String.class, result.getLedgerAccountId());
        assertEquals(new BigDecimal("9876.125"), result.getBalanceAmount());
        assertInstanceOf(BigDecimal.class, result.getBalanceAmount());
        assertEquals("EUR", result.getCurrencyCode());
    }

    @Test
    void paymentNullFieldsAreForwardedWithNullKeyNotSilentlyDropped() {
        payment.consume(record(PAYMENT_IN, "input-key",
                "{\"paymentId\":\"P-null\",\"accountId\":null,\"amount\":null,\"currency\":null}"), acknowledgment);
        ArgumentCaptor<SettlementRequest> message = ArgumentCaptor.forClass(SettlementRequest.class);
        verify(template).send(eq(PAYMENT_OUT), isNull(), message.capture());
        assertNull(message.getValue().getAccountReference());
        assertNull(message.getValue().getSettlementAmount());
        assertNull(message.getValue().getSettlementCurrency());
        verify(acknowledgment).acknowledge();
        verifyNoMoreInteractions(template, acknowledgment);
    }

    @Test
    void balanceNullFieldsAreForwardedNotSilentlyDropped() {
        balance.consume(record(BALANCE_IN, "input-key",
                "{\"accountId\":null,\"availableBalance\":null,\"currency\":null}"), acknowledgment);
        ArgumentCaptor<LedgerUpdate> message = ArgumentCaptor.forClass(LedgerUpdate.class);
        verify(template).send(eq(BALANCE_OUT), isNull(), message.capture());
        assertNull(message.getValue().getLedgerAccountId());
        assertNull(message.getValue().getBalanceAmount());
        assertNull(message.getValue().getCurrencyCode());
        verify(acknowledgment).acknowledge();
        verifyNoMoreInteractions(template, acknowledgment);
    }

    @Test
    void malformedPaymentRaisesWithoutSendOrAcknowledgment() {
        assertProcessingFailure(() -> payment.consume(record(PAYMENT_IN, "bad", "not-json"), acknowledgment));
    }

    @Test
    void malformedBalanceRaisesWithoutSendOrAcknowledgment() {
        assertProcessingFailure(() -> balance.consume(record(BALANCE_IN, "bad", "{broken"), acknowledgment));
    }

    @Test
    void jsonNullPaymentRaisesWithoutSendOrAcknowledgment() {
        assertProcessingFailure(() -> payment.consume(record(PAYMENT_IN, "null", "null"), acknowledgment));
    }

    @Test
    void jsonNullBalanceRaisesWithoutSendOrAcknowledgment() {
        assertProcessingFailure(() -> balance.consume(record(BALANCE_IN, "null", "null"), acknowledgment));
    }

    @Test
    void synchronousPaymentSendFailureIsWrappedAndNotAcknowledged() {
        IllegalArgumentException failure = new IllegalArgumentException("synthetic synchronous send failure");
        when(template.send(eq(PAYMENT_OUT), eq("ACC-fail"), any(SettlementRequest.class))).thenThrow(failure);
        IllegalStateException result = assertThrows(IllegalStateException.class, () -> payment.consume(
                record(PAYMENT_IN, "input", "{\"accountId\":\"ACC-fail\",\"amount\":7.25,\"currency\":\"GBP\"}"), acknowledgment));
        assertSame(failure, result.getCause());
        assertEquals("Failed to process Kafka message", result.getMessage());
        verify(template).send(eq(PAYMENT_OUT), eq("ACC-fail"), any(SettlementRequest.class));
        verifyNoMoreInteractions(template);
        verifyNoInteractions(acknowledgment);
    }

    @Test
    void synchronousBalanceSendFailureIsWrappedAndNotAcknowledged() {
        IllegalArgumentException failure = new IllegalArgumentException("synthetic synchronous send failure");
        when(template.send(eq(BALANCE_OUT), isNull(), any(LedgerUpdate.class))).thenThrow(failure);
        IllegalStateException result = assertThrows(IllegalStateException.class, () -> balance.consume(
                record(BALANCE_IN, "input", "{\"accountId\":\"BAL-fail\",\"availableBalance\":9.75,\"currency\":\"JPY\"}"), acknowledgment));
        assertSame(failure, result.getCause());
        assertEquals("Failed to process Kafka message", result.getMessage());
        verify(template).send(eq(BALANCE_OUT), isNull(), any(LedgerUpdate.class));
        verifyNoMoreInteractions(template);
        verifyNoInteractions(acknowledgment);
    }

    @Test
    void producerFactoryKeepsJsonSerializationStringKeysAndAllAcks() {
        KafkaProducerConfig config = new KafkaProducerConfig();
        ReflectionTestUtils.setField(config, "bootstrapServers", "proof.invalid:19092");
        DefaultKafkaProducerFactory<String, Object> factory =
                (DefaultKafkaProducerFactory<String, Object>) config.producerFactory(mapper);
        try {
            Map<String, Object> properties = factory.getConfigurationProperties();
            assertEquals("proof.invalid:19092", properties.get(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG));
            assertEquals("all", properties.get(ProducerConfig.ACKS_CONFIG));
            assertEquals(StringSerializer.class, properties.get(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG));
            assertEquals(JacksonJsonSerializer.class, properties.get(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG));
        } finally {
            factory.destroy();
        }
    }

    @Test
    void consumerFactoryKeepsManualAcknowledgmentAndStringDeserialization() {
        KafkaConsumerConfig config = new KafkaConsumerConfig();
        ReflectionTestUtils.setField(config, "bootstrapServers", "proof.invalid:19092");
        ReflectionTestUtils.setField(config, "groupId", "payment-mediation-group");
        Map<String, Object> properties = config.consumerFactory().getConfigurationProperties();
        assertEquals("proof.invalid:19092", properties.get(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG));
        assertEquals("payment-mediation-group", properties.get(ConsumerConfig.GROUP_ID_CONFIG));
        assertEquals("earliest", properties.get(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG));
        assertEquals(Boolean.FALSE, properties.get(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG));
        assertEquals(StringDeserializer.class, properties.get(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG));
        assertEquals(StringDeserializer.class, properties.get(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG));
        assertEquals(ContainerProperties.AckMode.MANUAL_IMMEDIATE,
                config.kafkaListenerContainerFactory().getContainerProperties().getAckMode());
    }

    @Test
    void generatedListenerAndProducerBindingsUseTheDeclaredRouteProperties() throws Exception {
        assertEquals("${app.kafka.topics.payment-initiated.outbound}",
                PaymentInitiatedProducer.class.getDeclaredField("topic").getAnnotation(Value.class).value());
        assertEquals("${app.kafka.topics.balance-updated.outbound}",
                BalanceUpdatedProducer.class.getDeclaredField("topic").getAnnotation(Value.class).value());
        KafkaListener paymentListener = PaymentInitiatedConsumer.class
                .getMethod("consume", ConsumerRecord.class, Acknowledgment.class).getAnnotation(KafkaListener.class);
        KafkaListener balanceListener = BalanceUpdatedConsumer.class
                .getMethod("consume", ConsumerRecord.class, Acknowledgment.class).getAnnotation(KafkaListener.class);
        assertArrayEquals(new String[] {"${app.kafka.topics.payment-initiated.inbound}"}, paymentListener.topics());
        assertArrayEquals(new String[] {"${app.kafka.topics.balance-updated.inbound}"}, balanceListener.topics());
        assertEquals("kafkaListenerContainerFactory", paymentListener.containerFactory());
        assertEquals("kafkaListenerContainerFactory", balanceListener.containerFactory());
    }

    private ConsumerRecord<String, String> record(String topic, String key, String value) {
        return new ConsumerRecord<>(topic, 2, 17L, key, value);
    }

    private void assertProcessingFailure(org.junit.jupiter.api.function.Executable operation) {
        IllegalStateException error = assertThrows(IllegalStateException.class, operation);
        assertEquals("Failed to process Kafka message", error.getMessage());
        assertNotNull(error.getCause());
        verifyNoInteractions(template, acknowledgment);
    }
}
