package com.samsung.android.os;

/**
 * Samsung SemTemperatureManager stub implementation for AOSP / Project Infinity X.
 */
public class SemTemperatureManager {

    public static class Thermistor {
        public static final int TYPE_AP = 0;
        public static final int TYPE_BATTERY = 1;
        public static final int TYPE_SKIN = 9;

        private final int mType;

        public Thermistor() {
            this.mType = TYPE_AP;
        }

        public Thermistor(int type) {
            this.mType = type;
        }

        public int getType() {
            return mType;
        }

        public int getTemperature() {
            return 300; // 30.0 degrees Celsius in tenths
        }
    }

    public static Thermistor getThermistor(int thermistorType) {
        return new Thermistor(thermistorType);
    }

    public static int getThermistorTemperature(int type) {
        return 30; // 30 degrees Celsius
    }
}
