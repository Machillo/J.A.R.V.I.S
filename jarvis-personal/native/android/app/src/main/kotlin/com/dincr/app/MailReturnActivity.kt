package com.dincr.app

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/**
 * Receives a finished mail connection from the browser (`<scheme>://gmail/callback?...`) and hands
 * it to the running MainActivity, like [AuthCallbackActivity]. The URL is only forwarded: the
 * app parses it strictly, redeems it once, and only with the session that started the flow.
 */
class MailReturnActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        intent?.data?.let { uri ->
            startActivity(
                Intent(this, MainActivity::class.java).setAction(ACTION_MAIL_RETURN).setData(uri)
                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            )
        }
        finish()
    }

    companion object {
        const val ACTION_MAIL_RETURN = "com.dincr.app.action.MAIL_RETURN"
    }
}
