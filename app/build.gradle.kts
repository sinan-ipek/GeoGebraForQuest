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
        versionCode = 62
        versionName = "0.9.11"

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
}

// v0.9.11 registered media-surface diagnostic:
// - the working GeoGebra LayoutXML/WebView panel is completely untouched;
// - a second panel is registered through VideoSurfacePanelRegistration;
// - its Android Surface receives a synthetic full-colour L|R test frame;
// - MediaPanelSettings uses StereoMode.LeftRight so eye routing is performed by
//   the same registered compositor/panel path used by Meta's stereo media samples;
// - no custom stereo shader, SceneObject overlay or GeoGebra texture is involved.
spatial {
    allowUsageDataCollection.set(true)
    shaders {
        sources.add(project.layout.projectDirectory.dir("src/shaders"))
    }
}
