package com.connecttophone.util

import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import java.util.UUID

class PreferencesManager(context: Context) {

    private val prefs: SharedPreferences = context.getSharedPreferences("connect_prefs", Context.MODE_PRIVATE)

    companion object {
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_DEVICE_NAME = "device_name"
        private const val KEY_PAIRED_PC_ID = "paired_pc_id"
        private const val KEY_PAIRED_PC_NAME = "paired_pc_name"
        private const val KEY_PAIRED_PC_IP = "paired_pc_ip"
        private const val KEY_PAIRED_PC_PORT = "paired_pc_port"
        private const val KEY_AUTH_TOKEN = "auth_token"
        private const val KEY_AUTO_CONNECT = "auto_connect"
        private const val KEY_SYNC_CLIPBOARD = "sync_clipboard"
        private const val KEY_SYNC_IMAGES = "sync_images"
    }

    var deviceId: String
        get() {
            var id = prefs.getString(KEY_DEVICE_ID, null)
            if (id == null) {
                id = UUID.randomUUID().toString()
                prefs.edit().putString(KEY_DEVICE_ID, id).apply()
            }
            return id
        }
        set(value) = prefs.edit().putString(KEY_DEVICE_ID, value).apply()

    var deviceName: String
        get() = prefs.getString(KEY_DEVICE_NAME, null) ?: "${Build.MANUFACTURER} ${Build.MODEL}"
        set(value) = prefs.edit().putString(KEY_DEVICE_NAME, value).apply()

    var pairedPcId: String?
        get() = prefs.getString(KEY_PAIRED_PC_ID, null)
        set(value) = prefs.edit().putString(KEY_PAIRED_PC_ID, value).apply()

    var pairedPcName: String?
        get() = prefs.getString(KEY_PAIRED_PC_NAME, null)
        set(value) = prefs.edit().putString(KEY_PAIRED_PC_NAME, value).apply()

    var pairedPcIp: String?
        get() = prefs.getString(KEY_PAIRED_PC_IP, null)
        set(value) = prefs.edit().putString(KEY_PAIRED_PC_IP, value).apply()

    var pairedPcPort: Int
        get() = prefs.getInt(KEY_PAIRED_PC_PORT, 42100)
        set(value) = prefs.edit().putInt(KEY_PAIRED_PC_PORT, value).apply()

    var authToken: String?
        get() = prefs.getString(KEY_AUTH_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_AUTH_TOKEN, value).apply()

    val isPaired: Boolean
        get() = !pairedPcId.isNullOrEmpty() && !authToken.isNullOrEmpty() && !pairedPcIp.isNullOrEmpty()

    var autoConnect: Boolean
        get() = prefs.getBoolean(KEY_AUTO_CONNECT, true)
        set(value) = prefs.edit().putBoolean(KEY_AUTO_CONNECT, value).apply()

    var syncClipboard: Boolean
        get() = prefs.getBoolean(KEY_SYNC_CLIPBOARD, true)
        set(value) = prefs.edit().putBoolean(KEY_SYNC_CLIPBOARD, value).apply()

    var syncImages: Boolean
        get() = prefs.getBoolean(KEY_SYNC_IMAGES, true)
        set(value) = prefs.edit().putBoolean(KEY_SYNC_IMAGES, value).apply()

    fun savePairing(pcId: String, pcName: String, pcIp: String, pcPort: Int, token: String) {
        prefs.edit()
            .putString(KEY_PAIRED_PC_ID, pcId)
            .putString(KEY_PAIRED_PC_NAME, pcName)
            .putString(KEY_PAIRED_PC_IP, pcIp)
            .putInt(KEY_PAIRED_PC_PORT, pcPort)
            .putString(KEY_AUTH_TOKEN, token)
            .apply()
    }

    fun clearPairing() {
        prefs.edit()
            .remove(KEY_PAIRED_PC_ID)
            .remove(KEY_PAIRED_PC_NAME)
            .remove(KEY_PAIRED_PC_IP)
            .remove(KEY_AUTH_TOKEN)
            .apply()
    }
}
