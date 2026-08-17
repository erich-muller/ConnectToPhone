package com.connecttophone.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent

class ClipboardAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "ClipboardAccessService"
        var instance: ClipboardAccessibilityService? = null
            private set

        fun performTap(normX: Float, normY: Float, durationMs: Long = 50L): Boolean {
            val service = instance ?: return false
            val (realX, realY) = service.toRealPixels(normX, normY)

            val path = Path().apply {
                moveTo(realX, realY)
            }
            val stroke = GestureDescription.StrokeDescription(path, 0, durationMs.coerceAtLeast(20L))
            val gesture = GestureDescription.Builder().addStroke(stroke).build()
            val dispatched = service.dispatchGesture(gesture, null, null)
            Log.d(TAG, "Dispatched TAP at ($realX, $realY) -> $dispatched")
            return dispatched
        }

        fun performSwipe(startNormX: Float, startNormY: Float, endNormX: Float, endNormY: Float, durationMs: Long = 200L): Boolean {
            val service = instance ?: return false
            val (startX, startY) = service.toRealPixels(startNormX, startNormY)
            val (endX, endY) = service.toRealPixels(endNormX, endNormY)

            val path = Path().apply {
                moveTo(startX, startY)
                lineTo(endX, endY)
            }
            val stroke = GestureDescription.StrokeDescription(path, 0, durationMs.coerceIn(50L, 1000L))
            val gesture = GestureDescription.Builder().addStroke(stroke).build()
            val dispatched = service.dispatchGesture(gesture, null, null)
            Log.d(TAG, "Dispatched SWIPE from ($startX, $startY) to ($endX, $endY) in ${durationMs}ms -> $dispatched")
            return dispatched
        }

        fun performGlobalKey(key: String): Boolean {
            val service = instance ?: return false
            return when (key.uppercase()) {
                "BACK" -> service.performGlobalAction(GLOBAL_ACTION_BACK)
                "HOME" -> service.performGlobalAction(GLOBAL_ACTION_HOME)
                "RECENTS" -> service.performGlobalAction(GLOBAL_ACTION_RECENTS)
                "NOTIFICATIONS" -> service.performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
                "LOCK" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) service.performGlobalAction(GLOBAL_ACTION_LOCK_SCREEN) else false
                else -> false
            }
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        Log.d(TAG, "ClipboardAccessibilityService connected with gesture capability")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return

        val eventType = event.eventType
        if (eventType == AccessibilityEvent.TYPE_VIEW_TEXT_SELECTION_CHANGED ||
            eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
            eventType == AccessibilityEvent.TYPE_VIEW_CLICKED) {
            CompanionService.triggerClipboardCheck()
        }
    }

    override fun onInterrupt() {
        Log.d(TAG, "ClipboardAccessibilityService interrupted")
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
    }

    private fun toRealPixels(normX: Float, normY: Float): Pair<Float, Float> {
        val windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val bounds = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            windowManager.currentWindowMetrics.bounds
        } else {
            val dm = DisplayMetrics()
            @Suppress("DEPRECATION")
            windowManager.defaultDisplay.getRealMetrics(dm)
            Rect(0, 0, dm.widthPixels, dm.heightPixels)
        }

        val screenW = bounds.width().toFloat()
        val screenH = bounds.height().toFloat()

        val realX = (normX.coerceIn(0.0f, 1.0f) * screenW).coerceIn(0.0f, screenW - 1f)
        val realY = (normY.coerceIn(0.0f, 1.0f) * screenH).coerceIn(0.0f, screenH - 1f)
        return Pair(realX, realY)
    }
}
