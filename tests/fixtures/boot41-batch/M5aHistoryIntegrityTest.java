package @PACKAGE@;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.InvocationTargetException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import @PACKAGE@.batch.WidgetEodBatchJob;
import @BATCH@.JobExecution;
import @BATCH@.JobInstance;
import @PARAMS@.JobParameters;
import @PARAMS@.JobParametersBuilder;
import org.springframework.batch.core.repository.JobRepository;
import @HISTORY_IMPORT@;
import org.springframework.transaction.PlatformTransactionManager;

class M5aHistoryIntegrityTest {
    private final LocalDate originalDate = LocalDate.of(2026, 9, 27);
    private final JobInstance instance = new JobInstance(7L, "widgetEodJob");

    private JobParameters parameters(String date) {
        return new JobParametersBuilder().addString("runId", "history-run", true)
                .addLocalDate("businessDate", LocalDate.parse(date), false).toJobParameters();
    }

    private JobExecution execution(long id, JobParameters params) {
        return @EXECUTION_CTOR@;
    }

    private LocalDate decide(JobExecution current, List<JobExecution> history) throws Exception {
        var method = WidgetEodBatchJob.class.getDeclaredMethod("authoritativeBusinessDate", JobExecution.class, List.class);
        method.setAccessible(true);
        try {
            return (LocalDate) method.invoke(null, current, history);
        } catch (InvocationTargetException exception) {
            throw (Exception) exception.getCause();
        }
    }

    @Test void firstDurableExecutionEstablishesOriginWithoutContext() throws Exception {
        var current = execution(11, parameters("2026-09-27"));
        assertEquals(originalDate, decide(current, List.of(current)));
        assertTrue(current.getExecutionContext().isEmpty());
    }

    @Test void rejectedAttemptsAndShuffledTiedOrReversedTimestampsCannotRebindOrPoison() throws Exception {
        var origin = execution(11, parameters("2026-09-27"));
        var earlyAgain = execution(19, parameters("2026-09-27"));
        var rejected = execution(27, parameters("2026-09-28"));
        var rejectedAgain = execution(31, parameters("2026-09-29"));
        var retry = execution(45, parameters("2026-09-27"));
        var history = new ArrayList<>(List.of(origin, earlyAgain, rejected, rejectedAgain, retry));
        origin.setCreateTime(LocalDateTime.of(2030, 1, 1, 0, 0));
        for (var execution : List.of(earlyAgain, rejected, rejectedAgain, retry)) {
            execution.setCreateTime(LocalDateTime.of(2000, 1, 1, 0, 0));
        }
        assertThrows(IllegalStateException.class, () -> decide(rejected, List.of(origin, earlyAgain, rejected)));
        for (int i = 0; i < history.size(); i++) {
            Collections.rotate(history, 1);
            assertEquals(originalDate, decide(retry, history));
        }
        for (var execution : history) assertTrue(execution.getExecutionContext().isEmpty());
    }

