# R8 / Release Hardening

The rules file lives at `app/proguard-rules.pro` and is referenced from
`app/BUILD.bazel` via `proguard_specs`. This document explains what each stanza
defends against and how to validate a release build.

## Why this matters in an emergency app

Reflection-using libraries (Gson, Retrofit, Reaktive's adapters, MVICore's
binder) silently misbehave under R8 when their entry points are obfuscated.
The failure mode is almost never a crash — it's "JSON has all empty fields",
"no events ever arrive on the stream", "the WebSocket connects but no message
ever decodes". Debugging this *post-release* is brutal because debug builds
have R8 off.

The rules file is annotated stanza-by-stanza for that reason.

## Stanza catalogue

| Stanza | Library | What breaks without it |
|---|---|---|
| `-keep class com.google.gson.**`, `@SerializedName` keep | Gson | All `@SerializedName("...")`-mapped fields silently round-trip as null. |
| `-keepclassmembers ... com.amanah.feature.core.network.**` / `realtime.RealtimeEnvelope` | Amanah DTOs | Same as above — Gson reflection sees obfuscated field names. |
| Retrofit interface keep | Retrofit | `Retrofit.create(ApiService::class.java)` resolves to a Proxy whose `invoke` reads method/annotation reflectively. Stripped methods become `MethodNotFoundException` at first call. |
| OkHttp suppressions | OkHttp | OkHttp's PublicSuffixDatabase uses reflection to resolve platform internals. Without the keepname rule R8 strips the class and logging fails. |
| `-keep class com.badoo.reaktive.**` | Reaktive | Reaktive's scheduler and disposable contracts have package-private reflective access — strip = NPE on `subscribe`. |
| `-keep class com.badoo.mvicore.**` | MVICore | Binder uses reflective constructor lookup on `Feature` subclasses. |
| `-keepclassmembers ... GeneratedMessageLite`, protobuf dontwarn | DataStore | DataStore's proto module emits generated classes accessed by name; we keep the safety net even though we currently only use Preferences. |
| Coroutines dontwarn | Coroutines | Removes ServiceLoader warnings; without them R8 still works but emits walls of warnings that hide real issues. |
| `-keep class com.uber.h3core.**` | H3 | JNI bridge class name is referenced by the native lib loader. |
| Compose runtime keep | Compose | Generated `ComposableInferredTarget`/state class names are looked up reflectively at composition time. |
| Nodes framework constructors | In-house Nodes lib | `routerFactory(interactor)` lambdas instantiate routers reflectively in `Node.performAttach`. |
| `-keepattributes SourceFile, LineNumberTable` | Crash reporting | Without this, Sentry / Crashlytics symbolication is useless. |
| `assumenosideeffects Log.v/d/i` | Performance + security | Strips verbose / debug / info log calls from release. Crash-relevant `warn` / `error` survive. |

## Validation checklist

A release build is acceptable only when every line is checked.

- [ ] `bazel build //app:amanah --compilation_mode=opt` succeeds with no R8 warnings (warnings ≠ errors but each is a future bug).
- [ ] `adb install` of the release APK launches without ANR within 2 s on a Pixel 7 (R8 misconfig often triggers slow first-class-load).
- [ ] Login → load dashboard → trigger emergency (against a staging backend) → live responder updates render on the map. If any step regresses vs the debug build, R8 is stripping something it shouldn't.
- [ ] `logcat | grep AndroidRuntime` over a full demo run shows zero `NoSuchMethodError` / `NoSuchFieldException` / `ClassNotFoundException`.
- [ ] APK size before/after rules: rules should NOT bloat the APK by > 10 %. If they do, you've kept too much — narrow the rule.
- [ ] Mapping file (`mapping.txt`) is uploaded to Sentry / Crashlytics. Untrusted developers must not have access — the mapping file leaks symbol → name correspondence.
- [ ] Try a network-error path (block `api.amanah.example` in /etc/hosts) — exception messages should still be human-readable; if they show `Ljava/lang/Object;`, source attribute keep is missing.

## Smoke-test script

```bash
# Build release APK
bazel build //app:amanah --compilation_mode=opt

# Install on connected device
adb install -r bazel-bin/app/amanah.apk

# Run the demo flow scripted via UI Automator
adb shell am instrument -w com.amanah.app.test/.SmokeRunner

# Inspect logcat for stripped-class errors
adb logcat -d AndroidRuntime:E '*:S' | grep -E 'NoSuch(Method|Field|Class)|ClassNotFoundException'
```

If the last grep returns anything, you have an R8 regression.

## When to add a new rule

Whenever you add a dependency that uses reflection. Test:

1. Build a release APK with the new dep but no new rule.
2. Run the smoke test.
3. If it fails, the failure message will tell you which class is missing — add the narrowest `-keep` that resolves it. Avoid `-keep class your.package.** { *; }` unless absolutely necessary; it disables R8's value for that package.

## Rule rot

If you delete a dependency, **remove its rules**. Stale `-keep`s prevent R8 from optimising code that's still present but no longer needs the protection — costs APK size and slows the build.

The current file has been pruned of Scarlet rules (Scarlet was removed in this hardening pass).
