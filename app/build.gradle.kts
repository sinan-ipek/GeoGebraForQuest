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
        versionCode = 113
        versionName = "0.9.30-exp25-embedded-picker-popup-whitelist"

        ndkVersion = "27.0.12077973"
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
    implementation(libs.meta.spatial.sdk.isdk)
}

// v0.9.30-exp25-embedded-picker-popup-whitelist lives only on experimental-embedded-stereo.
// Stable v0.9.29 remains frozen on stable-v0.9.29-palette.
// Exp25 keeps Exp24's ActivityPanel picker architecture but matches Meta's official embedding
// contract: allowEmbedded + CREATE_ACTIVITY_CONTAINER + executeOnVrActivity result bridge.
// Remote popup navigation is now a strict whitelist: accounts/callback only; material routes are
// handed to MAIN and all other GeoGebra popup routes are blocked before rendering.
spatial {
    allowUsageDataCollection.set(true)
    shaders {
        sources.add(project.layout.projectDirectory.dir("src/shaders"))
    }
}
