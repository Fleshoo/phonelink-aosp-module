package tests;

import com.samsung.android.feature.SemFloatingFeature;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class JavaSemFloatingFeatureBoundaryTest {

    public static void main(String[] args) throws Exception {
        System.out.println("==================================================");
        System.out.println("  JAVA ADVERSARIAL BOUNDARY TEST: SEMFLOATINGFEATURE");
        System.out.println("  JVM: " + System.getProperty("java.version") + " (" + System.getProperty("java.vendor") + ")");
        System.out.println("==================================================");

        testNullTagHandling();
        testNullMutationsInSetFeature();
        testEmptyAndExtremeTags();
        testUnusualTypesInStorage();
        testConcurrentMutationsAndQueries();

        System.out.println("==================================================");
        System.out.println("  ALL JAVA BOUNDARY TESTS PASSED CLEANLY!");
        System.out.println("==================================================");
    }

    private static void testNullTagHandling() {
        System.out.print("[1/5] Testing null tags on all accessors... ");
        SemFloatingFeature.resetInstance();
        SemFloatingFeature feature = SemFloatingFeature.getInstance();

        // getBoolean
        assert !feature.getBoolean(null) : "getBoolean(null) should be false";
        assert feature.getBoolean(null, true) : "getBoolean(null, true) should be true";
        assert !feature.getBoolean(null, false) : "getBoolean(null, false) should be false";
        assert !feature.getEnableStatus(null) : "getEnableStatus(null) should be false";

        // getString
        assert feature.getString(null) == null : "getString(null) should be null";
        assert "default_str".equals(feature.getString(null, "default_str")) : "getString(null, def) should return default";

        // getInt & getInteger
        assert feature.getInt(null) == 0 : "getInt(null) should be 0";
        assert feature.getInt(null, 999) == 999 : "getInt(null, 999) should return default";
        assert feature.getInteger(null, 888) == 888 : "getInteger(null, 888) should return default";

        System.out.println("PASSED");
    }

    private static void testNullMutationsInSetFeature() {
        System.out.print("[2/5] Testing setFeature with null tag, null value, null both... ");
        SemFloatingFeature feature = SemFloatingFeature.getInstance();

        // ConcurrentHashMap throws NullPointerException if key or value is null.
        // SemFloatingFeature has null guards: if (tag != null && value != null)
        try {
            feature.setFeature(null, "some_value");
            feature.setFeature("some_tag", null);
            feature.setFeature(null, null);
        } catch (NullPointerException npe) {
            assert false : "setFeature threw NullPointerException on null input: " + npe;
        }

        assert feature.getString("some_tag") == null : "some_tag should not be stored";
        System.out.println("PASSED");
    }

    private static void testEmptyAndExtremeTags() {
        System.out.print("[3/5] Testing empty string, whitespace, and 100k-char tags... ");
        SemFloatingFeature feature = SemFloatingFeature.getInstance();

        // Empty string tag
        assert !feature.getBoolean("") : "getBoolean('') should be false";
        assert feature.getBoolean("", true) : "getBoolean('', true) should be true";
        assert feature.getString("") == null : "getString('') should be null";
        assert "fallback".equals(feature.getString("", "fallback")) : "getString('', fallback) failed";
        assert feature.getInt("", 123) == 123 : "getInt('', 123) failed";

        // Whitespace tags
        assert !feature.getBoolean("   ") : "getBoolean('   ') failed";
        assert feature.getInt("\t\n", -1) == -1 : "getInt('\\t\\n') failed";

        // 100k character tag & value
        char[] arr = new char[100_000];
        Arrays.fill(arr, 'Z');
        String hugeTag = "HUGE_" + new String(arr);
        String hugeVal = "VAL_" + new String(arr);
        feature.setFeature(hugeTag, hugeVal);
        assert hugeVal.equals(feature.getString(hugeTag)) : "hugeVal mismatch";

        System.out.println("PASSED");
    }

    private static void testUnusualTypesInStorage() {
        System.out.print("[4/5] Testing unusual types (Double inf/nan, Long, Byte, Short, custom Object)... ");
        SemFloatingFeature feature = SemFloatingFeature.getInstance();

        feature.setFeature("TAG_POS_INF", Double.POSITIVE_INFINITY);
        feature.setFeature("TAG_NEG_INF", Double.NEGATIVE_INFINITY);
        feature.setFeature("TAG_NAN", Double.NaN);
        feature.setFeature("TAG_LONG", Long.MAX_VALUE);
        feature.setFeature("TAG_BYTE", Byte.valueOf((byte) 42));
        feature.setFeature("TAG_SHORT", Short.valueOf((short) 1234));
        feature.setFeature("TAG_FLOAT", Float.valueOf(3.75f));
        feature.setFeature("TAG_BOOL_TRUE", Boolean.TRUE);
        feature.setFeature("TAG_INT_NUM", 9999);

        // In Java: val instanceof Number -> ((Number) val).intValue()
        assert feature.getInt("TAG_POS_INF", 0) == Integer.MAX_VALUE : "POS_INF intValue should be Integer.MAX_VALUE";
        assert feature.getInt("TAG_NEG_INF", 0) == Integer.MIN_VALUE : "NEG_INF intValue should be Integer.MIN_VALUE";
        assert feature.getInt("TAG_NAN", -1) == 0 : "NaN intValue should be 0";
        assert feature.getInt("TAG_LONG", 0) == -1 : "Long.MAX_VALUE intValue should be -1";
        assert feature.getInt("TAG_BYTE", 0) == 42 : "Byte intValue should be 42";
        assert feature.getInt("TAG_SHORT", 0) == 1234 : "Short intValue should be 1234";
        assert feature.getInt("TAG_FLOAT", 0) == 3 : "Float intValue should be 3";

        // Cross-type access:
        // getInt on Boolean -> Boolean is not Number -> returns default
        assert feature.getInt("TAG_BOOL_TRUE", 77) == 77 : "getInt on Boolean should return default";

        // getBoolean on Integer -> Integer is not Boolean -> returns default
        assert !feature.getBoolean("TAG_INT_NUM", false) : "getBoolean on Integer should return default (false)";
        assert feature.getBoolean("TAG_INT_NUM", true) : "getBoolean on Integer should return default (true)";

        // Custom object on getString -> returns val.toString()
        Object customObj = new Object() {
            @Override
            public String toString() {
                return "CUSTOM_TO_STRING";
            }
        };
        feature.setFeature("TAG_CUSTOM_OBJ", customObj);
        assert "CUSTOM_TO_STRING".equals(feature.getString("TAG_CUSTOM_OBJ")) : "getString on Object failed";

        System.out.println("PASSED");
    }

    private static void testConcurrentMutationsAndQueries() throws Exception {
        System.out.print("[5/5] Testing 100,000 rapid concurrent queries + mutations across 50 threads... ");
        SemFloatingFeature feature = SemFloatingFeature.getInstance();
        int totalOps = 100_000;
        int numThreads = 50;
        int opsPerThread = totalOps / numThreads;

        ExecutorService executor = Executors.newFixedThreadPool(numThreads);
        AtomicInteger opsCount = new AtomicInteger(0);
        List<String> errors = Collections.synchronizedList(new ArrayList<>());

        long t0 = System.nanoTime();
        List<Future<?>> futures = new ArrayList<>();
        for (int t = 0; t < numThreads; t++) {
            final int tid = t;
            futures.add(executor.submit(() -> {
                Random rand = new Random();
                for (int i = 0; i < opsPerThread; i++) {
                    try {
                        int action = rand.nextInt(5);
                        String key = "TAG_CONCURRENT_" + rand.nextInt(20);
                        if (action == 0) {
                            // Mutate
                            feature.setFeature(key, "V_" + rand.nextInt(1000));
                        } else if (action == 1) {
                            feature.getBoolean("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LINK_TO_WINDOWS");
                        } else if (action == 2) {
                            feature.getString(key, "default");
                        } else if (action == 3) {
                            feature.getInt(key, 0);
                        } else {
                            feature.setFeature(null, null); // null mutation stress
                            feature.getBoolean(null, true);
                        }
                        opsCount.incrementAndGet();
                    } catch (Exception e) {
                        errors.add("Thread " + tid + " failed: " + e);
                    }
                }
            }));
        }

        for (Future<?> f : futures) {
            f.get(10, TimeUnit.SECONDS);
        }
        long dt = System.nanoTime() - t0;
        executor.shutdown();

        assert errors.isEmpty() : "Errors during concurrent stress: " + errors;
        assert opsCount.get() == totalOps : "Ops count mismatch: " + opsCount.get();

        double ms = dt / 1_000_000.0;
        System.out.printf("PASSED (100,000 ops in %.2f ms, %.1f ops/sec)%n", ms, (totalOps / (ms / 1000.0)));
    }
}
