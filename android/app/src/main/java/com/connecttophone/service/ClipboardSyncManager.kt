package com.connecttophone.service

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.connecttophone.util.ImageUtils
import java.security.MessageDigest

class ClipboardSyncManager(
    private val context: Context,
    private val onLocalTextCopied: (String) -> Unit,
    private val onLocalImageCopied: (String) -> Unit
) {
    private val TAG = "ClipboardSync"
    private val clipboardManager = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    private val mainHandler = Handler(Looper.getMainLooper())

    private var lastContentHash: String = ""
    private var isApplyingRemoteChange = false
    private var isListening = false

    private val clipListener = ClipboardManager.OnPrimaryClipChangedListener {
        onClipboardChanged()
    }

    fun start() {
        if (isListening) return
        isListening = true
        clipboardManager.addPrimaryClipChangedListener(clipListener)
        Log.d(TAG, "Clipboard listener started")
    }

    fun stop() {
        isListening = false
        clipboardManager.removePrimaryClipChangedListener(clipListener)
        Log.d(TAG, "Clipboard listener stopped")
    }

    private fun computeHash(str: String): String {
        val md = MessageDigest.getInstance("SHA-256")
        val bytes = md.digest(str.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }
    }

    fun onClipboardChanged() {
        if (isApplyingRemoteChange) {
            isApplyingRemoteChange = false
            return
        }

        try {
            val clipData = clipboardManager.primaryClip ?: return
            if (clipData.itemCount <= 0) return

            val item = clipData.getItemAt(0)
            val description = clipData.description

            // Check for image uri
            if (description.hasMimeType("image/*") || item.uri != null) {
                val uri = item.uri
                if (uri != null) {
                    val base64 = ImageUtils.uriToBase64(context, uri)
                    if (!base64.isNullOrEmpty()) {
                        val hash = computeHash(base64)
                        if (hash != lastContentHash) {
                            lastContentHash = hash
                            Log.d(TAG, "Local image copied, sending to PC")
                            onLocalImageCopied(base64)
                            return
                        }
                    }
                }
            }

            // Check for text
            val text = item.text?.toString()
            if (!text.isNullOrEmpty()) {
                val hash = computeHash(text)
                if (hash != lastContentHash) {
                    lastContentHash = hash
                    Log.d(TAG, "Local text copied: ${text.take(30)}..., sending to PC")
                    onLocalTextCopied(text)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error checking clipboard: ${e.message}")
        }
    }

    fun applyRemoteText(text: String) {
        if (text.isEmpty()) return
        val hash = computeHash(text)
        if (hash == lastContentHash) return

        lastContentHash = hash
        isApplyingRemoteChange = true

        mainHandler.post {
            try {
                val clip = ClipData.newPlainText("ConnectToPhone", text)
                clipboardManager.setPrimaryClip(clip)
                Log.d(TAG, "Applied remote text to Android clipboard: ${text.take(30)}...")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to apply remote text: ${e.message}")
            }
        }
    }

    fun applyRemoteImage(base64Data: String) {
        if (base64Data.isEmpty()) return
        val hash = computeHash(base64Data)
        if (hash == lastContentHash) return

        lastContentHash = hash
        isApplyingRemoteChange = true

        mainHandler.post {
            try {
                val uri = ImageUtils.base64ToUri(context, base64Data)
                if (uri != null) {
                    val clip = ClipData.newUri(context.contentResolver, "ConnectToPhone Image", uri)
                    clipboardManager.setPrimaryClip(clip)
                    Log.d(TAG, "Applied remote image to Android clipboard via FileProvider")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to apply remote image: ${e.message}")
            }
        }
    }
}
