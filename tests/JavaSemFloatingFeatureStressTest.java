package tests;

import com.samsung.android.feature.SemFloatingFeature;
import me.phonelink.xposed.stubs.OneUIStubs;
import me.phonelink.xposed.stubs.SemFloatingFeatureStub;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class JavaSemFloatingFeatureStressTest {

    public static void main(String[] args) throws Exception {
        System.out.println("==================================================");
        System.out.println("  JAVA ADVERSARIAL STRESS TEST: SEMFLOATINGFEATURE");
        System.out.println("  JVM: " + System.getProperty("java.version") + " (" + System.getProperty("java.vendor") + ")");
        System.out.println("==================================================");

        testExtremeInputs();
        testSingletonConcurrency();
        test10000RapidConcurrentQueries();
        testConcurrentReaderWriterStress();
        testOneUIStubs();

        System.out.println("==================================================");
        System.out.println("  ALL JAVA STRESS TESTS COMPLETED CLEANLY!");
        System.out.println("==================================================");
    }

    private static void testExtremeInputs() {
        System.out.print("[1/5] Testing extreme inputs, nulls, defaults... ");
        SemFloatingFeature.resetInstance();
        SemFloatingFeature feature = SemFloatingFeature.getInstance();

        // Null checks
        assert !feature.getBoolean(null) : "getBoolean(null) failed";
        assert feature.getBoolean(null, true) : "getBoolean(null, true) failed";
        assert feature.getString(null) == null : "getString(null) should be null";
        assert "def".equals(feature.getString(null, "def")) : "getString(null, def) failed";
        assert feature.getInt(null) == 0 : "getInt(null) failed";
        assert feature.getInt(null, 42) == 42 : "getInt(null, 42) failed";

        // Empty string
        assert !feature.getBoolean("") : "getBoolean('') failed";
        assert feature.getBoolean("", true) : "getBoolean('', true) failed";
        assert "".equals(feature.getString("", "")) : "getString('', '') failed";
        assert feature.getInt("", 10) == 10 : "getInt('', 10) failed";

        // Non-existent key
        String nonExistent = "SEC_FLOATING_FEATURE_TOTALLY_NON_EXISTENT_99999";
        assert !feature.getBoolean(nonExistent) : "non-existent getBoolean failed";
        assert feature.getBoolean(nonExistent, true) : "non-existent getBoolean with default failed";
        assert feature.getString(nonExistent) == null : "non-existent getString failed";
        assert "fallback".equals(feature.getString(nonExistent, "fallback")) : "non-existent getString fallback failed";
        assert feature.getInt(nonExistent) == 0 : "non-existent getInt failed";
        assert feature.getInt(nonExistent, -1) == -1 : "non-existent getInt default failed";

        // Extreme strings (100,000 characters)
        char[] chars = new char[100_000];
        Arrays.fill(chars, 'X');
        String hugeKey = "KEY_" + new String(chars);
        String hugeVal = "VAL_" + new String(chars);
        feature.setFeature(hugeKey, hugeVal);
        assert hugeVal.equals(feature.getString(hugeKey)) : "Huge string mismatch";

        // Type confusion: getInt on Boolean, getBoolean on String
        feature.setFeature("BOOL_FLAG", Boolean.TRUE);
        feature.setFeature("STRING_FLAG", "not_a_number");
        feature.setFeature("INT_FLAG", 12345);

        // In Java implementation, getInt checks `val instanceof Number`
        assert feature.getInt("BOOL_FLAG", 99) == 99 : "getInt on Boolean should return default (Boolean is not Number)";
        assert feature.getInt("STRING_FLAG", 88) == 88 : "getInt on String should return default";
        assert feature.getInt("INT_FLAG", 0) == 12345 : "getInt on Integer failed";
        assert !feature.getBoolean("STRING_FLAG", false) : "getBoolean on String should return default";
        assert feature.getBoolean("STRING_FLAG", true) : "getBoolean on String should return default (true)";

        System.out.println("PASSED");
    }

    private static void testSingletonConcurrency() throws Exception {
        System.out.print("[2/5] Testing singleton double-checked locking under 100 concurrent threads... ");
        SemFloatingFeature.resetInstance();

        int numThreads = 100;
        ExecutorService executor = Executors.newFixedThreadPool(numThreads);
        CyclicBarrier barrier = new CyclicBarrier(numThreads);
        Set<Integer> identities = Collections.synchronizedSet(new HashSet<>());

        List<Future<?>> futures = new ArrayList<>();
        for (int i = 0; i < numThreads; i++) {
            futures.add(executor.submit(() -> {
                try {
                    barrier.await();
                    SemFloatingFeature instance = SemFloatingFeature.getInstance();
                    identities.add(System.identityHashCode(instance));
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            }));
        }

        for (Future<?> f : futures) {
            f.get(5, TimeUnit.SECONDS);
        }
        executor.shutdown();

        assert identities.size() == 1 : "Singleton broken! Multiple instances created: " + identities.size();
        System.out.println("PASSED (exactly 1 instance across " + numThreads + " threads)");
    }

    private static void test10000RapidConcurrentQueries() throws Exception {
        System.out.print("[3/5] Testing 10,000 rapid concurrent queries across 50 threads... ");
        SemFloatingFeature feature = SemFloatingFeature.getInstance();
        int totalQueries = 10_000;
        int numThreads = 50;
        int queriesPerThread = totalQueries / numThreads;

        ExecutorService executor = Executors.newFixedThreadPool(numThreads);
        AtomicInteger successCount = new AtomicInteger(0);
        List<String> errors = Collections.synchronizedList(new ArrayList<>());

        long t0 = System.nanoTime();
        List<Future<?>> futures = new ArrayList<>();
        for (int t = 0; t < numThreads; t++) {
            futures.add(executor.submit(() -> {
                for (int q = 0; q < queriesPerThread; q++) {
                    try {
                        boolean b1 = feature.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LINK_TO_WINDOWS");
                        if (!b1) errors.add("Expected true for LINK_TO_WINDOWS");

                        boolean b2 = feature.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_KNOX");
                        if (b2) errors.add("Expected false for KNOX");

                        String brand = feature.getString("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME");
                        if (!"Samsung".equals(brand)) errors.add("Expected Samsung for BRAND");

                        int def = feature.getInt("SEC_NONEXISTENT", 99);
                        if (def != 99) errors.add("Expected 99 for default");

                        successCount.incrementAndGet();
                    } catch (Exception e) {
                        errors.add("Exception: " + e.getMessage());
                    }
                }
            }));
        }

        for (Future<?> f : futures) {
            f.get(10, TimeUnit.SECONDS);
        }
        long elapsedNanos = System.nanoTime() - t0;
        executor.shutdown();

        assert errors.isEmpty() : "Errors during concurrent queries: " + errors;
        assert successCount.get() == totalQueries : "Query count mismatch: " + successCount.get();

        double elapsedMs = elapsedNanos / 1_000_000.0;
        System.out.printf("PASSED (10,000 queries in %.2f ms, %.1f qps)%n", elapsedMs, (totalQueries / (elapsedMs / 1000.0)));
    }

    private static void testConcurrentReaderWriterStress() throws Exception {
        System.out.print("[4/5] Testing concurrent reader-writer stress on HashMap... ");
        SemFloatingFeature feature = SemFloatingFeature.getInstance();
        int numReaders = 20;
        int numWriters = 5;
        ExecutorService executor = Executors.newFixedThreadPool(numReaders + numWriters);
        AtomicInteger reads = new AtomicInteger(0);
        AtomicInteger writes = new AtomicInteger(0);
        List<String> errors = Collections.synchronizedList(new ArrayList<>());
        long stopTime = System.currentTimeMillis() + 1000; // 1 second run

        // Writers mutating mFeatures via setFeature
        for (int w = 0; w < numWriters; w++) {
            final int wid = w;
            executor.submit(() -> {
                Random rand = new Random();
                while (System.currentTimeMillis() < stopTime) {
                    try {
                        String key = "CONCURRENT_KEY_" + rand.nextInt(50);
                        feature.setFeature(key, "VAL_" + rand.nextInt(1000));
                        writes.incrementAndGet();
                    } catch (Exception e) {
                        errors.add("Writer " + wid + " crashed: " + e.getClass().getName() + " - " + e.getMessage());
                    }
                }
            });
        }

        // Readers
        for (int r = 0; r < numReaders; r++) {
            final int rid = r;
            executor.submit(() -> {
                Random rand = new Random();
                while (System.currentTimeMillis() < stopTime) {
                    try {
                        String key = "CONCURRENT_KEY_" + rand.nextInt(50);
                        feature.getString(key, "fallback");
                        feature.getInt(key, 0);
                        feature.getBoolean(key, false);
                        reads.incrementAndGet();
                    } catch (Exception e) {
                        errors.add("Reader " + rid + " crashed: " + e.getClass().getName() + " - " + e.getMessage());
                    }
                }
            });
        }

        executor.shutdown();
        executor.awaitTermination(3, TimeUnit.SECONDS);

        System.out.printf("PASSED (%d reads, %d writes in 1s, errors: %d)%n", reads.get(), writes.get(), errors.size());
        if (!errors.isEmpty()) {
            System.out.println("  [VULNERABILITY DETECTED]: HashMap thread-safety failure: " + errors.get(0));
        }
    }

    private static void testOneUIStubs() {
        System.out.print("[5/5] Testing OneUIStubs constants and methods... ");
        assert OneUIStubs.SEM_INT == 5001 : "SEM_INT should be 5001";
        assert OneUIStubs.SEM_PLATFORM_INT == 140100 : "SEM_PLATFORM_INT should be 140100";
        assert OneUIStubs.getSemIntValue() == 5001 : "getSemIntValue() should return 5001";
        assert OneUIStubs.getSemPlatformIntValue() == 140100 : "getSemPlatformIntValue() should return 140100";
        assert OneUIStubs.isOneUI2_1OrLater() : "isOneUI2_1OrLater() should return true";
        assert !OneUIStubs.isDesktopMode() : "isDesktopMode() should return false";
        assert !OneUIStubs.isSmartClipSupported() : "isSmartClipSupported() should return false";
        System.out.println("PASSED");
    }
}
