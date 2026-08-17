package com.connecttophone.service

import android.app.Activity
import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.graphics.Rect
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.util.Base64
import android.util.DisplayMetrics
import android.util.Log
import android.view.Display
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import com.connecttophone.ConnectApp
import com.connecttophone.MainActivity
import com.connecttophone.R
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer

class ScreenCaptureService : Service() {

    companion object {
        private const val TAG = "ScreenCaptureService"
        private const val NOTIFICATION_ID = 2002

        const val EXTRA_RESULT_CODE = "extra_result_code"
        const val EXTRA_DATA = "extra_data"

        var isRunning = false
            private set

        fun getStartIntent(context: Context, resultCode: Int, data: Intent): Intent {
            return Intent(context, ScreenCaptureService::class.java).apply {
                putExtra(EXTRA_RESULT_CODE, resultCode)
                putExtra(EXTRA_DATA, data)
            }
        }
    }

    private var mediaProjectionManager: MediaProjectionManager? = null
    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var handlerThread: HandlerThread? = null
    private var backgroundHandler: Handler? = null

    private var displayManager: DisplayManager? = null
    private var displayListener: DisplayManager.DisplayListener? = null

    private var screenWidth = 720
    private var screenHeight = 1280
    private var screenDensity = 320

    private var lastFrameTime = 0L
    private val frameIntervalMs = 33L // ~30 FPS
    private var cleanBuffer: ByteBuffer? = null
    private var reusableBitmap: Bitmap? = null
    private val outStream = ByteArrayOutputStream()

