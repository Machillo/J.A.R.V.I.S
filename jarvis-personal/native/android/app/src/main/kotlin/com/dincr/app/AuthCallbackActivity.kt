package com.dincr.app

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/**
 * Receives the OAuth redirect from the Custom Tab and hands it to the existing MainActivity
 * (the AppAuth pattern). The pending PKCE verifier lives in MainActivity's ViewModel, so the
 * redirect must reach that instance: CLEAR_TOP closes the Custom Tab above it and SINGLE_TOP
 * delivers the URL to onNewIntent. This keeps MainActivity out of `singleTask`. The URL is only
 * forwarded; AppModel accepts it only while its own sign-in is pending and only on the exact
 * redirect.
 */
class AuthCallbackActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        intent?.data?.let { uri ->
            startActivity(
                Intent(this, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData(uri)
                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            )
        }
        finish()
    }
}
