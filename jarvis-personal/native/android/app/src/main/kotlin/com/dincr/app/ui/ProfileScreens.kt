package com.dincr.app.ui

import android.app.Activity
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Logout
import androidx.compose.material.icons.rounded.AccountBalance
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Email
import androidx.compose.material.icons.rounded.Gavel
import androidx.compose.material.icons.rounded.Key
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Palette
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.SupportAgent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppLock
import com.dincr.app.AppModel
import com.dincr.app.Appearance
import com.dincr.app.StoreBilling
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
import com.dincr.data.FinancialProfile
import com.dincr.data.IdempotencyKey
import com.dincr.data.Jarvis
import com.dincr.data.OpsFlag
import com.dincr.data.PlanChangeRequest
import com.dincr.data.PlanTier
import com.dincr.data.SupportRequest
import com.dincr.data.WholeNumberInput
import com.dincr.design.BannerTone
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.ErrorState
import com.dincr.design.StatusBanner
import com.dincr.design.generated.DincrSpacing
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Display name of a backend plan code. The plan itself always comes from `/auth/me`. */
fun planName(plan: String?): String = when (plan ?: "free") {
    "free" -> "Free"
    "vip" -> "VIP"
    else -> (plan ?: "").replaceFirstChar { it.uppercase() }
}

/** G1 — profile hub. */
@Composable
fun ProfileHubScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val plan = profile?.planTier ?: PlanTier.FREE
    var confirming by remember { mutableStateOf(false) }
    ScreenColumn {
        Text(tx("Perfil", "Profile"), style = MaterialTheme.typography.headlineMedium, color = Dincr.colors.text)
        DincrCard {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.semantics(mergeDescendants = true) {}) {
                Box(Modifier.size(44.dp).background(Dincr.colors.tintContainer, CircleShape), contentAlignment = Alignment.Center) {
                    Text(profile?.firstName?.take(1) ?: "D", color = Dincr.colors.onTintContainer, style = MaterialTheme.typography.titleMedium)
                }
                Column(Modifier.weight(1f).padding(horizontal = DincrSpacing.s3)) {
                    Text(profile?.displayName ?: tx("Tu cuenta", "Your account"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                    Text(profile?.email.orEmpty(), style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
                }
                PlanBadge(planName(profile?.plan))
            }
        }
        if (Jarvis.isAvailable(profile)) DincrCard {
            // The Owner's personal space (JARVIS recovery, J0); no plan or other role sees it.
            NavRow(Icons.Rounded.Key, "JARVIS", tx("Tu espacio personal", "Your personal space")) { nav.open("jarvis") }
        }
        DincrCard {
            Column {
                NavRow(Icons.Rounded.Person, tx("Mi situación financiera", "My financial situation"), tx("Ingresos, gastos esenciales y ahorros", "Income, essential expenses and savings")) { nav.open("situation") }
                NavRow(Icons.Rounded.Star, tx("Mi plan", "My plan"), planName(profile?.plan) + (if (profile?.isCourtesy == true) tx(" · cortesía", " · courtesy") else "")) { nav.open("plans") }
                if (plan == PlanTier.VIP && model.isOn(OpsFlag.GMAIL_AUTOMATION)) {
                    NavRow(Icons.Rounded.Email, tx("Correos financieros", "Financial emails"), tx("Avisos de tu banco para revisar", "Bank notices to review")) { nav.open("mail") }
                    NavRow(Icons.Rounded.AccountBalance, tx("Cuentas detectadas", "Detected accounts"), tx("Confirmá cuáles son tuyas", "Confirm which are yours")) { nav.open("accounts") }
                }
                NavRow(Icons.Rounded.Settings, tx("Ajustes de cuenta", "Account settings"), tx("Apariencia, datos y privacidad", "Appearance, data and privacy")) { nav.open("settings") }
                NavRow(Icons.Rounded.Lock, tx("Seguridad", "Security"), tx("Bloqueo de la app", "App lock")) { nav.open("security") }
                NavRow(Icons.Rounded.SupportAgent, tx("Ayuda y soporte", "Help and support"), tx("Reportá un problema o una idea", "Report a problem or an idea")) { nav.open("support") }
            }
        }
        TextButton({ confirming = true }, Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
            Text(tx("Cerrar sesión", "Sign out"), color = Dincr.colors.negative, style = MaterialTheme.typography.titleMedium)
        }
        Caption("DINCR ${model.appVersion}")
    }
    if (confirming) ConfirmDialog(tx("¿Cerrar sesión en este dispositivo?", "Sign out on this device?"), tx("Tus datos quedan en tu cuenta.", "Your data stays in your account."),
        tx("Cerrar sesión", "Sign out"), onDismiss = { confirming = false }, onConfirm = { confirming = false; model.signOut() })
}

/**
 * G2 — the declared financial situation. Empty means unknown (null), never zero; the observed
 * income average is shown as a hint only and is never copied into the declared salary.
 */
@Composable
fun SituationScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val plan = profile?.planTier ?: PlanTier.FREE
    val situation = rememberLoad(model) { model.api.financialSituation() }
    DetailScaffold(tx("Mi situación financiera", "My financial situation"), nav::back) {
        LoadContent(situation) { s -> SituationForm(model, s.profile, s.observed?.monthlyIncomeAverage, plan) { situation.replace(it) } }
    }
}

