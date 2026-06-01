package com.matchoracle.app;

import com.getcapacitor.BridgeActivity;

/**
 * MainActivity for MatchOracle Android.
 *
 * Extends Capacitor's BridgeActivity which sets up the WebView bridge,
 * registers all Capacitor plugins, and loads the configured server URL
 * (https://matchoracle-production.up.railway.app) defined in
 * capacitor.config.json.
 *
 * No additional setup is required here — all configuration lives in
 * capacitor.config.json and the Gradle build files.
 */
public class MainActivity extends BridgeActivity {
    // Intentionally empty: Capacitor handles all lifecycle events.
}
