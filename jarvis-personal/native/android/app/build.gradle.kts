import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

// Backend configuration comes from local.properties (git-ignored). Without it the app runs on
// synthetic fixture data, like the iOS prototype.
val local = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}
fun localValue(key: String) = "\"" + (local.getProperty(key) ?: "") + "\""

android {
    namespace = "com.dincr.app"
    compileSdk = 36

    defaultConfig {
        // The prototype never replaces the store app: taking over com.dincr.app is a release decision.
        applicationId = "com.dincr.app.nativedev"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "DINCR_API_URL", localValue("dincr.apiUrl"))
        buildConfigField("String", "DINCR_SUPABASE_URL", localValue("dincr.supabaseUrl"))
        buildConfigField("String", "DINCR_SUPABASE_ANON_KEY", localValue("dincr.supabaseAnonKey"))
    }

    buildTypes {
        release {
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
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.lifecycle.runtime.compose)
    implementation(libs.navigation.compose)
    implementation(libs.browser)
    implementation(libs.coroutines.android)
    implementation(libs.serialization.json)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.runner)
}
