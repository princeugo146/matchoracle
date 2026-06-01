package com.matchoracle.app;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;

import androidx.appcompat.app.AppCompatActivity;

/**
 * Splash screen shown for 1.5 seconds before launching MainActivity.
 * The splash layout uses the MatchOracle dark theme and logo.
 */
public class SplashActivity extends AppCompatActivity {

    private static final int SPLASH_DELAY_MS = 1500;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_splash);

        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            Intent intent = new Intent(SplashActivity.this, MainActivity.class);
            // Pass through any deep-link intent data
            if (getIntent() != null && getIntent().getData() != null) {
                intent.setData(getIntent().getData());
            }
            startActivity(intent);
            finish();
        }, SPLASH_DELAY_MS);
    }
}
