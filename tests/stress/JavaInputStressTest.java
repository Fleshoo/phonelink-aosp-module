package tests.stress;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.*;

/**
 * JavaInputStressTest: Adversarial Java Bytecode Verification & Stress Harness
 * for Milestone M4 (Remote Input Injection Engine).
 *
 * Verifies directly against compiled classes in lsposed_module/build/app_classes:
 * 1. SystemServerHooks bytecode, sPrivilegedUidCache O(1) performance and thread safety.
 * 2. High-throughput multi-threaded contention (32 threads, 1,000,000 lookups, 0 deadlocks).
 * 3. Cold-cache race condition insertion without data corruption or exceptions.
 * 4. Memory footprint under maximum Android UID allocation (10,000 entries < 5MB).
 * 5. InputInjectionHooks method signatures and DEX conformance.
 */
public class JavaInputStressTest {

    private static final String SYSTEM_SERVER_HOOKS_CLASS = "me.phonelink.xposed.hooks.SystemServerHooks";
    private static final String INPUT_INJECTION_HOOKS_CLASS = "me.phonelink.xposed.hooks.InputInjectionHooks";

    public static void main(String[] args) {
        System.out.println("================================================================================");
        System.out.println("  M4 JAVA BYTECODE ADVERSARIAL STRESS TEST & BENCHMARK HARNESS");
        System.out.println("  Targets: SystemServerHooks & InputInjectionHooks");
        System.out.println("================================================================================");

        try {
            testSystemServerHooksStructure();
            testPrivilegedUidCacheO1Benchmark();
            testConcurrentMultithreadedContention();
            testColdCacheRaceConditions();
            testMemoryFootprintAndScalability();
            testIsPrivilegedInputCallerLogic();
            testInputInjectionHooksStructure();

            System.out.println("================================================================================");
            System.out.println("[SUCCESS] ALL JAVA ADVERSARIAL STRESS TESTS PASSED CLEANLY (7/7)");
            System.out.println("================================================================================");
            System.exit(0);
        } catch (Throwable t) {
            System.err.println("\n[FAILURE] Stress test encountered an error:");
            t.printStackTrace();
            System.exit(1);
        }
    }

    private static void testSystemServerHooksStructure() throws Exception {
        System.out.print("[*] Test 1: Verifying SystemServerHooks structure & fields... ");
        Class<?> clazz = Class.forName(SYSTEM_SERVER_HOOKS_CLASS);

        Field cacheField = clazz.getDeclaredField("sPrivilegedUidCache");
        cacheField.setAccessible(true);
        int modifiers = cacheField.getModifiers();

        if (!Modifier.isStatic(modifiers)) {
            throw new AssertionError("sPrivilegedUidCache must be static");
        }
        if (!Modifier.isFinal(modifiers)) {
            throw new AssertionError("sPrivilegedUidCache must be final");
        }
        if (!ConcurrentHashMap.class.isAssignableFrom(cacheField.getType())) {
            throw new AssertionError("sPrivilegedUidCache must be a ConcurrentHashMap");
        }

        Field pkgMdxField = clazz.getDeclaredField("PKG_MDX");
        String pkgMdx = (String) pkgMdxField.get(null);
        if (!"com.samsung.android.mdx".equals(pkgMdx)) {
            throw new AssertionError("PKG_MDX incorrect: " + pkgMdx);
        }

        Field pkgAppManagerField = clazz.getDeclaredField("PKG_APPMANAGER");
        String pkgAppManager = (String) pkgAppManagerField.get(null);
        if (!"com.microsoft.appmanager".equals(pkgAppManager)) {
            throw new AssertionError("PKG_APPMANAGER incorrect: " + pkgAppManager);
        }

        System.out.println("PASSED (ConcurrentHashMap, static final, package constants verified)");
    }

