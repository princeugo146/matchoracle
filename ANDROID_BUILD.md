# MatchOracle Android Build Guide

A complete guide to building, signing, and releasing the MatchOracle Android
app — a Capacitor-based native wrapper around the Django web application.

---

## Table of Contents

1. [How it works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Local setup](#local-setup)
4. [Building the APK](#building-the-apk)
5. [Signing for release](#signing-for-release)
6. [CI/CD with GitHub Actions](#cicd-with-github-actions)
7. [Google Play Store submission](#google-play-store-submission)
8. [Updating the app](#updating-the-app)
9. [Troubleshooting](#troubleshooting)

---

## How it works

Capacitor wraps the MatchOracle web app in a native Android WebView. When the
app launches it loads `https://matchoracle-production.up.railway.app` directly
— no static assets are bundled. All authentication, predictions, and data live
on the existing Django backend; the Android shell just provides the native
container and Play Store distribution.

```
Android device
└── MatchOracle APK
    └── Capacitor WebView
        └── https://matchoracle-production.up.railway.app  (Django backend)
```

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | 18 or 20 LTS | https://nodejs.org |
| npm | 9+ | bundled with Node |
| Java JDK | 17 | https://adoptium.net |
| Android Studio | Hedgehog+ | https://developer.android.com/studio |
| Android SDK | API 34 | via Android Studio SDK Manager |
| Gradle | 8.x | bundled in `android/gradlew` |

> **macOS shortcut:** `brew install node openjdk@17 && brew install --cask android-studio`

Set `JAVA_HOME` and `ANDROID_HOME` in your shell profile:

```bash
# ~/.zshrc or ~/.bashrc
export JAVA_HOME=$(/usr/libexec/java_home -v 17)          # macOS
export ANDROID_HOME=$HOME/Library/Android/sdk              # macOS
export PATH=$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools
```

---

## Local setup

```bash
# 1. Clone the repository
git clone https://github.com/your-org/matchoracle.git
cd matchoracle

# 2. Install Capacitor and plugin dependencies
npm install

# 3. Sync Capacitor configuration into the Android project
#    (run this every time capacitor.config.json changes)
npx cap sync android

# 4. Open in Android Studio (optional — for visual editing)
npx cap open android
```

---

## Building the APK

### Debug build (for testing — no signing required)

```bash
cd android
./gradlew assembleDebug
```

Output: `android/app/build/outputs/apk/debug/app-debug.apk`

Install directly on a connected device:

```bash
adb install android/app/build/outputs/apk/debug/app-debug.apk
```

### Release build (for distribution)

A release build requires a signed keystore. See [Signing for release](#signing-for-release) first.

```bash
cd android
./gradlew assembleRelease
```

Output: `android/app/build/outputs/apk/release/app-release.apk`

---

## Signing for release

Android requires every APK distributed outside of debug mode to be signed with
a keystore. **Generate the keystore once and keep it safe — losing it means you
can never update your Play Store listing.**

### 1. Generate a keystore

```bash
keytool -genkey -v \
  -keystore matchoracle.keystore \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -alias matchoracle
```

You will be prompted for:
- Keystore password (remember this)
- Your name, organisation, city, country
- Key password (can be the same as keystore password)

Store `matchoracle.keystore` somewhere **outside** the repository (e.g. a
password manager or secure cloud storage).

### 2. Create signing-config.properties

```bash
cp android/app/signing-config.properties.example android/app/signing-config.properties
```

Edit `android/app/signing-config.properties`:

```properties
storeFile=/absolute/path/to/matchoracle.keystore
storePassword=your_keystore_password
keyAlias=matchoracle
keyPassword=your_key_password
```

> `signing-config.properties` is listed in `.gitignore` and must **never** be
> committed to version control.

### 3. Build the signed release APK

```bash
cd android
./gradlew assembleRelease
```

Verify the signature:

```bash
apksigner verify --verbose android/app/build/outputs/apk/release/app-release.apk
```

---

## CI/CD with GitHub Actions

The workflow at `.github/workflows/build-android.yml` automates APK builds.

### Required GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `KEYSTORE_BASE64` | Base64-encoded keystore: `base64 -i matchoracle.keystore` |
| `KEYSTORE_PASSWORD` | Keystore password |
| `KEY_ALIAS` | `matchoracle` |
| `KEY_PASSWORD` | Key password |

### Triggering a build

**Manual (any branch):**
1. Go to **Actions → Build Android APK**
2. Click **Run workflow**
3. Choose `release` or `debug`
4. Download the APK from the workflow artifacts

**Automatic (on version tag):**

```bash
git tag v2.0.1
git push origin v2.0.1
```

This triggers a release build and creates a GitHub Release with the APK
attached automatically.

---

## Google Play Store submission

### First-time setup

1. Create a [Google Play Console](https://play.google.com/console) account ($25 one-time fee)
2. Create a new app → **MatchOracle**
3. Fill in store listing details:
   - **Title:** MatchOracle
   - **Short description:** AI-powered football predictions & live scores
   - **Full description:** (use the README content)
   - **Category:** Sports
   - **Content rating:** Complete the questionnaire (Everyone)

### Upload the APK / AAB

Google Play prefers **Android App Bundles (.aab)** over APKs for smaller
download sizes. Build an AAB:

```bash
cd android
./gradlew bundleRelease
```

Output: `android/app/build/outputs/bundle/release/app-release.aab`

Upload via Play Console → **Production → Create new release → Upload**.

### Version management

Before each Play Store upload, increment `versionCode` in
`android/app/build.gradle` (must always increase):

```groovy
defaultConfig {
    versionCode 2          // ← increment this
    versionName "2.0.1"    // ← update this to match
}
```

### Required assets for Play Store

| Asset | Size | Notes |
|-------|------|-------|
| App icon | 512×512 PNG | No alpha, no rounded corners |
| Feature graphic | 1024×500 PNG | Shown at top of store listing |
| Screenshots | Min 2, max 8 | Phone: 16:9 or 9:16 |
| Privacy policy URL | — | Required for apps with login |

---

## Updating the app

Because the app loads the Django backend remotely, **most updates require no
APK rebuild** — just deploy to Railway and users see the changes instantly.

An APK rebuild is only needed when:

- Changing `capacitor.config.json` (server URL, plugins, etc.)
- Adding or updating Capacitor plugins
- Changing Android permissions in `AndroidManifest.xml`
- Updating app icons or splash screen
- Bumping `versionCode` / `versionName` for Play Store

### Update workflow

```bash
# 1. Make your changes
# 2. Sync Capacitor
npx cap sync android

# 3. Bump versionCode in android/app/build.gradle

# 4. Build and sign
cd android && ./gradlew assembleRelease

# 5. Upload to Play Console
```

---

## Troubleshooting

### `JAVA_HOME is not set`

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17)   # macOS
# or
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64  # Linux
```

### `SDK location not found`

Create `android/local.properties`:

```properties
sdk.dir=/Users/yourname/Library/Android/sdk   # macOS
# or
sdk.dir=/home/yourname/Android/Sdk             # Linux
```

### `Gradle build failed: Could not resolve com.getcapacitor:core`

Run `npm install` from the project root first, then `npx cap sync android`.
Capacitor's Android AAR is resolved from `node_modules`, not Maven Central.

### `App crashes immediately on launch`

Check that the server URL in `capacitor.config.json` is reachable from the
device. The device must have internet access and the Railway deployment must be
running.

### `WebView shows blank screen`

1. Enable WebView debugging: set `webContentsDebuggingEnabled: true` in
   `capacitor.config.json` temporarily
2. Open `chrome://inspect` on a desktop Chrome browser
3. Find the device and inspect the WebView to see console errors

### `Signing failed: keystore not found`

Ensure `storeFile` in `signing-config.properties` is an **absolute** path, not
relative. Example: `/Users/alice/keys/matchoracle.keystore`

### `versionCode must be greater than previous`

Increment `versionCode` in `android/app/build.gradle` before uploading to Play
Store. The value must always increase monotonically.

---

## File reference

```
matchoracle/
├── capacitor.config.json          # Capacitor configuration (server URL, plugins)
├── package.json                   # Node dependencies (Capacitor CLI & plugins)
├── ANDROID_BUILD.md               # This file
├── .github/workflows/
│   └── build-android.yml          # GitHub Actions CI/CD workflow
└── android/                       # Android Studio project
    ├── build.gradle               # Top-level Gradle config
    ├── settings.gradle            # Module declarations
    ├── gradle.properties          # JVM & build flags
    └── app/
        ├── build.gradle           # App-level build config (versionCode, signing)
        ├── proguard-rules.pro     # R8 / ProGuard rules for release builds
        ├── signing-config.properties.example   # Template (copy & fill in)
        └── src/main/
            ├── AndroidManifest.xml             # Permissions, activities, deep links
            ├── java/com/matchoracle/app/
            │   └── MainActivity.java           # Capacitor bridge entry point
            └── res/
                ├── drawable/splash.xml         # Splash screen drawable
                ├── mipmap-*/ic_launcher.png    # App icons (all densities)
                ├── values/colors.xml           # Brand colours
                ├── values/strings.xml          # App name & string resources
                ├── values/styles.xml           # App theme
                ├── xml/file_paths.xml          # FileProvider paths
                └── xml/network_security_config.xml  # HTTPS-only policy
```
