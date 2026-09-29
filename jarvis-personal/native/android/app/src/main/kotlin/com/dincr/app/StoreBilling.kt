package com.dincr.app

import android.app.Activity
import android.content.Context
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.QueryPurchasesParams
import com.android.billingclient.api.queryProductDetails
import com.android.billingclient.api.queryPurchasesAsync
import com.dincr.data.ApiError
import com.dincr.data.DincrApi
import kotlin.coroutines.resume
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine

/**
 * Google Play subscriptions, same contract as the Capacitor app (`lib/storeBilling`): the backend
 * is the only authority. Before buying, the backend issues a customer token that travels as the
 * purchase's obfuscated account id; after buying, the purchase token is sent to
 * `/product-ops/billing/store/google/purchases`, which verifies it with Google and acknowledges it
 * (the app never acknowledges). Restoring re-sends the current purchases. Only a build with the
 * DINCR Play identity (`com.dincr.app`, installed from Play) can buy the DINCR products.
 */
class StoreBilling(context: Context, private val api: DincrApi, private val scope: CoroutineScope, private val onChange: (String) -> Unit) {
    private var onPurchase: ((Result<Unit>) -> Unit)? = null
    private val listener = PurchasesUpdatedListener { result, purchases -> handleUpdate(result, purchases) }
    private val client = BillingClient.newBuilder(context.applicationContext)
        .setListener(listener)
        .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build())
        .build()

    enum class Period(val wire: String) { MONTHLY("monthly"), ANNUAL("annual") }

    data class Offer(val plan: String, val period: Period, val productId: String, val price: String?, val details: ProductDetails?, val offerToken: String?)

    private suspend fun connected(): Boolean {
        if (client.isReady) return true
        return suspendCancellableCoroutine { cont ->
            client.startConnection(object : BillingClientStateListener {
                override fun onBillingSetupFinished(result: BillingResult) { if (cont.isActive) cont.resume(result.responseCode == BillingClient.BillingResponseCode.OK) }
                override fun onBillingServiceDisconnected() { if (cont.isActive) cont.resume(false) }
            })
        }
    }

    /** Offers for the backend's catalog; prices only ever come from the store. */
    suspend fun offers(): List<Offer> {
        val catalog = api.storeCatalog()
        val ids = catalog.plans.flatMap { plan -> listOfNotNull(plan.monthly?.productId, plan.annual?.productId).map { plan.code to it } }
        if (!connected() || ids.isEmpty()) return emptyList()
        val params = QueryProductDetailsParams.newBuilder().setProductList(ids.map { it.second }.distinct().map { id ->
            QueryProductDetailsParams.Product.newBuilder().setProductId(id).setProductType(BillingClient.ProductType.SUBS).build()
        }).build()
        val details = client.queryProductDetails(params).productDetailsList.orEmpty().associateBy { it.productId }
        return catalog.plans.flatMap { plan ->
            listOfNotNull(plan.monthly?.productId?.let { plan.code to (Period.MONTHLY to it) }, plan.annual?.productId?.let { plan.code to (Period.ANNUAL to it) })
        }.map { (code, pair) ->
            val (period, id) = pair
            val product = details[id]
            val offer = product?.subscriptionOfferDetails?.let { list -> list.firstOrNull { it.basePlanId == period.wire } ?: list.firstOrNull() }
            Offer(code, period, id, offer?.pricingPhases?.pricingPhaseList?.lastOrNull()?.formattedPrice, product, offer?.offerToken)
        }
    }

    /** Buys [offer] for the signed-in account; [done] gets the verified result. */
    suspend fun purchase(activity: Activity, offer: Offer, done: (Result<Unit>) -> Unit) {
        val entitlement = api.storeEntitlement()
        if (entitlement.isLive) { done(Result.failure(IllegalStateException(tx("Ya tenés una suscripción activa en la tienda.", "You already have an active store subscription.")))); return }
        val token = api.storeCustomerToken().token
        val details = offer.details ?: run { done(Result.failure(IllegalStateException(tx("Este plan no está disponible en Google Play.", "This plan isn’t available on Google Play.")))); return }
        val offerToken = offer.offerToken ?: run { done(Result.failure(IllegalStateException(tx("Este plan no está disponible en Google Play.", "This plan isn’t available on Google Play.")))); return }
        if (!connected()) { done(Result.failure(IllegalStateException(tx("No pudimos conectar con Google Play.", "We couldn’t reach Google Play.")))); return }
        onPurchase = done
        val params = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(listOf(BillingFlowParams.ProductDetailsParams.newBuilder().setProductDetails(details).setOfferToken(offerToken).build()))
            .setObfuscatedAccountId(token)
            .build()
        val result = client.launchBillingFlow(activity, params)
        if (result.responseCode != BillingClient.BillingResponseCode.OK) { onPurchase = null; done(Result.failure(IllegalStateException(message(result)))) }
    }

    /** Restore: sends every current purchase of this Google account to the backend again. */
    suspend fun restore(): Int {
        if (!connected()) throw IllegalStateException(tx("No pudimos conectar con Google Play.", "We couldn’t reach Google Play."))
        val purchases = client.queryPurchasesAsync(QueryPurchasesParams.newBuilder().setProductType(BillingClient.ProductType.SUBS).build()).purchasesList
        var verified = 0
        purchases.filter { it.purchaseState == Purchase.PurchaseState.PURCHASED }.forEach { purchase ->
            purchase.products.firstOrNull()?.let { api.verifyGooglePurchase(purchase.purchaseToken, it); verified += 1 }
        }
        return verified
    }

    /** Silent reconcile at start/resume: purchases the backend never confirmed are sent again. */
    fun reconcile() = scope.launch {
        runCatching {
            if (!connected()) return@runCatching
            client.queryPurchasesAsync(QueryPurchasesParams.newBuilder().setProductType(BillingClient.ProductType.SUBS).build()).purchasesList
                .filter { it.purchaseState == Purchase.PurchaseState.PURCHASED && !it.isAcknowledged }
                .forEach { purchase -> purchase.products.firstOrNull()?.let { api.verifyGooglePurchase(purchase.purchaseToken, it) } }
        }
    }

    private fun handleUpdate(result: BillingResult, purchases: List<Purchase>?) {
        val done = onPurchase
        onPurchase = null
        if (result.responseCode != BillingClient.BillingResponseCode.OK) { done?.invoke(Result.failure(IllegalStateException(message(result)))); return }
        scope.launch {
            val outcome = runCatching {
                purchases.orEmpty().filter { it.purchaseState == Purchase.PurchaseState.PURCHASED }.forEach { purchase ->
                    purchase.products.firstOrNull()?.let { api.verifyGooglePurchase(purchase.purchaseToken, it) }
                }
                if (purchases.orEmpty().any { it.purchaseState == Purchase.PurchaseState.PENDING }) onChange(tx("Tu pago está pendiente. Te avisamos cuando Google Play lo confirme.", "Your payment is pending. We’ll update your plan when Google Play confirms it."))
            }.recoverCatching { error ->
                throw IllegalStateException(when ((error as? ApiError)?.status) {
                    409 -> tx("Esta compra pertenece a otra cuenta DINCR.", "This purchase belongs to another DINCR account.")
                    422 -> tx("No pudimos verificar la compra con Google Play.", "We couldn’t verify the purchase with Google Play.")
                    503 -> tx("Las compras en la tienda están en pausa. Tu pago no se perdió: tocá Restaurar más tarde.", "Store purchases are paused. Your payment isn’t lost: tap Restore later.")
                    else -> error.message ?: tx("No pudimos confirmar la compra. Tocá Restaurar.", "We couldn’t confirm the purchase. Tap Restore.")
                })
            }
            done?.invoke(outcome)
        }
    }

    private fun message(result: BillingResult): String = when (result.responseCode) {
        BillingClient.BillingResponseCode.USER_CANCELED -> tx("Compra cancelada.", "Purchase cancelled.")
        BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED -> tx("Ya tenés esta suscripción. Tocá Restaurar.", "You already own this subscription. Tap Restore.")
        BillingClient.BillingResponseCode.BILLING_UNAVAILABLE, BillingClient.BillingResponseCode.FEATURE_NOT_SUPPORTED -> tx("Google Play no permite compras en este dispositivo o esta versión de la app.", "Google Play can’t make purchases on this device or app version.")
        else -> tx("Google Play no pudo completar la compra.", "Google Play couldn’t complete the purchase.")
    }

    fun close() { if (client.isReady) client.endConnection() }
}
