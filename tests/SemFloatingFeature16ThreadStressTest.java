package tests;

import com.samsung.android.feature.SemFloatingFeature;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Adversarial 16-Thread Stress Test Harness for SemFloatingFeature.
 * 
 * Target: 50,000+ operations across 16 concurrent threads (800,000 total operations).
 * Stresses:
 * 1. Heavy concurrent reader-writer contention on mFeatures ConcurrentHashMap.
 * 2. Verification that NO ConcurrentModificationException occurs.
 * 3. Strict null-safety: getBoolean(null), getString(null), getInt(null), setFeature(null, val), setFeature(key, null), setFeature(null, null).
 * 4. Invariant preservation: base Samsung flags must never be corrupted or overwritten.
 * 5. Type confusion resilience: Reading Boolean as int, String as bool, Number as string.
 */
public class SemFloatingFeature16ThreadStressTest {

    private static final int NUM_THREADS = 16;
    private static final int OPS_PER_THREAD = 50_000;
    private static final int TOTAL_OPERATIONS = NUM_THREADS * OPS_PER_THREAD; // 800,000

    public static void main(String[] args) throws Exception {
        System.out.println("================================================================================");
        System.out.println("  SEMFLOATINGFEATURE 16-THREAD ADVERSARIAL STRESS TEST HARNESS");
        System.out.println("  Configuration: " + NUM_THREADS + " threads x " + OPS_PER_THREAD + " ops = " + TOTAL_OPERATIONS + " total ops");
        System.out.println("  JVM: " + System.getProperty("java.version") + " (" + System.getProperty("java.vendor") + ")");
        System.out.println("================================================================================");

        run16ThreadConcurrentStress();
        runNullSafetyExhaustiveCheck();
        runTypeConfusionStress();
        runLifecycleResetStress();

        System.out.println("================================================================================");
        System.out.println("  ALL 16-THREAD STRESS HARNESS TESTS COMPLETED CLEANLY WITH ZERO FAILURES!");
        System.out.println("================================================================================");
    }

