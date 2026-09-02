package com.connecttophone.net

import android.os.Build
import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

class LanConnectionClient(
    private val scope: CoroutineScope,
    private val deviceId: String,
    private val deviceName: String,
    private val onConnectionStateChanged: (isConnected: Boolean, details: String) -> Unit,
    private val onMessageReceived: (type: String, payload: JsonObject, sourceId: String) -> Unit
) {
    private val TAG = "LanConnectionClient"
    private val gson = Gson()

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    private var activeWebSocket: WebSocket? = null
    private var isIntentionalDisconnect = false
    private var reconnectJob: Job? = null

    var currentHostIp: String? = null
        private set
    var currentPort: Int = 42100
        private set
    var currentAuthToken: String? = null
        private set
    private var pendingPairPin: String? = null

    var isConnected: Boolean = false
        private set

    fun setAuthToken(token: String) {
        currentAuthToken = token
        pendingPairPin = null
    }

    fun connectForPairing(hostIp: String, port: Int, pin: String) {
        connect(hostIp, port, null, pin)
    }

    fun connect(hostIp: String, port: Int, authToken: String?, pairPin: String? = null) {
        currentHostIp = hostIp
        currentPort = port
        currentAuthToken = authToken
        pendingPairPin = pairPin
        isIntentionalDisconnect = false

        reconnectJob?.cancel()
        disconnectInternal()

        val wsUrl = "ws://$hostIp:$port"
        Log.d(TAG, "Connecting to $wsUrl...")
        onConnectionStateChanged(false, "Conectando a $hostIp:$port...")

        val request = Request.Builder().url(wsUrl).build()

        activeWebSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d(TAG, "WebSocket connected, performing handshake...")

                // Send pairing request or authentication
                val pin = pendingPairPin
                val token = currentAuthToken
                if (!pin.isNullOrEmpty()) {
                    Log.d(TAG, "Sending PAIR_REQUEST with PIN: $pin")
                    sendPairRequest(pin)
                    onConnectionStateChanged(false, "Validando PIN de pareamento...")
                } else if (!token.isNullOrEmpty()) {
                    Log.d(TAG, "Sending AUTH_CONNECT token...")
                    val authMsg = BaseMessage(
                        type = MessageType.AUTH_CONNECT,
                        sourceId = deviceId,
                        payload = AuthConnectPayload(
                            authToken = token,
                            deviceName = deviceName,
                            model = "${Build.MANUFACTURER} ${Build.MODEL}",
                            androidVersion = "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"
                        )
                    )
                    webSocket.send(gson.toJson(authMsg))
                    onConnectionStateChanged(false, "Autenticando com PC...")
                }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val jsonObj = gson.fromJson(text, JsonObject::class.java)
                    val type = jsonObj.get("type")?.asString ?: return
                    val sourceId = jsonObj.get("source_id")?.asString ?: ""
                    val payload = jsonObj.getAsJsonObject("payload") ?: JsonObject()

                    if (type == MessageType.PING) {
                        val pong = BaseMessage(type = MessageType.PONG, sourceId = deviceId, payload = emptyMap<String, String>())
                        webSocket.send(gson.toJson(pong))
                    } else {
                        onMessageReceived(type, payload, sourceId)
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error handling message: ${e.message}")
                }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closing: $reason")
                webSocket.close(1000, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closed: $reason")
                handleDisconnect("Desconectado")
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket failure: ${t.message}")
                handleDisconnect("Falha na conexão: ${t.message}")
            }
        })
    }

    fun sendPairRequest(pin: String) {
        val msg = BaseMessage(
            type = MessageType.PAIR_REQUEST,
            sourceId = deviceId,
            payload = PairRequestPayload(
                pin = pin,
                deviceName = deviceName,
                model = "${Build.MANUFACTURER} ${Build.MODEL}"
            )
        )
        sendJson(gson.toJson(msg))
    }

    fun sendClipboardText(text: String) {
        if (!isConnected) return
        val msg = BaseMessage(
            type = MessageType.CLIPBOARD_TEXT,
            sourceId = deviceId,
            payload = ClipboardTextPayload(content = text)
        )
        sendJson(gson.toJson(msg))
    }

    fun sendClipboardImage(base64Data: String) {
        if (!isConnected) return
        val msg = BaseMessage(
            type = MessageType.CLIPBOARD_IMAGE,
            sourceId = deviceId,
            payload = ClipboardImagePayload(format = "png", data = base64Data)
        )
        sendJson(gson.toJson(msg))
    }

    fun sendDeviceStatus(batteryLevel: Int, isCharging: Boolean, wifiSsid: String) {
        if (!isConnected) return
        val msg = BaseMessage(
            type = MessageType.DEVICE_STATUS,
            sourceId = deviceId,
            payload = DeviceStatusPayload(batteryLevel, isCharging, wifiSsid)
        )
        sendJson(gson.toJson(msg))
    }

    fun sendStreamFrame(base64Frame: String, width: Int, height: Int) {
        if (!isConnected) return
        val msg = BaseMessage(
            type = MessageType.STREAM_FRAME,
            sourceId = deviceId,
            payload = StreamFramePayload(
                format = "jpeg",
                data = base64Frame,
                width = width,
                height = height
            )
        )
        sendJson(gson.toJson(msg))
    }

    fun setAuthenticated(authenticated: Boolean, details: String) {
        isConnected = authenticated
        onConnectionStateChanged(authenticated, details)
    }

    fun sendStreamStop(reason: String = "User stopped") {
        val msg = BaseMessage(
            type = MessageType.STREAM_STOP,
            sourceId = deviceId,
            payload = mapOf("reason" to reason)
        )
        sendJson(gson.toJson(msg))
    }

    fun sendStreamStartResponse(status: String) {
        val msg = BaseMessage(
            type = MessageType.STREAM_START_RESP,
            sourceId = deviceId,
            payload = mapOf("status" to status)
        )
        sendJson(gson.toJson(msg))
    }

    private fun sendJson(jsonStr: String): Boolean {
        return try {
            activeWebSocket?.send(jsonStr) ?: false
        } catch (e: Exception) {
            Log.e(TAG, "Error sending data: ${e.message}")
            false
        }
    }

    private fun handleDisconnect(reason: String) {
        isConnected = false
        activeWebSocket = null
        onConnectionStateChanged(false, reason)

        if (!isIntentionalDisconnect && currentHostIp != null) {
            scheduleReconnect()
        }
    }

    private fun scheduleReconnect() {
        reconnectJob?.cancel()
        reconnectJob = scope.launch(Dispatchers.IO) {
            delay(3000)
            if (!isIntentionalDisconnect && currentHostIp != null && !isConnected) {
                Log.d(TAG, "Attempting auto-reconnect...")
                connect(currentHostIp!!, currentPort, currentAuthToken)
            }
        }
    }

    private fun disconnectInternal() {
        try {
            activeWebSocket?.close(1000, "Normal closure")
        } catch (e: Exception) {
            // Ignore
        }
        activeWebSocket = null
        isConnected = false
    }

    fun disconnect() {
        isIntentionalDisconnect = true
        reconnectJob?.cancel()
        disconnectInternal()
        onConnectionStateChanged(false, "Desconectado pelo usuário")
    }
}
