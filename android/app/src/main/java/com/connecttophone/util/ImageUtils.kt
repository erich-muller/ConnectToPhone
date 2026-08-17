package com.connecttophone.util

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Base64
import androidx.core.content.FileProvider
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream

object ImageUtils {

    fun uriToBase64(context: Context, uri: Uri, quality: Int = 90): String? {
        return try {
            val inputStream: InputStream? = context.contentResolver.openInputStream(uri)
            val bitmap = BitmapFactory.decodeStream(inputStream)
            inputStream?.close()
            bitmapToBase64(bitmap, quality)
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    fun bitmapToBase64(bitmap: Bitmap?, quality: Int = 90): String? {
        if (bitmap == null) return null
        val outputStream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.PNG, quality, outputStream)
        val byteArray = outputStream.toByteArray()
        return Base64.encodeToString(byteArray, Base64.NO_WRAP)
    }

    fun base64ToUri(context: Context, base64Str: String): Uri? {
        return try {
            val decodedBytes = Base64.decode(base64Str, Base64.DEFAULT)
            val cacheDir = File(context.cacheDir, "clip_images")
            if (!cacheDir.exists()) {
                cacheDir.mkdirs()
            }
            val imageFile = File(cacheDir, "clip_${System.currentTimeMillis()}.png")
            val fos = FileOutputStream(imageFile)
            fos.write(decodedBytes)
            fos.flush()
            fos.close()

            FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                imageFile
            )
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }
}