@Composable
private fun SituationForm(model: AppModel, current: FinancialProfile?, observedIncome: java.math.BigDecimal?, plan: PlanTier, onSaved: (com.dincr.data.FinancialSituation) -> Unit) {
    val format = Dincr.money
    fun text(value: java.math.BigDecimal?) = value?.let(format::inputText).orEmpty()
    var incomeType by remember { mutableStateOf(current?.incomeType ?: "fixed") }
    var salary by remember { mutableStateOf(text(current?.fixedMonthlySalary)) }
    var hourly by remember { mutableStateOf(text(current?.hourlyRate)) }
    var days by remember { mutableStateOf(current?.workDaysPerWeek?.toString().orEmpty()) }
    var hours by remember { mutableStateOf(current?.hoursPerDay?.let(format::inputText).orEmpty()) }
    var frequency by remember { mutableStateOf(current?.payFrequency ?: "monthly") }
    var essentials by remember { mutableStateOf(text(current?.essentialMonthlyExpenses)) }
    var savings by remember { mutableStateOf(text(current?.liquidSavings)) }
    var emergency by remember { mutableStateOf(text(current?.emergencyFundTarget)) }
    var preference by remember { mutableStateOf(current?.strategyPreference ?: "balanced") }
    var minimum by remember { mutableStateOf(text(current?.discretionaryMonthlyMinimum)) }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    Section(tx("Tus ingresos", "Your income")) {
        observedIncome?.takeIf { it.signum() > 0 }?.let { Caption(tx("En los últimos 90 días registraste en promedio ${format.format(it)} por mes.", "In the last 90 days you recorded ${format.format(it)} per month on average.")) }
        ChoiceChips(listOf("fixed" to tx("Salario fijo", "Fixed salary"), "hourly" to tx("Por horas", "Hourly")), incomeType, { incomeType = it })
        if (incomeType == "fixed") MoneyField(tx("Salario mensual", "Monthly salary"), salary, { salary = it }, errors["salary"])
        else {
            MoneyField(tx("Pago por hora", "Hourly rate"), hourly, { hourly = it }, errors["hourly"])
            FormField(tx("Días por semana", "Days per week"), days, { days = it }, errors["days"], KeyboardType.Number)
            FormField(tx("Horas por día", "Hours per day"), hours, { hours = it }, errors["hours"], KeyboardType.Decimal)
        }
        ChoiceChips(listOf("weekly" to tx("Semanal", "Weekly"), "biweekly" to tx("Quincenal", "Every two weeks"), "monthly" to tx("Mensual", "Monthly")), frequency, { frequency = it }, tx("Te pagan", "You get paid"))
    }
    if (plan != PlanTier.FREE) Section(tx("Gastos y ahorros", "Expenses and savings")) {
        MoneyField(tx("Gastos esenciales del mes", "Essential monthly expenses"), essentials, { essentials = it }, errors["essentials"])
        MoneyField(tx("Ahorros disponibles", "Available savings"), savings, { savings = it }, errors["savings"])
        MoneyField(tx("Meta de fondo de emergencia", "Emergency fund target"), emergency, { emergency = it }, errors["emergency"])
    }
    if (plan == PlanTier.VIP) Section(tx("Preferencias del director", "Director preferences")) {
        ChoiceChips(listOf("debt" to tx("Salir de deudas", "Get out of debt"), "emergency" to tx("Fondo de emergencia", "Emergency fund"), "goals" to tx("Metas", "Goals"), "balanced" to tx("Equilibrado", "Balanced")), preference, { preference = it }, tx("Prioridad", "Priority"))
        MoneyField(tx("Mínimo personal por mes", "Personal minimum per month"), minimum, { minimum = it }, errors["minimum"])
    }
    error?.let { ErrorState(it) }
    DincrPrimaryButton(tx("Guardar", "Save"), loading = saving, onClick = {
        val found = mutableMapOf<String, String>()
        fun money(key: String, value: String, positive: Boolean = false) = if (value.isBlank()) null else
            (if (positive) AmountInput.parse(value, format.separators) else AmountInput.parseZeroOrMore(value, format.separators)).also { if (it == null) found[key] = tx("Monto no válido.", "Not a valid amount.") }
        val request = FinancialProfile(
            incomeType = incomeType,
            fixedMonthlySalary = if (incomeType == "fixed") money("salary", salary, positive = true) else null,
            hourlyRate = if (incomeType == "hourly") money("hourly", hourly, positive = true) else null,
            workDaysPerWeek = if (incomeType == "hourly" && days.isNotBlank()) WholeNumberInput.parse(days, 1..7).also { if (it == null) found["days"] = tx("Entre 1 y 7.", "1 to 7.") } else current?.workDaysPerWeek,
            hoursPerDay = if (incomeType == "hourly" && hours.isNotBlank()) com.dincr.data.AmountInput.parseDecimal(hours, format.separators, 2, java.math.BigDecimal(24), allowZero = false).also { if (it == null) found["hours"] = tx("Entre 0 y 24.", "0 to 24.") } else current?.hoursPerDay,
            payFrequency = frequency,
            paydayNote = current?.paydayNote,
            essentialMonthlyExpenses = if (plan != PlanTier.FREE) money("essentials", essentials) else current?.essentialMonthlyExpenses,
            liquidSavings = if (plan != PlanTier.FREE) money("savings", savings) else current?.liquidSavings,
            emergencyFundTarget = if (plan != PlanTier.FREE) money("emergency", emergency) else current?.emergencyFundTarget,
            strategyPreference = if (plan == PlanTier.VIP) preference else current?.strategyPreference,
            discretionaryMonthlyMinimum = if (plan == PlanTier.VIP) money("minimum", minimum) else current?.discretionaryMonthlyMinimum,
        )
        errors = found
        if (found.isNotEmpty()) return@DincrPrimaryButton
        saving = true; error = null
        val key = IdempotencyKey.new()
        scope.launch {
            model.load(tx("No pudimos guardar tu situación.", "We couldn’t save your situation.")) { model.api.updateFinancialSituation(request, key) }
                .onSuccess { onSaved(it); model.showNotice(tx("Situación guardada", "Situation saved")) }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    })
}

/** G4, G7, G8, G9 — appearance, legal, data export and account deletion. */
@Composable
fun SettingsScreen(model: AppModel, nav: Navigator, appearance: Appearance, onAppearance: (Appearance) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var exporting by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf(false) }
    var deletingBusy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val profile by model.profile.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { model.recordScreen("settings_opened", "settings") }
    DetailScaffold(tx("Ajustes de cuenta", "Account settings"), nav::back) {
        Section(tx("Apariencia", "Appearance")) {
            listOf(Appearance.SYSTEM to tx("Automático", "Automatic"), Appearance.LIGHT to tx("Claro", "Light"), Appearance.DARK to tx("Oscuro", "Dark")).forEach { (value, label) ->
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(appearance == value, role = Role.RadioButton) { onAppearance(value) }, verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(appearance == value, null)
                    Text(label, color = Dincr.colors.text, modifier = Modifier.padding(start = DincrSpacing.s2))
                }
            }
        }
        DincrCard {
            Column {
                NavRow(Icons.Rounded.Gavel, tx("Términos y condiciones", "Terms and conditions")) { openInBrowser(context, TERMS_URL) }
                NavRow(Icons.Rounded.Gavel, tx("Política de privacidad", "Privacy policy")) { openInBrowser(context, PRIVACY_URL) }
                NavRow(Icons.Rounded.Download, tx("Descargar mis datos", "Download my data"), if (exporting) tx("Preparando…", "Preparing…") else tx("Un archivo JSON con tu información", "A JSON file with your information")) {
                    if (exporting) return@NavRow
                    exporting = true; error = null
                    scope.launch {
                        model.load(tx("No pudimos preparar tus datos.", "We couldn’t prepare your data.")) {
                            val json = model.api.exportData().toString()
                            withContext(Dispatchers.IO) {
                                val dir = File(context.cacheDir, com.dincr.app.EXPORT_DIR).apply { mkdirs() }
                                File(dir, "dincr-datos.json").apply { writeText(json) }
                            }
                        }.onSuccess { file ->
                            val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                            val send = Intent(Intent.ACTION_SEND).setType("application/json").putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                            context.startActivity(Intent.createChooser(send, tx("Guardar o compartir tus datos", "Save or share your data")))
                        }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
                        exporting = false
                    }
                }
            }
        }
        error?.let { ErrorState(it) }
        if (profile?.canDeleteAccountInApp == true) Section(tx("Eliminar cuenta", "Delete account")) {
            Text(tx("Se borran tus datos financieros y se revoca el acceso a tu correo conectado. No se puede deshacer.", "Your financial data is deleted and access to your connected mail is revoked. This can’t be undone."),
                style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
            TextButton({ deleting = true }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Eliminar mi cuenta", "Delete my account"), color = Dincr.colors.negative) }
        }
    }
    if (deleting) ConfirmDialog(tx("¿Eliminar tu cuenta de DINCR?", "Delete your DINCR account?"),
        tx("Se borran todos tus datos y se cierra la sesión. Si tenés una suscripción en Google Play, cancelala también allí.", "All your data is deleted and you are signed out. If you have a Google Play subscription, cancel it there too."),
        tx("Eliminar definitivamente", "Delete permanently"), busy = deletingBusy, onDismiss = { deleting = false }, onConfirm = {
            deletingBusy = true
            scope.launch { model.deleteAccount()?.let { error = it }; deletingBusy = false; deleting = false }
        })
}

/** A13/G6 — app lock (turned on only after a successful unlock). */
@Composable
fun SecurityScreen(model: AppModel, nav: Navigator) {
    val activity = androidx.activity.compose.LocalActivity.current as? FragmentActivity
    val lock = model.appLock
    var enabled by remember { mutableStateOf(lock.isEnabled) }
    var message by remember { mutableStateOf<String?>(null) }
    DetailScaffold(tx("Seguridad", "Security"), nav::back) {
        Section(tx("Bloqueo de DINCR", "DINCR lock")) {
            Text(tx("Pedí tu biometría o el bloqueo del teléfono al abrir DINCR y después de 5 minutos fuera de la app.", "Ask for your biometrics or phone lock when opening DINCR and after 5 minutes away."),
                style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
            when (lock.availability) {
                AppLock.Availability.UNSUPPORTED -> StatusBanner(BannerTone.INFO, tx("No disponible", "Not available"), tx("Este teléfono no tiene un bloqueo compatible.", "This phone has no compatible lock."))
                AppLock.Availability.NOT_ENROLLED -> StatusBanner(BannerTone.INFO, tx("Configurá un bloqueo de pantalla", "Set up a screen lock"), tx("Agregá un PIN, patrón o biometría en los ajustes del teléfono.", "Add a PIN, pattern or biometrics in the phone settings."))
                AppLock.Availability.AVAILABLE -> Row(Modifier.fillMaxWidth().heightIn(min = 56.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(tx("Bloquear DINCR", "Lock DINCR"), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text, modifier = Modifier.weight(1f))
                    Switch(enabled, onCheckedChange = { on ->
                        if (!on) { lock.setEnabled(false); enabled = false; return@Switch }
                        activity?.let { a -> lock.authenticate(a) { error -> if (error == null) { lock.setEnabled(true); enabled = true } else message = error } }
                    }, modifier = Modifier.semantics { contentDescription = tx("Bloquear DINCR", "Lock DINCR") })
                }
            }
            message?.let { Caption(it) }
            if (enabled) TextButton({ lock.lockNow() }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Bloquear ahora", "Lock now"), color = Dincr.colors.tint) }
        }
        Section(tx("Inicio de sesión", "Sign-in")) {
            Text(tx("Entrás con tu cuenta de Google. DINCR no guarda tu contraseña.", "You sign in with your Google account. DINCR never stores your password."), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
        }
    }
}

/** G3 + store — current plan, change plan (with confirmation) and Google Play subscription. */
@Composable
fun PlanSettingsScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val data = rememberLoad(model) { model.api.plans() to runCatching { model.api.billingCatalog() }.getOrNull() }
    var confirmPlan by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val subscription = profile?.subscription
    DetailScaffold(tx("Mi plan", "My plan"), nav::back) {
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                Text(tx("Plan actual", "Current plan"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
                Text(subscription?.planName ?: planName(profile?.plan), style = MaterialTheme.typography.headlineSmall, color = Dincr.colors.text)
                if (profile?.isCourtesy == true) Caption(tx("Acceso de cortesía", "Courtesy access") + (subscription?.expiresAt?.let { tx(" hasta ", " until ") + dateLabel(it) } ?: ""))
                subscription?.pendingPlan?.let { pending ->
                    StatusBanner(BannerTone.INFO, tx("Cambio programado", "Scheduled change"),
                        tx("Pasás a ${planName(pending)} el ", "You move to ${planName(pending)} on ") + dateLabel(subscription.pendingEffectiveAt))
                }
            }
        }
        LoadContent(data) { (options, catalog) ->
            val promotion = catalog?.promotion?.active == true || options.any { it.promotion?.active == true }
            options.forEach { option ->
                PlanCard(option, catalog, promotion, busy && confirmPlan == option.code, enabled = !busy, current = option.code == profile?.plan,
                    actionLabel = tx("Cambiar a ${option.name ?: option.code}", "Switch to ${option.name ?: option.code}")) { confirmPlan = option.code }
            }
        }
        error?.let { ErrorState(it) }
        if (profile?.role == "user") StoreSubscriptionPanel(model)
    }
    confirmPlan?.let { code ->
        val downgrade = PlanTier.from(code).rank < (profile?.planTier ?: PlanTier.FREE).rank
        ConfirmDialog(tx("¿Cambiar a ${planName(code)}?", "Switch to ${planName(code)}?"),
            if (downgrade) tx("El cambio se aplica al final de tu período actual. Hasta entonces conservás tu plan.", "The change applies at the end of your current period. Until then you keep your plan.")
            else tx("Tendrás las funciones de ${planName(code)} de inmediato.", "You’ll get ${planName(code)} features right away."),
            tx("Cambiar", "Switch"), destructive = false, busy = busy, onDismiss = { confirmPlan = null }, onConfirm = {
                busy = true; error = null
                scope.launch {
                    model.load(tx("No pudimos cambiar tu plan.", "We couldn’t change your plan.")) { model.api.choosePlan(PlanChangeRequest(code, consentVersion = PLAN_CONSENT_VERSION)) }
                        .onSuccess { result ->
                            (result.profile ?: model.api.me()).let(model::apply)
                            model.showNotice(when (result.status) {
                                "downgrade_scheduled" -> tx("Cambio programado para el final de tu período.", "Change scheduled for the end of your period.")
                                "plan_kept" -> tx("Conservás tu plan actual.", "You keep your current plan.")
                                else -> tx("Plan actualizado", "Plan updated")
                            })
                        }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
                    busy = false; confirmPlan = null
                }
            })
    }
}

/** Google Play subscription: buy, restore, manage. The backend decides the plan. */
@Composable
private fun StoreSubscriptionPanel(model: AppModel) {
    val context = LocalContext.current
    val activity = androidx.activity.compose.LocalActivity.current
    val scope = rememberCoroutineScope()
    if (!model.isOn(OpsFlag.STORE_BILLING)) {
        Section(tx("Suscripción en Google Play", "Google Play subscription")) {
            Caption(model.flags.value.message(OpsFlag.STORE_BILLING, com.dincr.data.AppLanguage.current()) ?: tx("Las compras en Google Play estarán disponibles pronto.", "Google Play purchases will be available soon."))
        }
        return
    }
    val billing = model.storeBilling()
    val offers = rememberLoad(model) { billing.offers() }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    Section(tx("Suscripción en Google Play", "Google Play subscription")) {
        LoadContent(offers, rows = 2) { list ->
            if (list.all { it.details == null }) Caption(tx("Los planes de la tienda no están disponibles en esta versión de la app.", "Store plans aren’t available in this app version."))
            list.filter { it.details != null }.forEach { offer ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("${planName(offer.plan)} · ${if (offer.period == StoreBilling.Period.MONTHLY) tx("mensual", "monthly") else tx("anual", "yearly")}", style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
                        offer.price?.let { Caption(it) }
                    }
                    TextButton(enabled = !busy && activity != null, onClick = {
                        busy = true; message = null
                        scope.launch {
                            runCatching { billing.purchase(activity!!, offer) { result ->
                                busy = false
                                result.onSuccess { model.retryIdentity(); model.showNotice(tx("Suscripción activa", "Subscription active")) }.onFailure { message = it.message }
                            } }.onFailure { busy = false; message = it.message }
                        }
                    }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Suscribirme", "Subscribe"), color = Dincr.colors.tint) }
                }
            }
        }
        message?.let { Caption(it) }
        Row {
            TextButton(enabled = !busy, onClick = {
                busy = true; message = null
                scope.launch {
                    runCatching { billing.restore() }.onSuccess { model.retryIdentity(); message = tx("Revisamos tus compras ($it).", "We checked your purchases ($it).") }.onFailure { message = it.message }
                    busy = false
                }
            }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Restaurar compras", "Restore purchases"), color = Dincr.colors.tint) }
            TextButton({ openInBrowser(context, "https://play.google.com/store/account/subscriptions?package=${context.packageName}") }, modifier = Modifier.heightIn(min = 48.dp)) {
                Text(tx("Administrar", "Manage"), color = Dincr.colors.tint)
            }
        }
    }
}

/** I2/I3 — support: a report to the team and the status of previous ones. */
@Composable
fun SupportScreen(model: AppModel, nav: Navigator) {
    val tickets = rememberLoad(model) { model.api.supportTickets() }
    var category by remember { mutableStateOf("error") }
    var subject by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var sending by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    DetailScaffold(tx("Ayuda y soporte", "Help and support"), nav::back) {
        Section(tx("Contanos qué pasó", "Tell us what happened")) {
            ChoiceChips(listOf("error" to tx("Un problema", "A problem"), "improvement" to tx("Una idea", "An idea"), "payment" to tx("Pagos", "Payments"), "security" to tx("Seguridad", "Security")), category, { category = it })
            FormField(tx("Asunto", "Subject"), subject, { subject = it; errors = errors - "subject" }, errors["subject"])
            FormField(tx("Detalle", "Details"), message, { message = it; errors = errors - "message" }, errors["message"], singleLine = false,
                supporting = tx("No incluyas contraseñas ni números completos de tarjeta.", "Don’t include passwords or full card numbers."))
            error?.let { ErrorState(it) }
            DincrPrimaryButton(tx("Enviar", "Send"), loading = sending, onClick = {
                val found = mutableMapOf<String, String>()
                if (subject.trim().length !in 3..140) found["subject"] = tx("Entre 3 y 140 caracteres.", "3 to 140 characters.")
                if (message.trim().length !in 5..4000) found["message"] = tx("Entre 5 y 4000 caracteres.", "5 to 4000 characters.")
                errors = found
                if (found.isNotEmpty()) return@DincrPrimaryButton
                sending = true; error = null
                scope.launch {
                    model.load(tx("No pudimos enviar tu reporte.", "We couldn’t send your report.")) {
                        model.api.createSupportTicket(SupportRequest(category, subject.trim(), message.trim(), model.appVersion.take(30), "native-android"))
                    }.onSuccess { created ->
                        subject = ""; message = ""
                        model.showNotice(tx("Recibimos tu reporte ${created.publicId.orEmpty()}.", "We received your report ${created.publicId.orEmpty()}."))
                        tickets.reload()
                    }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
                    sending = false
                }
            })
        }
        SectionTitle(tx("Mis reportes", "My reports"))
        LoadContent(tickets, rows = 2) { list ->
            if (list.isEmpty()) Caption(tx("Todavía no enviaste reportes.", "You haven’t sent any reports yet."))
            list.forEach { ticket ->
                DincrCard {
                    Column {
                        Text(ticket.subject.orEmpty(), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                        Caption(listOfNotNull(ticket.publicId, ticketStatus(ticket.status), dateLabel(ticket.createdAt)).joinToString(" · "))
                        if (ticket.status == "resolved" && ticket.userResolution == null) Row {
                            TextButton({ scope.launch { model.load("") { model.api.resolveTicket(ticket.id, true) }; tickets.reload() } }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Quedó resuelto", "It’s solved"), color = Dincr.colors.tint) }
                            TextButton({ scope.launch { model.load("") { model.api.resolveTicket(ticket.id, false) }; tickets.reload() } }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Sigue pasando", "Still happening"), color = Dincr.colors.tint) }
                        }
                    }
                }
            }
        }
    }
}

private fun ticketStatus(status: String?) = when (status) {
    "open", "new" -> tx("Abierto", "Open"); "in_progress" -> tx("En revisión", "In progress"); "resolved" -> tx("Resuelto", "Resolved"); "closed" -> tx("Cerrado", "Closed"); else -> status
}
