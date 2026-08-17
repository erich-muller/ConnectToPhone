package com.connecttophone.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.connecttophone.ConnectApp
import com.connecttophone.MainActivity
import com.connecttophone.R
import com.connecttophone.net.DeviceDiscovery
import com.connecttophone.net.LanConnectionClient
import com.connecttophone.net.MessageType
import com.connecttophone.util.PreferencesManager
import com.google.gson.JsonObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class CompanionService : Service() {

    companion object {
        private const val TAG = "CompanionService"
        private const val NOTIFICATION_ID = 1001

        var instance: CompanionService? = null
            private set

        fun triggerClipboardCheck() {
            instance?.clipboardSyncManager?.onClipboardChanged()
        }

        fun sendScreenFrame(base64Frame: String, width: Int, height: Int) {
            instance?.lanClient?.sendStreamFrame(base64Frame, width, height)
        }
    }

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private lateinit var prefs: PreferencesManager
    private var lanClient: LanConnectionClient? = null
    private var deviceDiscovery: DeviceDiscovery? = null
    private var clipboardSyncManager: ClipboardSyncManager? = null

    private var statusUpdateJob: Job? = null
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        prefs = PreferencesManager(this)

        startForeground(NOTIFICATION_ID, buildNotification(getString(R.string.service_searching)))

        setupNetworkCallback()
        setupClipboard()
        setupNetworking()

        startPeriodicStatusReporting()
        Log.d(TAG, "CompanionService created and started in foreground")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Ensure connection is active
        tryConnectOrDiscover()
        return START_STICKY
    }

    private fun setupNetworking() {
        lanClient = LanConnectionClient(
            scope = serviceScope,
            deviceId = prefs.deviceId,
            deviceName = prefs.deviceName,
            onConnectionStateChanged = { isConnected, details ->
                updateNotification(if (isConnected) getString(R.string.service_connected) else details)
                if (isConnected) {
                    reportDeviceStatus()
                }
            },
            onMessageReceived = { type, payload ->
                handleIncomingMessage(type, payload)
            }
        )

        deviceDiscovery = DeviceDiscovery(
            context = this,
            deviceId = prefs.deviceId,
            deviceName = prefs.deviceName,
            onPcDiscovered = { pcId, pcName, ip, port ->
                // If paired or auto-connect enabled, connect immediately
                if (prefs.pairedPcId == pcId || !prefs.isPaired) {
                    if (lanClient?.isConnected == false) {
                        Log.d(TAG, "Connecting to discovered PC $pcName ($ip:$port)...")
                        lanClient?.connect(ip, port, prefs.authToken)
                    }
                }
            }
        )

        deviceDiscovery?.startListening(serviceScope)
        tryConnectOrDiscover()
    }

    private fun setupClipboard() {
        clipboardSyncManager = ClipboardSyncManager(
            context = this,
            onLocalTextCopied = { text ->
                if (prefs.syncClipboard) {
                    lanClient?.sendClipboardText(text)
                }
            },
            onLocalImageCopied = { b64 ->
                if (prefs.syncClipboard && prefs.syncImages) {
                    lanClient?.sendClipboardImage(b64)
                }
            }
        )
        clipboardSyncManager?.start()
    }

    private fun setupNetworkCallback() {
        connectivityManager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .build()

        networkCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                Log.d(TAG, "Wi-Fi connected. Attempting reconnection to Linux PC...")
                serviceScope.launch {
                    delay(1000)
                    tryConnectOrDiscover()
                }
            }

            override fun onLost(network: Network) {
                Log.d(TAG, "Wi-Fi lost")
                updateNotification(getString(R.string.service_searching))
            }
        }
        connectivityManager?.registerNetworkCallback(request, networkCallback!!)
    }

    fun tryConnectOrDiscover() {
        if (lanClient?.isConnected == true) return

        val ip = prefs.pairedPcIp
        val port = prefs.pairedPcPort
        val token = prefs.authToken

        if (!ip.isNullOrEmpty() && !token.isNullOrEmpty()) {
            lanClient?.connect(ip, port, token)
        } else {
            deviceDiscovery?.sendSearchBroadcast()
        }
    }

    fun initiatePairing(ip: String, port: Int, pin: String) {
        lanClient?.connect(ip, port, null)
        serviceScope.launch {
            delay(500)
            lanClient?.sendPairRequest(pin)
        }
    }

    private fun handleIncomingMessage(type: String, payload: JsonObject) {
        when (type) {
            MessageType.CLIPBOARD_TEXT -> {
                val text = payload.get("content")?.asString ?: ""
                if (text.isNotEmpty()) {
                    clipboardSyncManager?.applyRemoteText(text)
                }
            }
            MessageType.CLIPBOARD_IMAGE -> {
                val b64 = payload.get("data")?.asString ?: ""
                if (b64.isNotEmpty()) {
                    clipboardSyncManager?.applyRemoteImage(b64)
                }
            }
            MessageType.PAIR_RESPONSE -> {
                val status = payload.get("status")?.asString
                if (status == "accepted") {
                    val token = payload.get("auth_token")?.asString ?: ""
                    val pcName = payload.get("device_name")?.asString ?: "Linux PC"
                    prefs.savePairing("linux_pc", pcName, prefs.pairedPcIp ?: "", prefs.pairedPcPort, token)
                    Log.d(TAG, "Pairing successful! Saved credentials.")
                }
            }
            MessageType.STREAM_START_REQ -> {
                // Screen mirror requested by PC. Request permission in UI or forward intent
                val intent = Intent(this, MainActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    putExtra("ACTION_START_SCREEN_CAPTURE", true)
                }
                startActivity(intent)
            }
            MessageType.STREAM_STOP -> {
                stopService(Intent(this, ScreenCaptureService::class.java))
            }
            MessageType.INPUT_TOUCH -> {
                val action = payload.get("action")?.asString ?: "TAP"
                when (action.uppercase()) {
                    "TAP" -> {
                        val x = payload.get("x")?.asFloat ?: 0f
                        val y = payload.get("y")?.asFloat ?: 0f
                        val dur = payload.get("duration")?.asLong ?: 50L
                        ClipboardAccessibilityService.performTap(x, y, dur)
                    }
                    "SWIPE" -> {
                        val startX = payload.get("start_x")?.asFloat ?: 0f
                        val startY = payload.get("start_y")?.asFloat ?: 0f
                        val endX = payload.get("end_x")?.asFloat ?: 0f
                        val endY = payload.get("end_y")?.asFloat ?: 0f
                        val dur = payload.get("duration")?.asLong ?: 200L
                        ClipboardAccessibilityService.performSwipe(startX, startY, endX, endY, dur)
                    }
                }
            }
            MessageType.INPUT_KEY -> {
                val key = payload.get("key")?.asString ?: ""
                if (key.isNotEmpty()) {
                    ClipboardAccessibilityService.performGlobalKey(key)
                }
            }
        }
    }

    private fun startPeriodicStatusReporting() {
        statusUpdateJob = serviceScope.launch {
            while (isActive) {
                if (lanClient?.isConnected == true) {
                    reportDeviceStatus()
                }
                delay(15000) // Every 15s
            }
        }
    }

    private fun reportDeviceStatus() {
        val batteryIntent = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = batteryIntent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batteryIntent?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val batteryPct = if (level >= 0 && scale > 0) (level * 100 / scale) else 50
        val status = batteryIntent?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL

        val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
        val ssid = wifi?.connectionInfo?.ssid?.replace("\"", "") ?: "Wi-Fi"

        lanClient?.sendDeviceStatus(batteryPct, isCharging, ssid)
    }

    private fun buildNotification(statusText: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, ConnectApp.CHANNEL_ID_SERVICE)
            .setContentTitle(getString(R.string.service_running_title))
            .setContentText(statusText)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(statusText: String) {
        val notification = buildNotification(statusText)
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
        manager.notify(NOTIFICATION_ID, notification)
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        statusUpdateJob?.cancel()
        lanClient?.disconnect()
        deviceDiscovery?.stopListening()
        clipboardSyncManager?.stop()

        networkCallback?.let { connectivityManager?.unregisterNetworkCallback(it) }
        serviceScope.cancel()
        Log.d(TAG, "CompanionService destroyed")
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
