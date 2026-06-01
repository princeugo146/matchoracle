# MatchOracle Android App

React Native / Expo wrapper for the MatchOracle web app, ready for Google Play Store distribution.

## Features

- 🚀 Animated splash screen with MatchOracle branding
- 📱 Full-screen WebView loading the MatchOracle web app
- ⬅️ Android back button navigation (goes back in WebView history)
- 🔔 Push notification support (Firebase Cloud Messaging)
- 🔗 Deep linking support (`matchoracle://` and HTTPS)
- 📴 Offline error screen with retry
- 🎨 Dark theme matching the web app (`#030508` background)
- 🔒 Network security config (HTTPS only in production)

## Prerequisites

- Node.js 18+
- Expo CLI: `npm install -g expo-cli`
- EAS CLI: `npm install -g eas-cli`
- Android Studio (for local builds)
- Expo account (for EAS builds)

## Setup

```bash
cd mofix/mofix/mobile
npm install
```

## Development

```bash
# Start Expo dev server
npm start

# Run on Android emulator/device
npm run android
```

## Building the APK

### Option 1: EAS Build (Recommended — cloud build, no Android Studio needed)

```bash
# Login to Expo
eas login

# Configure project (first time only)
eas build:configure

# Build preview APK (for testing)
npm run build:apk
# or: eas build --platform android --profile preview

# Build production AAB (for Google Play)
npm run build:aab
# or: eas build --platform android --profile production
```

The APK/AAB will be available for download from the Expo dashboard.

### Option 2: Local Build

```bash
# Generate native Android project
npx expo prebuild --platform android

# Build debug APK
cd android && ./gradlew assembleDebug

# Build release APK (requires signing config)
cd android && ./gradlew assembleRelease
```

Output: `android/app/build/outputs/apk/release/app-release.apk`

## Release Signing

For production builds, create a keystore and add to `~/.gradle/gradle.properties`:

```properties
MYAPP_UPLOAD_STORE_FILE=matchoracle-upload-key.keystore
MYAPP_UPLOAD_KEY_ALIAS=matchoracle-key-alias
MYAPP_UPLOAD_STORE_PASSWORD=your_store_password
MYAPP_UPLOAD_KEY_PASSWORD=your_key_password
```

Generate keystore:
```bash
keytool -genkeypair -v -storetype PKCS12 \
  -keystore matchoracle-upload-key.keystore \
  -alias matchoracle-key-alias \
  -keyalg RSA -keysize 2048 -validity 10000
```

## Google Play Submission

```bash
# Submit to Google Play (requires google-play-key.json)
eas submit --platform android
```

## Configuration

Edit `app.json` to update:
- `extra.webAppUrl` — the URL of your MatchOracle deployment
- `version` / `android.versionCode` — app version
- `android.package` — bundle ID (`com.matchoracle.app`)

## Project Structure

```
mobile/
├── App.tsx                    # Root component, navigation setup
├── app.json                   # Expo configuration
├── eas.json                   # EAS Build profiles
├── package.json               # Dependencies
├── screens/
│   ├── SplashScreen.tsx       # Animated splash screen
│   └── WebViewScreen.tsx      # WebView wrapper with back handling
├── assets/                    # App icons and splash images
│   ├── icon.png               # 1024x1024 app icon
│   ├── adaptive-icon.png      # Android adaptive icon foreground
│   ├── splash.png             # Splash screen image
│   └── notification-icon.png  # Push notification icon
└── android/
    ├── build.gradle           # Root build config
    └── app/
        ├── build.gradle       # App build config
        ├── proguard-rules.pro # ProGuard rules
        └── src/main/
            ├── AndroidManifest.xml
            └── res/           # Resources (strings, colors, styles)
```

## Branding

- **Primary colour:** `#00d4ff` (cyan)
- **Background:** `#030508` (near-black)
- **Accent:** `#7c3aed` (purple)
- **Font:** Orbitron (logo), Inter (body)
- **App name:** MatchOracle
- **Package:** `com.matchoracle.app`