    private static void run16ThreadConcurrentStress() throws Exception {
        System.out.printf("[PHASE 1] Executing %d operations across %d threads with high contention...%n", TOTAL_OPERATIONS, NUM_THREADS);
        SemFloatingFeature.resetInstance();
        SemFloatingFeature feature = SemFloatingFeature.getInstance();

        ExecutorService executor = Executors.newFixedThreadPool(NUM_THREADS);
        CyclicBarrier startBarrier = new CyclicBarrier(NUM_THREADS);
        CountDownLatch doneLatch = new CountDownLatch(NUM_THREADS);

        AtomicLong totalReads = new AtomicLong(0);
        AtomicLong totalWrites = new AtomicLong(0);
        AtomicLong nullChecks = new AtomicLong(0);
        List<Throwable> caughtExceptions = Collections.synchronizedList(new ArrayList<>());
        List<String> invariantViolations = Collections.synchronizedList(new ArrayList<>());

        long startTime = System.nanoTime();

        for (int t = 0; t < NUM_THREADS; t++) {
            final int threadId = t;
            executor.submit(() -> {
                Random rand = new Random(42 + threadId * 31);
                try {
                    // Synchronize thread release to maximize contention
                    startBarrier.await();

                    for (int op = 0; op < OPS_PER_THREAD; op++) {
                        int role = threadId % 4;

                        if (role == 0 || role == 1) {
                            // 8 threads (0, 1, 4, 5, 8, 9, 12, 13) are pure READERS
                            int readType = op % 5;
                            switch (readType) {
                                case 0:
                                    // Invariant checks on base flags
                                    boolean ltw = feature.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LINK_TO_WINDOWS");
                                    if (!ltw) invariantViolations.add("Thread " + threadId + ": LTW flag returned false!");
                                    boolean knox = feature.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_KNOX", true);
                                    if (knox) invariantViolations.add("Thread " + threadId + ": KNOX flag returned true!");
                                    String brand = feature.getString("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME");
                                    if (!"Samsung".equals(brand)) invariantViolations.add("Thread " + threadId + ": Brand was " + brand);
                                    totalReads.addAndGet(3);
                                    break;
                                case 1:
                                    // Dynamic key read
                                    String dynKey = "DYNAMIC_KEY_" + rand.nextInt(100);
                                    feature.getString(dynKey, "fallback");
                                    feature.getInt(dynKey, -1);
                                    feature.getBoolean(dynKey, false);
                                    totalReads.addAndGet(3);
                                    break;
                                case 2:
                                    // Nonexistent key read
                                    String nonExistent = "NON_EXISTENT_TAG_" + rand.nextInt(10000);
                                    if (feature.getBoolean(nonExistent, false)) invariantViolations.add("Nonexistent bool returned true");
                                    if (!"def".equals(feature.getString(nonExistent, "def"))) invariantViolations.add("Nonexistent str default failed");
                                    if (feature.getInt(nonExistent, 77) != 77) invariantViolations.add("Nonexistent int default failed");
                                    totalReads.addAndGet(3);
                                    break;
                                case 3:
                                    // Null-safety read operations
                                    if (feature.getBoolean(null, false)) invariantViolations.add("getBoolean(null) default failed");
                                    if (feature.getString(null) != null) invariantViolations.add("getString(null) expected null");
                                    if (!"safe".equals(feature.getString(null, "safe"))) invariantViolations.add("getString(null, 'safe') failed");
                                    if (feature.getInt(null, 100) != 100) invariantViolations.add("getInt(null, 100) failed");
                                    nullChecks.addAndGet(4);
                                    break;
                                case 4:
                                    // Enable status check
                                    feature.getEnableStatus("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LTW_REMOTE_APP");
                                    feature.getEnableStatus(null);
                                    totalReads.addAndGet(2);
                                    break;
                            }
                        } else if (role == 2) {
                            // 4 threads (2, 6, 10, 14) are pure WRITERS
                            int writeType = op % 4;
                            switch (writeType) {
                                case 0:
                                    feature.setFeature("DYNAMIC_KEY_" + rand.nextInt(100), "VALUE_" + rand.nextInt(5000));
                                    totalWrites.incrementAndGet();
                                    break;
                                case 1:
                                    feature.setFeature("DYNAMIC_KEY_" + rand.nextInt(100), rand.nextBoolean());
                                    totalWrites.incrementAndGet();
                                    break;
                                case 2:
                                    feature.setFeature("DYNAMIC_KEY_" + rand.nextInt(100), rand.nextInt(100000));
                                    totalWrites.incrementAndGet();
                                    break;
                                case 3:
                                    // Null setter attacks
                                    feature.setFeature(null, "null_key_value");
                                    feature.setFeature("DYNAMIC_KEY_" + rand.nextInt(100), null);
                                    feature.setFeature(null, null);
                                    nullChecks.addAndGet(3);
                                    break;
                            }
                        } else {
                            // 4 threads (3, 7, 11, 15) are MIXED READER-WRITERS
                            String threadKey = "THREAD_" + threadId + "_KEY_" + (op % 50);
                            String threadVal = "T" + threadId + "_VAL_" + op;
                            feature.setFeature(threadKey, threadVal);
                            totalWrites.incrementAndGet();

                            String readBack = feature.getString(threadKey, null);
                            if (readBack != null && !readBack.startsWith("T" + threadId + "_VAL_")) {
                                invariantViolations.add("Thread " + threadId + ": unexpected value " + readBack);
                            }
                            totalReads.incrementAndGet();
                        }
                    }
                } catch (Throwable ex) {
                    caughtExceptions.add(ex);
                } finally {
                    doneLatch.countDown();
                }
            });
        }

        boolean finished = doneLatch.await(30, TimeUnit.SECONDS);
        long elapsedNanos = System.nanoTime() - startTime;
        executor.shutdown();

        assert finished : "Stress test timed out after 30 seconds!";

        double elapsedSeconds = elapsedNanos / 1_000_000_000.0;
        double qps = TOTAL_OPERATIONS / elapsedSeconds;

        System.out.printf("  Duration: %.3f seconds (Throughput: %.1f operations/sec)%n", elapsedSeconds, qps);
        System.out.printf("  Total Reads: %d, Total Writes: %d, Null Operations: %d%n", totalReads.get(), totalWrites.get(), nullChecks.get());
        System.out.printf("  Exceptions Caught: %d, Invariant Violations: %d%n", caughtExceptions.size(), invariantViolations.size());

        if (!caughtExceptions.isEmpty()) {
            System.err.println("FAILED: Exceptions encountered during 16-thread stress test:");
            for (int i = 0; i < Math.min(5, caughtExceptions.size()); i++) {
                caughtExceptions.get(i).printStackTrace();
            }
            throw new AssertionError("16-thread stress test encountered " + caughtExceptions.size() + " exceptions!");
        }

        if (!invariantViolations.isEmpty()) {
            System.err.println("FAILED: Invariant violations detected: " + invariantViolations.subList(0, Math.min(5, invariantViolations.size())));
            throw new AssertionError("Invariant violations: " + invariantViolations.size());
        }

        // Post-stress baseline check
        assert feature.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LINK_TO_WINDOWS") : "Base LTW corrupted";
        assert !feature.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_KNOX") : "Base KNOX corrupted";
        assert "Samsung".equals(feature.getString("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME")) : "Base Brand corrupted";
        System.out.println("  [PHASE 1 RESULT] PASSED - 0 ConcurrentModificationExceptions, 0 NullPointerExceptions, 0 Invariant Violations.");
    }