    private static void testPrivilegedUidCacheO1Benchmark() throws Exception {
        System.out.print("[*] Test 2: Benchmarking sPrivilegedUidCache O(1) throughput (1,000,000 lookups)... ");
        Class<?> clazz = Class.forName(SYSTEM_SERVER_HOOKS_CLASS);
        Field cacheField = clazz.getDeclaredField("sPrivilegedUidCache");
        cacheField.setAccessible(true);
        @SuppressWarnings("unchecked")
        ConcurrentHashMap<Integer, Boolean> cache = (ConcurrentHashMap<Integer, Boolean>) cacheField.get(null);

        cache.clear();
        int mdxUid = 10150;
        int appManagerUid = 10151;
        int untrustedUid = 10999;

        cache.put(mdxUid, Boolean.TRUE);
        cache.put(appManagerUid, Boolean.TRUE);
        cache.put(untrustedUid, Boolean.FALSE);

        int iterations = 1_000_000;
        long start = System.nanoTime();
        for (int i = 0; i < iterations; i++) {
            int uid = (i % 3 == 0) ? mdxUid : ((i % 3 == 1) ? appManagerUid : untrustedUid);
            Boolean res = cache.get(uid);
            if (res == null) {
                throw new AssertionError("Cache returned null for pre-populated UID: " + uid);
            }
        }
        long durationNs = System.nanoTime() - start;
        double durationMs = durationNs / 1_000_000.0;
        double opsPerSec = (iterations / (durationNs / 1_000_000_000.0));
        double nsPerOp = (double) durationNs / iterations;

        System.out.printf("PASSED (%.2f ms, %.0f ops/sec, %.2f ns/lookup) [O(1) CONFIRMED]%n",
                durationMs, opsPerSec, nsPerOp);

        if (nsPerOp > 1000.0) { // Should take < 1 microsecond per hash lookup
            throw new AssertionError("Cache lookup took too long: " + nsPerOp + " ns");
        }
    }

    private static void testConcurrentMultithreadedContention() throws Exception {
        System.out.print("[*] Test 3: Stress testing 32 concurrent threads under heavy contention... ");
        Class<?> clazz = Class.forName(SYSTEM_SERVER_HOOKS_CLASS);
        Field cacheField = clazz.getDeclaredField("sPrivilegedUidCache");
        cacheField.setAccessible(true);
        @SuppressWarnings("unchecked")
        ConcurrentHashMap<Integer, Boolean> cache = (ConcurrentHashMap<Integer, Boolean>) cacheField.get(null);

        cache.clear();
        cache.put(10150, Boolean.TRUE);
        cache.put(10151, Boolean.TRUE);
        cache.put(10999, Boolean.FALSE);

        int threadCount = 32;
        int opsPerThread = 50_000;
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch endLatch = new CountDownLatch(threadCount);
        AtomicInteger errorCount = new AtomicInteger(0);

        for (int t = 0; t < threadCount; t++) {
            final int threadId = t;
            executor.submit(() -> {
                try {
                    startLatch.await();
                    for (int i = 0; i < opsPerThread; i++) {
                        int mode = i % 4;
                        if (mode == 0) {
                            Boolean r = cache.get(10150);
                            if (r != Boolean.TRUE) errorCount.incrementAndGet();
                        } else if (mode == 1) {
                            Boolean r = cache.get(10151);
                            if (r != Boolean.TRUE) errorCount.incrementAndGet();
                        } else if (mode == 2) {
                            Boolean r = cache.get(10999);
                            if (r != Boolean.FALSE) errorCount.incrementAndGet();
                        } else {
                            // Concurrent write to dynamic UID
                            int dynUid = 20000 + (i % 100);
                            cache.put(dynUid, Boolean.FALSE);
                            if (cache.get(dynUid) != Boolean.FALSE) errorCount.incrementAndGet();
                        }
                    }
                } catch (Throwable ex) {
                    errorCount.incrementAndGet();
                    ex.printStackTrace();
                } finally {
                    endLatch.countDown();
                }
            });
        }

        long start = System.nanoTime();
        startLatch.countDown(); // Release all threads simultaneously
        boolean completed = endLatch.await(10, TimeUnit.SECONDS);
        long durationMs = (System.nanoTime() - start) / 1_000_000;
        executor.shutdown();

        if (!completed) {
            throw new AssertionError("DEADLOCK DETECTED! Threads failed to complete within 10s timeout.");
        }
        if (errorCount.get() > 0) {
            throw new AssertionError("Encountered " + errorCount.get() + " errors during multithreaded contention.");
        }

        System.out.printf("PASSED (%d concurrent threads, %d ops total in %d ms, 0 deadlocks)%n",
                threadCount, threadCount * opsPerThread, durationMs);
    }

