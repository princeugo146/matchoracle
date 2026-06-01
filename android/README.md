# MatchOracle Android App

A native Android WebView wrapper for the MatchOracle web app.

## Requirements

- Android Studio Hedgehog (2023.1.1) or later
- JDK 17+
- Android SDK with API 26–34

## Build Instructions

### Debug APK

```bash
cd android
./gradlew assembleDebug
# Output: app/build/outputs/apk/debug/app-debug.apk
```

### Release APK (Play Store)

1. Generate a signing keystore:
   ```bash
   keytool -genkey -v -keystore matchoracle.jks \
     -alias matchoracle -keyalg RSA -keysize 2048 -validity 10000
   ```

2. Set environment variables (or edit `app/build.gradle`):
   ```bash
   export KEYSTORE_PATH=/path/to/matchoracle.jks
   export KEYSTORE_PASSWORD=your_store_password
   export KEY_ALIAS=matchoracle
   export KEY_PASSWORD=your_key_password
   ```

3. Uncomment the `signingConfigs` block in `app/build.gradle`

4. Build:
   ```bash
   ./gradlew assembleRelease
   # Output: app/build/outputs/apk/release/app-release.apk
   ```

### Android App Bundle (recommended for Play Store)

```bash
./gradlew bundleRelease
# Output: app/build/outputs/bundle/release/app-release.aab
```

## Configuration

The app loads: `https://matchoracle.up.railway.app`

To change the URL, edit `BASE_URL` in:
`app/src/main/java/com/matchoracle/app/MainActivity.java`

## Features

- Full WebView with JavaScript enabled
- Pull-to-refresh
- Progress bar while loading
- Back button navigation through WebView history
- Deep link support (`matchoracle://` and `https://matchoracle.up.railway.app`)
- Splash screen (1.5 seconds)
- External links open in system browser
- Dark theme matching the web app

## App Details

| Property | Value |
|----------|-------|
| Package | `com.matchoracle.app` |
| Min SDK | 26 (Android 8.0) |
| Target SDK | 34 (Android 14) |
| Version | 1.0.0 (code: 1) |
