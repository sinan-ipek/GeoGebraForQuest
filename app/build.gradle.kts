plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
    alias(libs.plugins.meta.spatial.plugin)
    alias(libs.plugins.compose.compiler)
}

android {
    namespace = "com.sinan.geogebraforquest"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.sinan.geogebraforquest"
        minSdk = 34
        targetSdk = 34
        versionCode = 24
        versionName = "0.6.2"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        resources.excludes.add("META-INF/LICENSE")
    }

    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    debugImplementation(libs.androidx.ui.tooling)

    implementation("androidx.webkit:webkit:1.12.1")

    implementation(libs.meta.spatial.sdk.base)
    implementation(libs.meta.spatial.sdk.vr)
    implementation(libs.meta.spatial.sdk.compose)
    implementation(libs.meta.spatial.sdk.toolkit)
}

// v0.6.2 keeps the proven StereoMode.LeftRight output path from v0.6.1 but
// replaces the synthetic targets with GeoGebra's raw JavaScript-captured SBS
// frame. No WebView screenshot or 3D-portal composition is involved.
spatial {
    allowUsageDataCollection.set(true)
}
