package me.phonelink.xposed.hooks;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaCrypto;
import android.media.MediaFormat;
import android.os.Bundle;
import android.view.Surface;

import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import me.phonelink.xposed.utils.XposedLog;

/**
 * VideoCodecHooks: Video Codec Adaptation & Low-Latency Parameter Sanitization.
 * Redirects Samsung proprietary video encoders (c2.sec.*, OMX.Exynos.*, OMX.SEC.*) to
 * Qualcomm Snapdragon 855 hardware encoders (c2.qti.avc.encoder / c2.qti.hevc.encoder)
 * and sanitizes surface formats and real-time streaming flags on AOSP Android 16.
 */
public final class VideoCodecHooks {
    private static final String TAG = "PhoneLink-VideoCodec";

    // Standard Qualcomm Snapdragon 855 Codec2 Encoders
    public static final String QTI_AVC_ENCODER = "c2.qti.avc.encoder";
    public static final String QTI_HEVC_ENCODER = "c2.qti.hevc.encoder";

    public static void init(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!"com.microsoft.appmanager".equals(lpparam.packageName) &&
            !"com.samsung.android.mdx".equals(lpparam.packageName)) {
            return;
        }
        XposedLog.i(TAG, "Initializing VideoCodecHooks for " + lpparam.packageName);
        hookCodecNameRedirection(lpparam.classLoader);
        hookMediaCodecConfigure(lpparam.classLoader);
        hookMediaCodecLifecycle(lpparam.classLoader);
        hookMediaCodecSetParameters(lpparam.classLoader);
    }

    /**
     * 1. Intercept MediaCodec.createByCodecName to redirect Samsung proprietary names
     *    (c2.sec.*, OMX.Exynos.*, OMX.SEC.*) to Qualcomm hardware encoders.
     */
    private static void hookCodecNameRedirection(ClassLoader classLoader) {
        try {
            XposedHelpers.findAndHookMethod(
                MediaCodec.class,
                "createByCodecName",
                String.class,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        String name = (String) param.args[0];
                        if (name == null) return;

                        String lower = name.toLowerCase();
                        if (lower.contains("sec.") || lower.contains("exynos.") || lower.contains("samsung")) {
                            if (lower.contains("hevc") || lower.contains("265")) {
                                XposedLog.i(TAG, "Redirecting Samsung HEVC encoder [" + name + "] -> [" + QTI_HEVC_ENCODER + "]");
                                param.args[0] = QTI_HEVC_ENCODER;
                            } else {
                                XposedLog.i(TAG, "Redirecting Samsung AVC encoder [" + name + "] -> [" + QTI_AVC_ENCODER + "]");
                                param.args[0] = QTI_AVC_ENCODER;
                            }
                        }
                    }
                }
            );
            XposedLog.i(TAG, "Hooked MediaCodec.createByCodecName for Qualcomm redirection");
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to hook MediaCodec.createByCodecName", t);
        }

        try {
            XposedHelpers.findAndHookMethod(
                MediaCodec.class,
                "createEncoderByType",
                String.class,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        String type = (String) param.args[0];
                        if (type != null) {
                            String lower = type.toLowerCase();
                            if (lower.contains("sec") || lower.contains("samsung")) {
                                XposedLog.i(TAG, "Redirecting proprietary encoder type [" + type + "] -> [video/avc]");
                                param.args[0] = "video/avc";
                            }
                        }
                    }
                }
            );
            XposedLog.i(TAG, "Hooked MediaCodec.createEncoderByType for type redirection");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook MediaCodec.createEncoderByType: " + t.getMessage());
        }
    }

    /**
     * 2. Intercept MediaCodec.configure to sanitize Samsung vendor parameters,
     *    enforce COLOR_FormatSurface, and map low-latency real-time flags for AOSP/Qualcomm.
     */
    private static void hookMediaCodecConfigure(ClassLoader classLoader) {
        try {
            XposedHelpers.findAndHookMethod(
                MediaCodec.class,
                "configure",
                MediaFormat.class,
                Surface.class,
                MediaCrypto.class,
                int.class,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        MediaFormat format = (MediaFormat) param.args[0];
                        int flags = (Integer) param.args[3];

                        if (format == null || (flags & MediaCodec.CONFIGURE_FLAG_ENCODE) == 0) {
                            return;
                        }

                        // A. Enforce standard COLOR_FormatSurface (0x7F000789)
                        if (format.containsKey(MediaFormat.KEY_COLOR_FORMAT)) {
                            int colorFormat = format.getInteger(MediaFormat.KEY_COLOR_FORMAT);
                            if (colorFormat != MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface) {
                                XposedLog.w(TAG, "Sanitizing non-standard color format: " + colorFormat + " -> COLOR_FormatSurface");
                                format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
                            }
                        } else {
                            format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
                        }

                        // B. Standard AOSP low-latency and priority keys
                        format.setInteger(MediaFormat.KEY_LOW_LATENCY, 1);
                        format.setInteger(MediaFormat.KEY_PRIORITY, 0); // Realtime priority

                        // C. Ensure valid bitrate mode (VBR = 2, CBR = 1)
                        if (!format.containsKey(MediaFormat.KEY_BITRATE_MODE)) {
                            format.setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR);
                        }

                        // D. Ensure I-Frame interval (1 second default for screen streaming)
                        if (!format.containsKey(MediaFormat.KEY_I_FRAME_INTERVAL)) {
                            format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
                        }

                        XposedLog.d(TAG, "MediaCodec.configure sanitized for Qualcomm encoder: " + format);
                    }
                }
            );
            XposedLog.i(TAG, "Hooked MediaCodec.configure for format sanitization");
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to hook MediaCodec.configure", t);
        }
    }

    /**
     * 3. Intercept MediaCodec.start to request an immediate IDR keyframe
     *    ensuring the remote client receives decodable video immediately.
     */
    private static void hookMediaCodecLifecycle(ClassLoader classLoader) {
        try {
            XposedHelpers.findAndHookMethod(
                MediaCodec.class,
                "start",
                new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        try {
                            MediaCodec codec = (MediaCodec) param.thisObject;
                            Bundle syncParams = new Bundle();
                            syncParams.putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 1);
                            codec.setParameters(syncParams);
                            XposedLog.i(TAG, "Dispatched initial IDR sync frame after MediaCodec.start()");
                        } catch (Throwable t) {
                            XposedLog.d(TAG, "Initial sync frame dispatch note: " + t.getMessage());
                        }
                    }
                }
            );
            XposedLog.i(TAG, "Hooked MediaCodec.start for immediate IDR sync frame");
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to hook MediaCodec.start", t);
        }
    }

    /**
     * 4. Intercept MediaCodec.setParameters to map Samsung sync-frame requests
     *    to standard AOSP PARAMETER_KEY_REQUEST_SYNC_FRAME.
     */
    private static void hookMediaCodecSetParameters(ClassLoader classLoader) {
        try {
            XposedHelpers.findAndHookMethod(
                MediaCodec.class,
                "setParameters",
                Bundle.class,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        Bundle params = (Bundle) param.args[0];
                        if (params == null) return;

                        if (params.containsKey("vendor.sec-ext-enc-request-sync")) {
                            params.putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 1);
                            XposedLog.d(TAG, "Mapped vendor.sec-ext-enc-request-sync -> request-sync");
                        }
                    }
                }
            );
            XposedLog.i(TAG, "Hooked MediaCodec.setParameters for sync frame mapping");
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to hook MediaCodec.setParameters", t);
        }
    }
}
