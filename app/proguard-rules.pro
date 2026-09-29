# =============================================================================
# Amanah_App — R8 / ProGuard release-build keep rules
# =============================================================================
# Drop into //app:amanah as `proguard_specs = ["proguard-rules.pro"]`.
#
# Every rule has a reason comment. Do not delete a rule without verifying that
# the corresponding library is no longer in the dependency graph — silent
# stripping of reflection-using code produces release-only crashes that don't
# reproduce in debug builds.
# =============================================================================


# --- Gson ---------------------------------------------------------------------
# Gson uses reflection on @SerializedName-annotated data classes. Keep:
#   - The annotation itself (so reflection finds it on stripped classes)
#   - Every data class field annotated with @SerializedName
#   - Field name (don't allow R8 to obfuscate field identifiers used by JSON)
#
# Without this, RealtimeEnvelope / LoginRequest / SosRequest etc. would round-
# trip with missing fields and parsing would silently succeed with empty data.

-keepattributes Signature, *Annotation*, EnclosingMethod, InnerClasses
-keep class com.google.gson.** { *; }
-keep class * extends com.google.gson.TypeAdapter
-keep class * implements com.google.gson.TypeAdapterFactory
-keep class * implements com.google.gson.JsonSerializer
-keep class * implements com.google.gson.JsonDeserializer

-keep class com.google.gson.annotations.SerializedName
-keepclassmembers,allowobfuscation class * {
    @com.google.gson.annotations.SerializedName <fields>;
}

# Keep ALL classes Amanah ships with @SerializedName fields. Belt-and-braces.
-keep,allowobfuscation @interface com.google.gson.annotations.SerializedName


# --- Amanah realtime + network DTOs ------------------------------------------
# Every DTO that goes over the wire is referenced reflectively by Gson. Keeping
# the *member* names is critical — class name obfuscation is fine.

-keepclassmembers,allowobfuscation class com.amanah.feature.core.network.** {
    <fields>;
    <init>(...);
}
-keepclassmembers,allowobfuscation class com.amanah.feature.core.realtime.RealtimeEnvelope {
    <fields>;
    <init>(...);
}
-keep,allowobfuscation class com.amanah.feature.emergency.model.** { <fields>; <init>(...); }


# --- Retrofit -----------------------------------------------------------------
# Retrofit consults interface methods + annotations at runtime via reflection.
# Without these, all @POST / @GET methods become unresolvable in release.

-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class retrofit2.Response

# Keep Amanah's ApiService interface as-is; the methods are accessed by name
# through Retrofit's Proxy implementation.
-keep interface com.amanah.feature.core.network.ApiService {
    *;
}
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations


# --- OkHttp -------------------------------------------------------------------
# OkHttp ships its own embedded ProGuard config but we restate the must-haves
# to survive an R8 schema bump.

-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
-keepnames class okhttp3.internal.publicsuffix.PublicSuffixDatabase


# --- Reaktive (Badoo) ---------------------------------------------------------
# Reaktive uses introspection in a few places (chiefly the test schedulers and
# the disposable contract). The library doesn't ship a consumer proguard file
# so we keep the public surface explicitly.

-keep class com.badoo.reaktive.** { *; }
-dontwarn com.badoo.reaktive.**


# --- MVICore (Badoo) ----------------------------------------------------------
# MVICore Feature inherits from BaseFeature which uses reflective constructor
# calls in the binder package. Keep the binder + element interfaces.

-keep class com.badoo.mvicore.** { *; }
-keep interface com.badoo.mvicore.element.** { *; }
-dontwarn com.badoo.mvicore.**


# --- Tink (Google) ------------------------------------------------------------
# Tink ships its own proguard rules in the AAR; we just suppress the warnings
# that surface from optional protobuf-lite paths we don't use.

-dontwarn com.google.errorprone.annotations.**
-dontwarn javax.annotation.**


# --- Jetpack DataStore --------------------------------------------------------
# DataStore proto support uses reflection on generated classes — we only use
# Preferences which doesn't but keep the safety net for future Proto use.

-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
    <fields>;
}
-dontwarn com.google.protobuf.**


# --- Coroutines ---------------------------------------------------------------
# Stack-trace recovery uses reflective access to package-private fields. Keep.

-keepclassmembers class kotlinx.coroutines.internal.MainDispatcherFactory {
    <init>(...);
}
-dontwarn kotlinx.coroutines.flow.**inlined**


# --- Google Maps Compose ------------------------------------------------------
# Maps SDK ships its own proguard config; nothing extra required as long as we
# don't override map view classnames. Suppress JNI warnings.

-dontwarn com.google.android.gms.**


# --- Uber H3 (JNI) ------------------------------------------------------------
# H3 ships a native lib. Keep its loader & don't strip the JNI bridge class.

-keep class com.uber.h3core.** { *; }
-dontwarn com.uber.h3core.**


# --- Compose ------------------------------------------------------------------
# Compose compiler emits generated metadata classes that are accessed via
# reflection at composition time. Don't obfuscate. (AGP's default rules cover
# this; restated here for Bazel where we control the full ruleset.)

-keep class androidx.compose.runtime.** { *; }
-keepclassmembers class androidx.compose.runtime.** { *; }


# --- Amanah Nodes framework ---------------------------------------------------
# View / Interactor / Router instances are constructed reflectively from
# Node.routerFactory and viewFactory lambdas. Constructors must survive.

-keepclassmembers class com.amanah.lib.nodes.** { <init>(...); }


# --- Crash dump quality of life ----------------------------------------------
# Preserve source-file attribute so Sentry / Crashlytics produce useful traces.

-keepattributes SourceFile, LineNumberTable
-renamesourcefileattribute Amanah


# --- Strip logs in release ----------------------------------------------------
# Drop verbose / debug / info log calls. Crash-relevant warn / error stay.

-assumenosideeffects class android.util.Log {
    public static *** v(...);
    public static *** d(...);
    public static *** i(...);
}


# --- Optional / vendor classes referenced by AndroidX ------------------------
# Gradle/AGP injects these from AAR consumer rules; under Bazel we declare them.
# androidx.window talks to OEM extension libraries that only exist on foldables.
# ListenableFuture (Guava) is an optional dependency of androidx.concurrent.

-dontwarn androidx.window.extensions.**
-dontwarn androidx.window.sidecar.**
-dontwarn com.google.common.util.concurrent.ListenableFuture