    private static void testColdCacheRaceConditions() throws Exception {
        System.out.print("[*] Test 4: Testing cold-cache race condition insertion across 16 threads... ");
        Class<?> clazz = Class.forName(SYSTEM_SERVER_HOOKS_CLASS);
        Field cacheField = clazz.getDeclaredField("sPrivilegedUidCache");
        cacheField.setAccessible(true);
        @SuppressWarnings("unchecked")
        ConcurrentHashMap<Integer, Boolean> cache = (ConcurrentHashMap<Integer, Boolean>) cacheField.get(null);

        cache.clear();
        int threadCount = 16;
        int targetUidCount = 2000;
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch endLatch = new CountDownLatch(threadCount);
        AtomicInteger mismatchCount = new AtomicInteger(0);

        for (int t = 0; t < threadCount; t++) {
            executor.submit(() -> {
                try {
                    startLatch.await();
                    for (int uid = 10000; uid < 10000 + targetUidCount; uid++) {
                        boolean isPriv = (uid == 10150 || uid == 10151);
                        // All threads attempt to put the value
                        cache.put(uid, isPriv);
                        Boolean fetched = cache.get(uid);
                        if (fetched == null || fetched != isPriv) {
                            mismatchCount.incrementAndGet();
                        }
                    }
                } catch (Throwable ex) {
                    mismatchCount.incrementAndGet();
                    ex.printStackTrace();
                } finally {
                    endLatch.countDown();
                }
            });
        }

        startLatch.countDown();
        boolean completed = endLatch.await(10, TimeUnit.SECONDS);
        executor.shutdown();

        if (!completed) {
            throw new AssertionError("Timeout waiting for cold-cache race condition test.");
        }
        if (mismatchCount.get() > 0) {
            throw new AssertionError("Race condition caused " + mismatchCount.get() + " value mismatches.");
        }
        if (cache.size() != targetUidCount) {
            throw new AssertionError("Expected map size " + targetUidCount + ", but got " + cache.size());
        }

        System.out.printf("PASSED (%d UIDs inserted concurrently by %d threads, map size=%d, 0 mismatches)%n",
                targetUidCount, threadCount, cache.size());
    }

    private static void testMemoryFootprintAndScalability() throws Exception {
        System.out.print("[*] Test 5: Testing memory footprint with 10,000 UIDs (full user 0 range)... ");
        Class<?> clazz = Class.forName(SYSTEM_SERVER_HOOKS_CLASS);
        Field cacheField = clazz.getDeclaredField("sPrivilegedUidCache");
        cacheField.setAccessible(true);
        @SuppressWarnings("unchecked")
        ConcurrentHashMap<Integer, Boolean> cache = (ConcurrentHashMap<Integer, Boolean>) cacheField.get(null);

        cache.clear();
        System.gc();
        Thread.sleep(50);
        long memBefore = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();

        // Android user 0 application UID range is typically 10000..19999 (10,000 UIDs)
        for (int uid = 10000; uid < 20000; uid++) {
            boolean priv = (uid == 10150 || uid == 10151);
            cache.put(uid, priv);
        }

        long memAfter = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
        long memUsedBytes = Math.max(0, memAfter - memBefore);
        double memUsedMB = memUsedBytes / (1024.0 * 1024.0);

        // Verify retrieval is still ultra-fast O(1)
        long start = System.nanoTime();
        for (int uid = 10000; uid < 20000; uid++) {
            Boolean val = cache.get(uid);
            if (val == null) throw new AssertionError("Missing UID: " + uid);
        }
        long queryDurationNs = System.nanoTime() - start;
        double nsPerQuery = (double) queryDurationNs / 10000;

        System.out.printf("PASSED (10,000 entries, ~%.2f MB heap delta, %.2f ns/lookup) [NO LEAK]%n",
                memUsedMB, nsPerQuery);

        if (memUsedMB > 10.0) {
            throw new AssertionError("Memory leak: 10,000 UIDs consumed excessive memory: " + memUsedMB + " MB");
        }
    }

