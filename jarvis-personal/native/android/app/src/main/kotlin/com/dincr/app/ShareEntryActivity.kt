package com.dincr.app

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/**
 * Text shared from another app. It only hands the text to the running MainActivity in DINCR's own
 * task, like [MailReturnActivity]. MainActivity prefills an expense: nothing is saved from here.
 */
class ShareEntryActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startActivity(
            Intent(this, MainActivity::class.java).setAction(Intent.ACTION_SEND).setType("text/plain")
                .putExtra(Intent.EXTRA_TEXT, intent?.getStringExtra(Intent.EXTRA_TEXT))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        )
        finish()
    }
}
