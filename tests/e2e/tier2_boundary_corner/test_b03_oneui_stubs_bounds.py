"""
Boundary & Corner Cases: Feature 3 (One UI Version & Framework Stubs)
Tests unknown Samsung class handling, NoClassDefFoundError reproduction on AOSP,
stub removal restoration, and version bounds.
"""

import unittest
from tests.mock_env.art_classloader import ARTClassLoader, OneUIStubs
from tests.mock_env.android_runtime import NoClassDefFoundError, ClassNotFoundException


class TestOneUIStubsBounds(unittest.TestCase):
    def setUp(self):
        self.class_loader = ARTClassLoader(is_aosp_base=True)

    def test_unstubbed_sem_floating_feature_throws_noclassdef(self):
        with self.assertRaises(NoClassDefFoundError) as ctx:
            self.class_loader.load_class("com.samsung.android.feature.SemFloatingFeature")
        self.assertIn("NoClassDefFoundError", str(ctx.exception))

    def test_unstubbed_ll0_c_throws_noclassdef(self):
        with self.assertRaises(NoClassDefFoundError) as ctx:
            self.class_loader.load_class("LL0.c")
        self.assertIn("NoClassDefFoundError", str(ctx.exception))

    def test_unknown_arbitrary_class_throws_class_not_found(self):
        with self.assertRaises(ClassNotFoundException):
            self.class_loader.load_class("com.samsung.android.nonexistent.UnknownService")

    def test_unregister_stub_restores_noclassdeffounderror(self):
        self.class_loader.register_stub("LL0.c", OneUIStubs)
        cls = self.class_loader.load_class("LL0.c")
        self.assertIs(cls, OneUIStubs)

        # Unregister and verify original error returns
        self.class_loader.unregister_stub("LL0.c")
        with self.assertRaises(NoClassDefFoundError):
            self.class_loader.load_class("LL0.c")

    def test_sem_int_boundary_meets_oneui_requirement(self):
        # Link to Windows requires One UI 3.0+ (SEM_INT >= 3000)
        self.assertGreaterEqual(OneUIStubs.SEM_INT, 3000)
        self.assertLessEqual(OneUIStubs.SEM_INT, 9999)


if __name__ == "__main__":
    unittest.main()
