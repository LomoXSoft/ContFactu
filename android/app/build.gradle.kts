import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "soft.lomox.contfactu"
    compileSdk = 35

    defaultConfig {
        applicationId = "soft.lomox.contfactu"
        minSdk = 26
        targetSdk = 35
        val versionPublica = "0.2.0"
        versionCode = 4
        versionName = versionPublica
        resValue("string", "app_name", "ContFactu $versionPublica")
    }

    // Firma de publicación. La clave y su contraseña nunca entran en el repositorio.
    // Se lee un .properties que esté fuera de git: el que indique la variable de entorno
    // CONTFACTU_FIRMA o, si no, android/keystore.properties (ignorado por .gitignore).
    // Claves: storeFile, storePassword o storePasswordFile, keyAlias y, opcional, keyPassword.
    // Las rutas relativas se resuelven desde la carpeta del propio .properties.
    // Sin ese archivo, assembleRelease genera un APK sin firmar.
    val firmaProps: File? = (System.getenv("CONTFACTU_FIRMA")?.takeIf { it.isNotBlank() }?.let { File(it) }
        ?: rootProject.file("keystore.properties")).takeIf { it.isFile }
    signingConfigs {
        if (firmaProps != null) {
            create("publicacion") {
                val p = Properties().apply { firmaProps.inputStream().use { load(it) } }
                fun ruta(s: String): File = File(s).let { if (it.isAbsolute) it else File(firmaProps.parentFile, s) }
                fun dato(k: String): String? = p.getProperty(k)?.trim()?.takeIf { it.isNotEmpty() }
                val clave = dato("storePassword")
                    ?: dato("storePasswordFile")?.let { ruta(it).readText().trim() }
                    ?: throw GradleException("Falta storePassword o storePasswordFile en ${firmaProps.name}.")
                storeFile = ruta(dato("storeFile") ?: throw GradleException("Falta storeFile en ${firmaProps.name}."))
                storePassword = clave
                keyAlias = dato("keyAlias") ?: "contfactu"
                keyPassword = dato("keyPassword") ?: clave
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("publicacion")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
            excludes += "/META-INF/DEPENDENCIES"
        }
    }
    lint { abortOnError = false }
}

base {
    archivesName.set("ContFactu-0.2.0")
}

dependencies {
    implementation(project(":nucleo"))
    val bom = platform("androidx.compose:compose-bom:2025.02.00")
    implementation(bom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.navigation:navigation-compose:2.8.9")
    implementation("androidx.core:core-ktx:1.15.0")
    val camera = "1.4.1"
    implementation("androidx.camera:camera-core:$camera")
    implementation("androidx.camera:camera-camera2:$camera")
    implementation("androidx.camera:camera-lifecycle:$camera")
    implementation("androidx.camera:camera-view:$camera")
    implementation("com.google.zxing:core:3.5.3")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
