import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Backend configuration comes from local.properties (git-ignored) or the environment, never from
// the repository: `dincr.apiUrl`, `dincr.supabaseUrl`, `dincr.supabaseAnonKey` (the public
// anon/publishable key only). The `dincr` identity defaults the API to production, like the
// Capacitor app; Supabase values are always external. Without them the app stops at an
// "unconfigured" screen. Fixture data runs only in a debug build that asks for it
// (`dincr.fixtures=true`, or the UI tests' launch extra). Release builds never contain a way in.
val local = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}
fun setting(key: String, env: String): String = local.getProperty(key) ?: System.getenv(env) ?: ""
fun quoted(value: String) = "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

/** Production API, public in the Capacitor app's source (`frontend/src/lib/apiUrl.js`). */
val productionApiUrl = "https://jarvis-backend-152f.onrender.com"

android {
    namespace = "com.dincr.app"
    compileSdk = 36

    defaultConfig {
        minSdk = 24
        targetSdk = 36
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "DINCR_SUPABASE_URL", quoted(setting("dincr.supabaseUrl", "DINCR_SUPABASE_URL")))
        buildConfigField("String", "DINCR_SUPABASE_ANON_KEY", quoted(setting("dincr.supabaseAnonKey", "DINCR_SUPABASE_ANON_KEY")))
        buildConfigField("boolean", "DINCR_FIXTURES", "false")
    }

    // Two identities (docs: native/RELEASE_IDENTITY.md):
    // - `dincr`: the DINCR app id `com.dincr.app`, the redirect Supabase already allows
    //   (`com.dincr.app://auth/callback`) and the mail return deep links the backend sends. It
    //   installs over (replaces) the Capacitor app on a device; store purchases still need a
    //   Play-signed build.
    // - `nativedev`: a side-by-side development id. Live sign-in needs its redirect in the Supabase
    //   allowlist, which is not requested; use it with fixtures or a development project.
    flavorDimensions += "identity"
    productFlavors {
        create("dincr") {
            dimension = "identity"
            applicationId = "com.dincr.app"
            versionCode = 100
            versionName = "2.0.0-rc.1"
            buildConfigField("String", "DINCR_API_URL", quoted(setting("dincr.apiUrl", "DINCR_API_URL").ifEmpty { productionApiUrl }))
            buildConfigField("String", "AUTH_REDIRECT", quoted("com.dincr.app://auth/callback"))
            manifestPlaceholders["authScheme"] = "com.dincr.app"
            manifestPlaceholders["mailScheme"] = "com.dincr.app"
            manifestPlaceholders["legacyMailScheme"] = "com.finva.app"
        }
        create("nativedev") {
            dimension = "identity"
            applicationId = "com.dincr.app.nativedev"
            versionCode = 100
            versionName = "2.0.0-rc.1-dev"
            buildConfigField("String", "DINCR_API_URL", quoted(setting("dincr.apiUrl", "DINCR_API_URL")))
            buildConfigField("String", "AUTH_REDIRECT", quoted("com.dincr.app.nativedev://auth/callback"))
            manifestPlaceholders["authScheme"] = "com.dincr.app.nativedev"
            // The backend returns mail connections to one global deep link (com.finva.app by
            // default); this identity never claims it, so it cannot collide with the DINCR app.
            manifestPlaceholders["mailScheme"] = "com.dincr.app.nativedev"
            manifestPlaceholders["legacyMailScheme"] = "com.dincr.app.nativedev"
        }
    }

    buildTypes {
        debug {
            buildConfigField("boolean", "DINCR_FIXTURES", (local.getProperty("dincr.fixtures") == "true").toString())
        }
        release {
            buildConfigField("boolean", "DINCR_FIXTURES", "false")
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        // java.time on API 24–25 (minSdk parity with the Capacitor app).
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin { jvmToolchain(17) }

dependencies {
    coreLibraryDesugaring(libs.desugar.jdk.libs)
    implementation(project(":core:design"))
    implementation(project(":core:data"))
    implementation(libs.activity.compose)
    implementation(libs.fragment)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.lifecycle.runtime.compose)
    implementation(libs.lifecycle.process)
    implementation(libs.navigation.compose)
    implementation(libs.browser)
    implementation(libs.biometric)
    implementation(libs.billing)
    implementation(libs.coroutines.android)
    implementation(libs.serialization.json)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.runner)
}
