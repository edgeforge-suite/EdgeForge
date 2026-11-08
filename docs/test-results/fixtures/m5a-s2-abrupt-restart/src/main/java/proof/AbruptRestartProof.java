package proof;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.repository.support.JobRepositoryFactoryBean;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

public final class AbruptRestartProof {
    private AbruptRestartProof() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            throw new IllegalArgumentException("usage: probe | init | launch <runId> <businessDate>");
        }

        DataSource dataSource = dataSource();
        if ("probe".equals(args[0])) {
            try (Connection connection = dataSource.getConnection();
                    Statement statement = connection.createStatement()) {
                statement.setQueryTimeout(requiredPositiveInt("JDBC_PROBE_TIMEOUT_SECONDS"));
                try (ResultSet result = statement.executeQuery("SELECT 1")) {
                    if (!result.next() || result.getInt(1) != 1) {
                        throw new IllegalStateException("PostgreSQL readiness query returned no result");
                    }
                }
            }
            System.out.println("POSTGRES_JDBC_READY");
            return;
        }
        if ("init".equals(args[0])) {
            ResourceDatabasePopulator populator = new ResourceDatabasePopulator(
                    new ClassPathResource("org/springframework/batch/core/schema-postgresql.sql"));
            populator.execute(dataSource);
            System.out.println("BATCH_SCHEMA_INITIALIZED");
            return;
        }
        if (!"launch".equals(args[0]) || args.length != 3) {
            throw new IllegalArgumentException("usage: probe | init | launch <runId> <businessDate>");
        }

        PlatformTransactionManager transactionManager = new JdbcTransactionManager(dataSource);
        JobRepository jobRepository = jobRepository(dataSource, transactionManager);
        JobLauncher launcher = jobLauncher(jobRepository);
        Job job = job(jobRepository, transactionManager);
        JobParameters parameters = new JobParametersBuilder()
                .addString("runId", args[1], true)
                .addString("businessDate", args[2], false)
                .toJobParameters();

        try {
            JobExecution execution = launcher.run(job, parameters);
            System.out.println("LAUNCH_RETURNED=" + execution.getStatus());
        } catch (JobExecutionAlreadyRunningException exception) {
            System.out.println("LAUNCH_EXCEPTION=" + exception.getClass().getName());
            System.out.println("LAUNCH_MESSAGE=" + exception.getMessage());
            System.exit(23);
        }
    }

    private static DataSource dataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl(required("JDBC_URL"));
        dataSource.setUsername(required("JDBC_USER"));
        dataSource.setPassword(required("JDBC_PASSWORD"));
        return dataSource;
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(name + " is required");
        }
        return value;
    }

    private static int requiredPositiveInt(String name) {
        String value = required(name);
        try {
            int parsed = Integer.parseInt(value);
            if (parsed > 0) {
                return parsed;
            }
        } catch (NumberFormatException exception) {
            throw new IllegalStateException(name + " must be a positive integer", exception);
        }
        throw new IllegalStateException(name + " must be a positive integer");
    }

    private static JobRepository jobRepository(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) throws Exception {
        JobRepositoryFactoryBean factory = new JobRepositoryFactoryBean();
        factory.setDataSource(dataSource);
        factory.setTransactionManager(transactionManager);
        factory.setDatabaseType("POSTGRES");
        factory.afterPropertiesSet();
        return factory.getObject();
    }

    private static JobLauncher jobLauncher(JobRepository jobRepository) throws Exception {
        TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
        launcher.setJobRepository(jobRepository);
        launcher.afterPropertiesSet();
        return launcher;
    }

    private static Job job(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager) {
        Step identityStep = new StepBuilder("runIdentity", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    JobExecution jobExecution = contribution.getStepExecution().getJobExecution();
                    ExecutionContext context = jobExecution.getExecutionContext();
                    String supplied = jobExecution.getJobParameters().getString("businessDate");
                    if (context.containsKey("frozenBusinessDate")) {
                        String frozen = context.getString("frozenBusinessDate");
                        if (!frozen.equals(supplied)) {
                            throw new IllegalStateException(
                                    "businessDate mismatch: frozen=" + frozen + ", supplied=" + supplied);
                        }
                    } else {
                        context.putString("frozenBusinessDate", supplied);
                        jobRepository.updateExecutionContext(jobExecution);
                    }
                    System.out.println("IDENTITY_STEP_ACCEPTED=" + supplied);
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .allowStartIfComplete(true)
                .build();

        Step dataStep = new StepBuilder("dataStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    System.out.println("DATA_STEP_WAITING");
                    System.out.flush();
                    while (true) {
                        Thread.sleep(1_000L);
                    }
                }, transactionManager)
                .build();

        return new JobBuilder("m5aS2AbruptRestart", jobRepository)
                .start(identityStep)
                .next(dataStep)
                .build();
    }
}