    private static void runNullSafetyExhaustiveCheck() {
        System.out.println("[PHASE 2] Testing exhaustive null safety across all public API methods...");
        SemFloatingFeature feature = SemFloatingFeature.getInstance();

        // 1. getBoolean null key
        assert !feature.getBoolean(null) : "getBoolean(null) must return false";
        assert feature.getBoolean(null, true) : "getBoolean(null, true) must return true";
        assert !feature.getBoolean(null, false) : "getBoolean(null, false) must return false";

        // 2. getEnableStatus null key
        assert !feature.getEnableStatus(null) : "getEnableStatus(null) must return false";

        // 3. getString null key
        assert feature.getString(null) == null : "getString(null) must return null";
        assert "default_val".equals(feature.getString(null, "default_val")) : "getString(null, default) failed";

        // 4. getInt / getInteger null key
        assert feature.getInt(null) == 0 : "getInt(null) must return 0";
        assert feature.getInt(null, 42) == 42 : "getInt(null, 42) must return 42";
        assert feature.getInteger(null, 99) == 99 : "getInteger(null, 99) must return 99";

        // 5. setFeature null key or null value
        feature.setFeature(null, "some_value");
        feature.setFeature("some_key", null);
        feature.setFeature(null, null);

        // Verify "some_key" was not put as null (which would cause NPE on subsequent queries)
        assert feature.getString("some_key") == null : "some_key should remain unset";
        assert feature.getString("some_key", "fallback").equals("fallback") : "some_key fallback failed";

        System.out.println("  [PHASE 2 RESULT] PASSED - All 5 public API methods exhibit 100% null safety.");
    }

    private static void runTypeConfusionStress() {
        System.out.println("[PHASE 3] Testing type confusion & boundary casting resilience...");
        SemFloatingFeature feature = SemFloatingFeature.getInstance();

        // Put various types
        feature.setFeature("TYPE_INT", 12345);
        feature.setFeature("TYPE_LONG", 9876543210L);
        feature.setFeature("TYPE_DOUBLE", 3.14159);
        feature.setFeature("TYPE_BOOL_TRUE", Boolean.TRUE);
        feature.setFeature("TYPE_BOOL_FALSE", Boolean.FALSE);
        feature.setFeature("TYPE_STR_NUM", "9999");
        feature.setFeature("TYPE_STR_TEXT", "HelloWorld");

        // getInt on Long / Double
        assert feature.getInt("TYPE_INT", 0) == 12345 : "getInt on Integer failed";
        assert feature.getInt("TYPE_LONG", 0) == (int) 9876543210L : "getInt on Long failed";
        assert feature.getInt("TYPE_DOUBLE", 0) == 3 : "getInt on Double failed";

        // getInt on Boolean / String
        assert feature.getInt("TYPE_BOOL_TRUE", -1) == -1 : "getInt on Boolean should return default";
        assert feature.getInt("TYPE_STR_TEXT", -1) == -1 : "getInt on String should return default";

        // getBoolean on non-booleans
        assert !feature.getBoolean("TYPE_INT", false) : "getBoolean on int should return default false";
        assert feature.getBoolean("TYPE_INT", true) : "getBoolean on int should return default true";
        assert !feature.getBoolean("TYPE_STR_TEXT", false) : "getBoolean on string should return default false";

        // getString on numbers and booleans
        assert "12345".equals(feature.getString("TYPE_INT", "")) : "getString on int failed";
        assert "true".equals(feature.getString("TYPE_BOOL_TRUE", "")) : "getString on bool failed";
        assert "HelloWorld".equals(feature.getString("TYPE_STR_TEXT", "")) : "getString on string failed";

        System.out.println("  [PHASE 3 RESULT] PASSED - Type confusion successfully handled without ClassCastException.");
    }

    private static void runLifecycleResetStress() throws Exception {
        System.out.println("[PHASE 4] Testing lifecycle resetInstance() across multiple multi-threaded batches...");
        for (int batch = 0; batch < 5; batch++) {
            SemFloatingFeature.resetInstance();
            SemFloatingFeature instance = SemFloatingFeature.getInstance();
            assert instance != null : "Instance must not be null after reset";

            // Verify clean baseline
            assert instance.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LINK_TO_WINDOWS");
            assert !instance.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_KNOX");

            // Rapid 16-thread read-write burst in each batch (16 x 5,000 = 80,000 ops)
            int numThreads = 16;
            int opsPerThread = 5_000;
            ExecutorService executor = Executors.newFixedThreadPool(numThreads);
            CountDownLatch latch = new CountDownLatch(numThreads);
            List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

            for (int t = 0; t < numThreads; t++) {
                final int tid = t;
                executor.submit(() -> {
                    try {
                        for (int i = 0; i < opsPerThread; i++) {
                            instance.setFeature("BATCH_KEY_" + tid, "VAL_" + i);
                            instance.getString("BATCH_KEY_" + tid, "");
                            instance.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LINK_TO_WINDOWS");
                        }
                    } catch (Throwable ex) {
                        errors.add(ex);
                    } finally {
                        latch.countDown();
                    }
                });
            }
            latch.await(5, TimeUnit.SECONDS);
            executor.shutdown();
            assert errors.isEmpty() : "Errors in batch " + batch + ": " + errors;
        }
        System.out.println("  [PHASE 4 RESULT] PASSED - 5 lifecycle reset batches (400,000 ops) verified cleanly.");
    }
}
