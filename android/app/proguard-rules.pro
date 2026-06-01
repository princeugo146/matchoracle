# ─── MatchOracle ProGuard / R8 rules ─────────────────────────────────────
# Applied during release builds (minifyEnabled = true).

# Keep Capacitor bridge classes
-keep class com.getcapacitor.** { *; }
-keep class com.matchoracle.app.** { *; }

# Keep AndroidX & Material
-keep class androidx.** { *; }
-keep class com.google.android.material.** { *; }

# Keep JavaScript interface annotations (used by Capacitor WebView bridge)
-keepattributes JavascriptInterface
-keepattributes *Annotation*

# Suppress warnings for missing classes in third-party libs
-dontwarn com.getcapacitor.**
-dontwarn okhttp3.**
-dontwarn okio.**

# Keep source file names and line numbers for crash reports
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
