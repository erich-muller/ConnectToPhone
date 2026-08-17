package com.connecttophone.net

import com.google.gson.annotations.SerializedName

object MessageType {
    const val DISCOVERY_BEACON = "DISCOVERY_BEACON"
    const val DISCOVERY_SEARCH = "DISCOVERY_SEARCH"
    const val PAIR_REQUEST = "PAIR_REQUEST"
    const val PAIR_RESPONSE = "PAIR_RESPONSE"
    const val AUTH_CONNECT = "AUTH_CONNECT"
    const val AUTH_RESPONSE = "AUTH_RESPONSE"

    const val PING = "PING"
    const val PONG = "PONG"
    const val DEVICE_STATUS = "DEVICE_STATUS"

    const val CLIPBOARD_TEXT = "CLIPBOARD_TEXT"
    const val CLIPBOARD_IMAGE = "CLIPBOARD_IMAGE"

    const val STREAM_START_REQ = "STREAM_START_REQ"
    const val STREAM_START_RESP = "STREAM_START_RESP"
    const val STREAM_STOP = "STREAM_STOP"
    const val STREAM_FRAME = "STREAM_FRAME"

    const val INPUT_TOUCH = "INPUT_TOUCH"
    const val INPUT_KEY = "INPUT_KEY"
}

data class BaseMessage<T>(
    @SerializedName("type") val type: String,
    @SerializedName("version") val version: String = "1.0",
    @SerializedName("timestamp") val timestamp: Long = System.currentTimeMillis(),
    @SerializedName("source_id") val sourceId: String,
    @SerializedName("payload") val payload: T
)

data class PairRequestPayload(
    @SerializedName("pin") val pin: String,
    @SerializedName("device_name") val deviceName: String,
    @SerializedName("model") val model: String
)

data class PairResponsePayload(
    @SerializedName("status") val status: String,
    @SerializedName("auth_token") val authToken: String?,
    @SerializedName("device_name") val deviceName: String?,
    @SerializedName("reason") val reason: String?
)

data class AuthConnectPayload(
    @SerializedName("auth_token") val authToken: String,
    @SerializedName("device_name") val deviceName: String,
    @SerializedName("model") val model: String,
    @SerializedName("android_version") val androidVersion: String
)

data class AuthResponsePayload(
    @SerializedName("status") val status: String,
    @SerializedName("device_name") val deviceName: String?,
    @SerializedName("reason") val reason: String?
)

data class DeviceStatusPayload(
    @SerializedName("battery_level") val batteryLevel: Int,
    @SerializedName("is_charging") val isCharging: Boolean,
    @SerializedName("wifi_ssid") val wifiSsid: String
)

data class ClipboardTextPayload(
    @SerializedName("content") val content: String
)

data class ClipboardImagePayload(
    @SerializedName("format") val format: String = "png",
    @SerializedName("data") val data: String // Base64
)

data class StreamStartReqPayload(
    @SerializedName("width") val width: Int = 720,
    @SerializedName("height") val height: Int = 1280,
    @SerializedName("fps") val fps: Int = 30,
    @SerializedName("bitrate") val bitrate: Int = 3000000
)

data class StreamFramePayload(
    @SerializedName("format") val format: String = "jpeg",
    @SerializedName("data") val data: String, // Base64
    @SerializedName("width") val width: Int,
    @SerializedName("height") val height: Int
)

data class InputTouchPayload(
    @SerializedName("action") val action: String, // DOWN, MOVE, UP
    @SerializedName("x") val x: Float, // Normalized 0.0 - 1.0
    @SerializedName("y") val y: Float
)

data class InputKeyPayload(
    @SerializedName("key") val key: String
)