    override fun onCreate() {
        super.onCreate()
        mediaProjectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        displayManager = getSystemService(Context.DISPLAY_SERVICE) as DisplayManager
        isRunning = true
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED) ?: Activity.RESULT_CANCELED
        val resultData = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent?.getParcelableExtra(EXTRA_DATA, Intent::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent?.getParcelableExtra(EXTRA_DATA)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                createNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            )
        } else {
            startForeground(NOTIFICATION_ID, createNotification())
        }

        if (resultCode == Activity.RESULT_OK && resultData != null) {
            startScreenCapture(resultCode, resultData)
        } else {
            Log.e(TAG, "Invalid result code ($resultCode) or null resultData")
            stopSelf()
        }

        return START_NOT_STICKY
    }

    private fun calculateDimensions(): Boolean {
        val windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val bounds = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            windowManager.currentWindowMetrics.bounds
        } else {
            val dm = DisplayMetrics()
            @Suppress("DEPRECATION")
            windowManager.defaultDisplay.getRealMetrics(dm)
            Rect(0, 0, dm.widthPixels, dm.heightPixels)
        }

        val realW = bounds.width().coerceAtLeast(480)
        val realH = bounds.height().coerceAtLeast(640)
        screenDensity = resources.displayMetrics.densityDpi

        val maxDimension = 1280
        val scale = if (maxOf(realW, realH) > maxDimension) {
            maxDimension.toFloat() / maxOf(realW, realH)
        } else 1.0f

        val newW = (((realW * scale).toInt() / 8) * 8).coerceAtLeast(320)
        val newH = (((realH * scale).toInt() / 8) * 8).coerceAtLeast(480)

        val changed = (newW != screenWidth || newH != screenHeight)
        screenWidth = newW
        screenHeight = newH

        Log.d(TAG, "Screen metrics: ${realW}x${realH} -> Capture resolution: ${screenWidth}x${screenHeight} (density=$screenDensity, changed=$changed)")
        return changed
    }

    private fun startScreenCapture(resultCode: Int, data: Intent) {
        try {
            calculateDimensions()

            mediaProjection = mediaProjectionManager?.getMediaProjection(resultCode, data)
            if (mediaProjection == null) {
                Log.e(TAG, "mediaProjection is null")
                stopSelf()
                return
            }

            mediaProjection?.registerCallback(object : MediaProjection.Callback() {
                override fun onStop() {
                    Log.d(TAG, "MediaProjection session stopped by system")
                    stopSelf()
                }
            }, null)

            handlerThread = HandlerThread("ScreenCaptureThread").apply { start() }
            backgroundHandler = Handler(handlerThread!!.looper)

            setupImageReaderAndBuffers()

            virtualDisplay = mediaProjection?.createVirtualDisplay(
                "ConnectScreenMirror",
                screenWidth,
                screenHeight,
                screenDensity,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                imageReader?.surface,
                null,
                backgroundHandler
            )

            setupOrientationListener()
            Log.d(TAG, "Screen projection active: ${screenWidth}x${screenHeight}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize screen projection: ${e.message}", e)
            stopSelf()
        }
    }

    private fun setupImageReaderAndBuffers() {
        cleanBuffer = ByteBuffer.allocateDirect(screenWidth * screenHeight * 4)
        reusableBitmap?.recycle()
        reusableBitmap = Bitmap.createBitmap(screenWidth, screenHeight, Bitmap.Config.ARGB_8888)

        imageReader?.close()
        imageReader = ImageReader.newInstance(screenWidth, screenHeight, PixelFormat.RGBA_8888, 3)
        imageReader?.setOnImageAvailableListener({ reader ->
            processAvailableFrame(reader)
        }, backgroundHandler)
    }

    private fun setupOrientationListener() {
        displayListener = object : DisplayManager.DisplayListener {
            override fun onDisplayAdded(displayId: Int) {}
            override fun onDisplayRemoved(displayId: Int) {}
            override fun onDisplayChanged(displayId: Int) {
                if (displayId == Display.DEFAULT_DISPLAY) {
                    onOrientationChanged()
                }
            }
        }
        displayManager?.registerDisplayListener(displayListener, backgroundHandler)
    }

    private fun onOrientationChanged() {
        backgroundHandler?.post {
            val changed = calculateDimensions()
            if (changed && isRunning && virtualDisplay != null) {
                Log.d(TAG, "Orientation change detected! Resizing VirtualDisplay to ${screenWidth}x${screenHeight}")
                setupImageReaderAndBuffers()
                virtualDisplay?.resize(screenWidth, screenHeight, screenDensity)
                virtualDisplay?.surface = imageReader?.surface
            }
        }
    }

    private fun processAvailableFrame(reader: ImageReader) {
        if (!isRunning) return
        val image = reader.acquireLatestImage() ?: return

        try {
            val now = System.currentTimeMillis()
            if (now - lastFrameTime < frameIntervalMs) {
                image.close()
                return
            }
            lastFrameTime = now

            val plane = image.planes[0]
            val buffer = plane.buffer
            val rowStride = plane.rowStride
            val pixelStride = plane.pixelStride
            val rowBytes = screenWidth * pixelStride

            val directBuf = cleanBuffer ?: return
            val bmp = reusableBitmap ?: return
            directBuf.clear()

            val bufferCapacity = buffer.capacity()
            for (y in 0 until screenHeight) {
                val rowStart = y * rowStride
                if (rowStart >= bufferCapacity) break
                buffer.position(rowStart)
                val oldLimit = buffer.limit()
                val targetLimit = minOf(rowStart + rowBytes, bufferCapacity)
                buffer.limit(targetLimit)
                directBuf.put(buffer)
                buffer.limit(oldLimit)
            }

            directBuf.rewind()
            bmp.copyPixelsFromBuffer(directBuf)

            outStream.reset()
            bmp.compress(Bitmap.CompressFormat.JPEG, 75, outStream)
            val jpegBytes = outStream.toByteArray()
            val base64Frame = Base64.encodeToString(jpegBytes, Base64.NO_WRAP)

            CompanionService.sendScreenFrame(base64Frame, screenWidth, screenHeight)

        } catch (e: Exception) {
            Log.e(TAG, "Error processing frame: ${e.message}")
        } finally {
            image.close()
        }
    }

    private fun createNotification(): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, ConnectApp.CHANNEL_ID_SCREEN)
            .setContentTitle("Espelhamento de Tela Ativo")
            .setContentText("Transmitindo tela para o Linux PC")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false

        try {
            displayListener?.let { displayManager?.unregisterDisplayListener(it) }
            displayListener = null

            virtualDisplay?.release()
            virtualDisplay = null

            imageReader?.close()
            imageReader = null

            mediaProjection?.stop()
            mediaProjection = null

            handlerThread?.quitSafely()
            handlerThread = null

            reusableBitmap?.recycle()
            reusableBitmap = null
            cleanBuffer = null
        } catch (e: Exception) {
            Log.e(TAG, "Error during cleanup: ${e.message}")
        }
        Log.d(TAG, "ScreenCaptureService destroyed")
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
