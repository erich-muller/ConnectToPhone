package com.connecttophone.service

import android.content.Context
import android.database.ContentObserver
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.util.Log
import com.connecttophone.util.ImageUtils

class ScreenshotObserver(
    private val context: Context,
    private val onScreenshotDetected: (base64Image: String) -> Unit
) : ContentObserver(Handler(Looper.getMainLooper())) {

    private val TAG = "ScreenshotObserver"
    private var lastProcessedUri: Uri? = null
    private var lastProcessedTime: Long = 0

    override fun onChange(selfChange: Boolean, uri: Uri?) {
        super.onChange(selfChange, uri)
        val targetUri = uri ?: MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        processLatestImage(targetUri)
    }

    private fun processLatestImage(triggerUri: Uri) {
        try {
            val projection = mutableListOf(
                MediaStore.Images.Media._ID,
                MediaStore.Images.Media.DISPLAY_NAME,
                MediaStore.Images.Media.DATE_ADDED
            )
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                projection.add(MediaStore.Images.Media.RELATIVE_PATH)
            }

            val sortOrder = "${MediaStore.Images.Media.DATE_ADDED} DESC"

            val queryUri = if (triggerUri == MediaStore.Images.Media.EXTERNAL_CONTENT_URI) {
                triggerUri
            } else {
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            }

            val cursor = context.contentResolver.query(
                queryUri,
                projection.toTypedArray(),
                null,
                null,
                sortOrder
            )

            cursor?.use {
                if (it.moveToFirst()) {
                    val idColumn = it.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
                    val nameColumn = it.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
                    val dateAddedColumn = it.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_ADDED)

                    val id = it.getLong(idColumn)
                    val name = it.getString(nameColumn) ?: ""
                    val dateAddedSec = it.getLong(dateAddedColumn)

                    var relativePath = ""
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        val pathCol = it.getColumnIndex(MediaStore.Images.Media.RELATIVE_PATH)
                        if (pathCol != -1) {
                            relativePath = it.getString(pathCol) ?: ""
                        }
                    }

                    val contentUri = Uri.withAppendedPath(
                        MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                        id.toString()
                    )

                    val lowerName = name.lowercase()
                    val lowerPath = relativePath.lowercase()
                    val isScreenshot = lowerName.contains("screenshot") ||
                            lowerName.contains("captura") ||
                            lowerName.contains("screen") ||
                            lowerName.contains("print") ||
                            lowerPath.contains("screenshot") ||
                            lowerPath.contains("captura")

                    val nowSec = System.currentTimeMillis() / 1000
                    val isRecent = (nowSec - dateAddedSec) in -5..30

                    if (isRecent && isScreenshot) {
                        val now = System.currentTimeMillis()
                        if (contentUri != lastProcessedUri || (now - lastProcessedTime) > 3000) {
                            lastProcessedUri = contentUri
                            lastProcessedTime = now
                            Log.d(TAG, "Screenshot detected: $name ($contentUri)")

                            val base64 = ImageUtils.uriToBase64(context, contentUri)
                            if (!base64.isNullOrEmpty()) {
                                onScreenshotDetected(base64)
                            }
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error checking for screenshot: ${e.message}")
        }
    }
}
