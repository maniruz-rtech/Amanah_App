package com.amanah.app

import android.app.Application
import android.content.pm.ApplicationInfo
import com.amanah.app.di.AppGraph
import com.amanah.feature.core.debug.AmanahDebugDrawer

class AmanahApplication : Application() {

    private val isDebuggable: Boolean
        get() = (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0

    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()

        graph = AppGraph(appContext = this, debugBuild = isDebuggable)

        // Bind ProcessLifecycleOwner → RealtimeGateway so background/foreground
        // events flow into the gateway without it knowing about Android lifecycle.
        graph.foregroundObserver.attach()

        // Bridge FCM signals (token rotation, silent wakeup) into the graph.
        graph.startPushIntegration()

        AmanahDebugDrawer.isEnabled = isDebuggable
        if (AmanahDebugDrawer.isEnabled) {
            AmanahDebugDrawer.registerFeature("LoginFeature")
            AmanahDebugDrawer.registerFeature("AdminFeature")
            AmanahDebugDrawer.registerFeature("UserFeature")
            AmanahDebugDrawer.registerFeature("EmergencyFeature")
        }
    }
}
