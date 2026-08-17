package com.connecttophone.net

import android.content.Context
import android.net.wifi.WifiManager
import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

class DeviceDiscovery(
    private val context: Context,
    private val deviceId: String,
    private val deviceName: String,
    private val onPcDiscovered: (pcId: String, pcName: String, ip: String, port: Int) -> Unit
) {
    private val TAG = "DeviceDiscovery"
    private val DISCOVERY_PORT = 42101
    private val gson = Gson()

    private var isListening = false
    private var socket: DatagramSocket? = null
    private var multicastLock: WifiManager.MulticastLock? = null
    private var listenerJob: Job? = null

    fun startListening(scope: CoroutineScope) {
        if (isListening) return
        isListening = true

        acquireMulticastLock()

        listenerJob = scope.launch(Dispatchers.IO) {
            try {
                socket = DatagramSocket(DISCOVERY_PORT).apply {
                    broadcast = true
                    soTimeout = 3000
                }
                val buffer = ByteArray(4096)
                val packet = DatagramPacket(buffer, buffer.size)

                Log.d(TAG, "Discovery listener started on port $DISCOVERY_PORT")

                // Immediately send search packet
                sendSearchBroadcast()

                while (isActive && isListening) {
                    try {
                        socket?.receive(packet)
                        val senderIp = packet.address.hostAddress ?: continue
                        val rawJson = String(packet.data, 0, packet.length, Charsets.UTF_8)
                        val jsonObj = gson.fromJson(rawJson, JsonObject::class.java)

                        val type = jsonObj.get("type")?.asString
                        val sourceId = jsonObj.get("source_id")?.asString ?: ""

                        if (sourceId != deviceId && type == MessageType.DISCOVERY_BEACON) {
                            val payload = jsonObj.getAsJsonObject("payload")
                            val pcName = payload.get("device_name")?.asString ?: "Linux PC"
                            val port = payload.get("ws_port")?.asInt ?: 42100

                            Log.d(TAG, "Found Linux PC: $pcName at $senderIp:$port")
                            onPcDiscovered(sourceId, pcName, senderIp, port)
                        }
                    } catch (e: java.net.SocketTimeoutException) {
                        // Periodic broadcast search
                        sendSearchBroadcast()
                    } catch (e: Exception) {
                        if (isListening) {
                            Log.e(TAG, "Error in receive loop: ${e.message}")
                            delay(1000)
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start discovery socket: ${e.message}")
            } finally {
                stopListening()
            }
        }
    }

    fun sendSearchBroadcast() {
        try {
            val msg = BaseMessage(
                type = MessageType.DISCOVERY_SEARCH,
                sourceId = deviceId,
                payload = mapOf(
                    "device_name" to deviceName,
                    "platform" to "android"
                )
            )
            val jsonStr = gson.toJson(msg)
            val data = jsonStr.toByteArray(Charsets.UTF_8)

            val broadcastAddr = InetAddress.getByName("255.255.255.255")
            val packet = DatagramPacket(data, data.size, broadcastAddr, DISCOVERY_PORT)
            DatagramSocket().use { s ->
                s.broadcast = true
                s.send(packet)
            }
        } catch (e: Exception) {
            // Ignore broadcast failure on transient network changes
        }
    }

    fun stopListening() {
        isListening = false
        listenerJob?.cancel()
        listenerJob = null
        try {
            socket?.close()
        } catch (e: Exception) {
            // Ignore
        }
        socket = null
        releaseMulticastLock()
        Log.d(TAG, "Discovery listener stopped")
    }

    private fun acquireMulticastLock() {
        try {
            val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            multicastLock = wifi?.createMulticastLock("ConnectToPhoneMulticast")?.apply {
                setReferenceCounted(true)
                acquire()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to acquire multicast lock: ${e.message}")
        }
    }

    private fun releaseMulticastLock() {
        try {
            if (multicastLock?.isHeld == true) {
                multicastLock?.release()
            }
        } catch (e: Exception) {
            // Ignore
        }
        multicastLock = null
    }
}
