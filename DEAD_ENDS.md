# Dead Ends: Phone Link Module

| Iteration | Approach Tried | Why It Failed | Files Touched |
|---|---|---|---|
| M1 Iteration 1 | Bundling pre-compiled reference `classes.dex` from `module_inspect` into `PhoneLinkXposed.apk` via `build_lsposed.py` | `assets/xposed_init` declares `me.phonelink.xposed.XposedInit`, but `classes.dex` contains `me.ayra.samsung.mdx.XposedInit`. Raw Java sources in `app/src/main/java/` were not compiled into bytecode. Causes fatal `ClassNotFoundException` on device. Forensic Auditor reported INTEGRITY VIOLATION. | `lsposed_module/build_lsposed.py`, `PhoneLinkXposed.apk` |
