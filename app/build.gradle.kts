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
        versionCode = 59
        versionName = "0.9.8"

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

// v0.9.8 eye-pass portal architecture:
// - the ordinary LayoutXML/WebView panel and its mesh are never replaced;
// - GeoGebra keeps the permanent 2x-wide full-colour L|R source buffer;
// - a separate non-interactive child SceneObject is created after scene, VR,
//   WebView and a valid 3D layout are ready;
// - getStereoPassId() is evaluated in the vertex shader, matching Meta's
//   official stereo shader pattern;
// - popup/settings overlaps punch holes in the portal instead of disabling the
//   complete stereo layer and exposing raw SBS across the whole 3D view.
spatial {
    allowUsageDataCollection.set(true)
    shaders {
        sources.add(project.layout.projectDirectory.dir("src/shaders"))
    }
}