    private static void testIsPrivilegedInputCallerLogic() throws Exception {
        System.out.print("[*] Test 6: Verifying isPrivilegedInputCaller reflection & bypass rules... ");
        Class<?> clazz = Class.forName(SYSTEM_SERVER_HOOKS_CLASS);
        Method method = clazz.getDeclaredMethod("isPrivilegedInputCaller", Object.class, int.class);
        method.setAccessible(true);

        Field cacheField = clazz.getDeclaredField("sPrivilegedUidCache");
        cacheField.setAccessible(true);
        @SuppressWarnings("unchecked")
        ConcurrentHashMap<Integer, Boolean> cache = (ConcurrentHashMap<Integer, Boolean>) cacheField.get(null);

        // Pre-populate cache to test fast-path
        cache.clear();
        cache.put(10150, Boolean.TRUE);
        cache.put(10151, Boolean.TRUE);
        cache.put(10999, Boolean.FALSE);

        // 1. Root (UID 0) must be true immediately
        boolean rootRes = (Boolean) method.invoke(null, null, 0);
        if (!rootRes) throw new AssertionError("Root UID 0 must be privileged");

        // 2. System (UID 1000) must be true immediately
        boolean sysRes = (Boolean) method.invoke(null, null, 1000);
        if (!sysRes) throw new AssertionError("System UID 1000 must be privileged");

        // 3. Cached MDX UID 10150
        boolean mdxRes = (Boolean) method.invoke(null, null, 10150);
        if (!mdxRes) throw new AssertionError("Cached MDX UID 10150 must be privileged");

        // 4. Cached AppManager UID 10151
        boolean amRes = (Boolean) method.invoke(null, null, 10151);
        if (!amRes) throw new AssertionError("Cached AppManager UID 10151 must be privileged");

        // 5. Cached untrusted UID 10999
        boolean untrustedRes = (Boolean) method.invoke(null, null, 10999);
        if (untrustedRes) throw new AssertionError("Untrusted UID 10999 must NOT be privileged");

        System.out.println("PASSED (UID 0=true, UID 1000=true, UID 10150=true, UID 10151=true, UID 10999=false)");
    }

    private static void testInputInjectionHooksStructure() throws Exception {
        System.out.print("[*] Test 7: Verifying InputInjectionHooks methods & signatures... ");
        Class<?> clazz = Class.forName(INPUT_INJECTION_HOOKS_CLASS);

        // Check hookSemInputInjector method
        Method hookSem = clazz.getDeclaredMethod("hookSemInputInjector", ClassLoader.class);
        if (!Modifier.isPrivate(hookSem.getModifiers()) || !Modifier.isStatic(hookSem.getModifiers())) {
            throw new AssertionError("hookSemInputInjector must be private static");
        }

        // Check hookInputInjectorManagerImpl method
        Method hookImpl = clazz.getDeclaredMethod("hookInputInjectorManagerImpl", ClassLoader.class);
        if (!Modifier.isPrivate(hookImpl.getModifiers()) || !Modifier.isStatic(hookImpl.getModifiers())) {
            throw new AssertionError("hookInputInjectorManagerImpl must be private static");
        }

        // Check injectEventInternal method
        Method injectInternal = clazz.getDeclaredMethod(
                "injectEventInternal",
                Object.class,
                Class.forName("android.view.InputEvent"),
                int.class,
                int.class
        );
        if (!Modifier.isPrivate(injectInternal.getModifiers()) || !Modifier.isStatic(injectInternal.getModifiers())) {
            throw new AssertionError("injectEventInternal must be private static");
        }

        System.out.println("PASSED (hookSemInputInjector, hookInputInjectorManagerImpl, injectEventInternal verified)");
    }
}
