package com.dincr.app;

import com.google.firebase.FirebaseApp;
import com.google.firebase.appdistribution.FirebaseAppDistribution;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    private boolean updateCheckStarted = false;

    @Override
    public void onResume() {
        super.onResume();
        // Tester builds only: release builds link the no-op App Distribution API.
        if (!updateCheckStarted && !FirebaseApp.getApps(this).isEmpty()) {
            updateCheckStarted = true;
            FirebaseAppDistribution.getInstance()
                .updateIfNewReleaseAvailable();
        }
    }
}