    @ParameterizedTest
    @ValueSource(strings = {"null-history", "empty-history", "missing-current", "null-record", "duplicate-id",
            "zero-id", "future-id", "wrong-instance", "missing-date", "string-date", "identifying-date",
            "missing-runId", "blank-runId", "wrong-runId", "nonidentifying-runId", "extra-identity",
            "frozen-conflict", "frozen-malformed", "context-owner", "context-date", "current-contradiction"})
    void invalidHistoryFailsClosedWithoutChangingContexts(String fault) throws Exception {
        var origin = execution(11, parameters("2026-09-27"));
        var current = execution(19, parameters("2026-09-27"));
        List<JobExecution> history = new ArrayList<>(List.of(origin, current));
        var builder = new JobParametersBuilder().addString("runId", "history-run", true);
        switch (fault) {
            case "null-history" -> history = null;
            case "empty-history" -> history.clear();
            case "missing-current" -> history.remove(current);
            case "null-record" -> history.add(null);
            case "duplicate-id" -> history.add(origin);
            case "zero-id" -> history.set(0, execution(0, origin.getJobParameters()));
            case "future-id" -> history.set(0, execution(21, origin.getJobParameters()));
            case "wrong-instance" -> history.set(0, @OTHER_EXECUTION_CTOR@);
            case "missing-date" -> history.set(0, execution(11, builder.toJobParameters()));
            case "string-date" -> history.set(0, execution(11, builder.addString("businessDate", "2026-09-27", false).toJobParameters()));
            case "identifying-date" -> history.set(0, execution(11, builder.addLocalDate("businessDate", originalDate, true).toJobParameters()));
            case "missing-runId" -> history.set(0, execution(11, new JobParametersBuilder().addLocalDate("businessDate", originalDate, false).toJobParameters()));
            case "blank-runId" -> history.set(0, execution(11, new JobParametersBuilder().addString("runId", " ", true).addLocalDate("businessDate", originalDate, false).toJobParameters()));
            case "wrong-runId" -> history.set(0, execution(11, new JobParametersBuilder().addString("runId", "other", true).addLocalDate("businessDate", originalDate, false).toJobParameters()));
            case "nonidentifying-runId" -> history.set(0, execution(11, new JobParametersBuilder().addString("runId", "history-run", false).addLocalDate("businessDate", originalDate, false).toJobParameters()));
            case "extra-identity" -> history.set(0, execution(11, builder.addLocalDate("businessDate", originalDate, false).addLong("extra", 1L, true).toJobParameters()));
            case "frozen-conflict" -> origin.getExecutionContext().putString("frozenBusinessDate", "2026-09-28");
            case "frozen-malformed" -> origin.getExecutionContext().put("frozenBusinessDate", 42L);
            case "context-owner" -> current.getExecutionContext().putString("runId", "other");
            case "context-date" -> current.getExecutionContext().putString("businessDate", "invalid");
            case "current-contradiction" -> history.set(1, execution(19, parameters("2026-09-28")));
            default -> fail(fault);
        }
        var supplied = history;
        var originContext = origin.getExecutionContext().toMap();
        var currentContext = current.getExecutionContext().toMap();
        var failure = assertThrows(IllegalStateException.class, () -> decide(current, supplied));
        assertTrue(failure.getMessage().startsWith("M5a integrity:"), failure.getMessage());
        assertEquals(originContext, origin.getExecutionContext().toMap());
        assertEquals(currentContext, current.getExecutionContext().toMap());
    }

    @Test void failedCompleteHistoryReadIsNotAFirstExecutionFallback() throws Exception {
        var repo = mock(JobRepository.class);
        var history = @HISTORY_MOCK@;
        var current = execution(11, parameters("2026-09-27"));
        when(history.getJobExecutions(instance)).thenThrow(new IllegalStateException("synthetic read failure"));
        var step = new WidgetEodBatchJob().widgetRunIdentityStep(@STEP_ARGUMENTS@, mock(PlatformTransactionManager.class));
        var tasklet = ((@TASKLET_STEP@) step).getTasklet();
        var contribution = new @CONTRIBUTION@(new @STEP_EXECUTION@("widgetRunIdentityStep", current));
        var failure = assertThrows(IllegalStateException.class, () -> tasklet.execute(contribution, null));
        assertTrue(failure.getMessage().contains("complete execution history unavailable"));
        assertTrue(current.getExecutionContext().isEmpty());
        verify(repo, never()).updateExecutionContext(current);
    }

    @Test void changedRetryWithoutFrozenContextUsesOriginalDurableParameters() throws Exception {
        var repo = mock(JobRepository.class);
        var history = @HISTORY_MOCK@;
        var origin = execution(11, parameters("2026-09-27"));
        var current = execution(19, parameters("2026-09-28"));
        when(history.getJobExecutions(instance)).thenReturn(List.of(current, origin));
        var step = new WidgetEodBatchJob().widgetRunIdentityStep(@STEP_ARGUMENTS@, mock(PlatformTransactionManager.class));
        var tasklet = ((@TASKLET_STEP@) step).getTasklet();
        var contribution = new @CONTRIBUTION@(new @STEP_EXECUTION@("widgetRunIdentityStep", current));
        var failure = assertThrows(IllegalStateException.class, () -> tasklet.execute(contribution, null));
        assertTrue(failure.getMessage().contains("businessDate mismatch"));
        assertTrue(current.getExecutionContext().isEmpty());
        verify(repo, never()).updateExecutionContext(current);
    }
}
