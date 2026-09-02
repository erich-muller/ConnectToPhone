package com.connecttophone

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.connecttophone.databinding.ActivityMainBinding
import com.connecttophone.service.CompanionService
import com.connecttophone.service.ScreenCaptureService
import com.connecttophone.util.PreferencesManager
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: PreferencesManager
    private val gson = Gson()

    private val qrScanLauncher = registerForActivityResult(ScanContract()) { result ->
        if (result.contents != null) {
            handleQrCodeResult(result.contents)
        }
    }

    private val screenCaptureLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            CompanionService.instance?.lanClient?.sendStreamStartResponse("accepted")
            startScreenCaptureService(result.resultCode, result.data!!)
        } else {
            CompanionService.instance?.lanClient?.sendStreamStartResponse("rejected")
            Toast.makeText(this, "Permissão de espelhamento negada", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = PreferencesManager(this)

        ensureCompanionServiceRunning()
        setupUI()
        setupCompanionListeners()
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        updateDeviceStatus()
        setupCompanionListeners()
    }

    private fun setupCompanionListeners() {
        CompanionService.onPairingStateChangedListener = { success ->
            runOnUiThread {
                updateDeviceStatus()
                if (success) {
                    binding.etPin.setText("")
                    Toast.makeText(this, "✅ Pareamento concluído com sucesso!", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this, "❌ PIN incorreto ou pareamento rejeitado", Toast.LENGTH_SHORT).show()
                }
            }
        }
        CompanionService.onConnectionStateChangedListener = { _, _ ->
            runOnUiThread {
                updateDeviceStatus()
            }
        }
        CompanionService.onPcDiscoveredListener = { _, pcName, ip, _ ->
            runOnUiThread {
                if (!prefs.isPaired) {
                    binding.tvStatus.text = "🟡 PC encontrado ($pcName em $ip). Digite o PIN ou escaneie o QR."
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent?.getBooleanExtra("ACTION_START_SCREEN_CAPTURE", false) == true) {
            requestScreenCapture()
        }
    }

    private fun ensureCompanionServiceRunning() {
        val serviceIntent = Intent(this, CompanionService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }
    }

    private fun setupUI() {
        updateDeviceStatus()

        // QR Code button
        binding.btnScanQr.setOnClickListener {
            val options = ScanOptions().apply {
                setPrompt("Aponte para o QR Code exibido no Linux")
                setBeepEnabled(true)
                setOrientationLocked(false)
            }
            qrScanLauncher.launch(options)
        }

        // PIN Button
        binding.btnPairPin.setOnClickListener {
            val pin = binding.etPin.text?.toString()?.trim() ?: ""
            if (pin.length == 6) {
                initiatePairingWithPin(pin)
            } else {
                Toast.makeText(this, "Digite um PIN válido de 6 dígitos", Toast.LENGTH_SHORT).show()
            }
        }

        // Toggles
        binding.switchClipboard.isChecked = prefs.syncClipboard
        binding.switchClipboard.setOnCheckedChangeListener { _, isChecked ->
            prefs.syncClipboard = isChecked
        }

        binding.switchImages.isChecked = prefs.syncImages
        binding.switchImages.setOnCheckedChangeListener { _, isChecked ->
            prefs.syncImages = isChecked
        }

        binding.switchAutoConnect.isChecked = prefs.autoConnect
        binding.switchAutoConnect.setOnCheckedChangeListener { _, isChecked ->
            prefs.autoConnect = isChecked
        }

        // Accessibility Settings Button
        binding.btnAccessibility.setOnClickListener {
            try {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            } catch (e: Exception) {
                Toast.makeText(this, "Não foi possível abrir configurações", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun updateDeviceStatus() {
        if (prefs.isPaired) {
            binding.tvPcName.text = prefs.pairedPcName ?: "Linux PC"
            binding.tvStatus.text = "🟢 Conectado ao PC na rede local"
            binding.tvStatus.setTextColor(getColor(R.color.success))
        } else {
            val discovered = CompanionService.lastDiscoveredPcName
            if (!discovered.isNullOrEmpty()) {
                binding.tvPcName.text = discovered
                binding.tvStatus.text = "🟡 PC localizado na rede (${CompanionService.lastDiscoveredPcIp}). Pronto para parear."
            } else {
                binding.tvPcName.text = "ConnectToPhone"
                binding.tvStatus.text = "🟡 Aguardando pareamento na rede local"
            }
            binding.tvStatus.setTextColor(getColor(R.color.warning))
        }
    }

    private fun handleQrCodeResult(qrContent: String) {
        try {
            val data = gson.fromJson(qrContent, JsonObject::class.java)
            val ip = data.get("ip")?.asString
            val port = data.get("port")?.asInt ?: 42100
            val pin = data.get("pin")?.asString
            val pcName = data.get("name")?.asString ?: "Linux PC"
            val pcId = data.get("id")?.asString ?: ""

            if (!ip.isNullOrEmpty() && !pin.isNullOrEmpty()) {
                prefs.pairedPcIp = ip
                prefs.pairedPcPort = port
                prefs.pairedPcName = pcName
                prefs.pairedPcId = pcId

                Toast.makeText(this, "Conectando ao PC ($ip:$port)...", Toast.LENGTH_SHORT).show()
                CompanionService.instance?.initiatePairing(ip, port, pin)
                updateDeviceStatus()
            } else {
                Toast.makeText(this, "QR Code inválido", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            Toast.makeText(this, "Erro ao processar QR Code: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun initiatePairingWithPin(pin: String) {
        val ip = prefs.pairedPcIp ?: CompanionService.lastDiscoveredPcIp
        val port = prefs.pairedPcPort.takeIf { it > 0 } ?: CompanionService.lastDiscoveredPcPort
        if (!ip.isNullOrEmpty()) {
            Toast.makeText(this, "Conectando ao PC ($ip:$port) com PIN...", Toast.LENGTH_SHORT).show()
            CompanionService.instance?.initiatePairing(ip, port, pin)
        } else {
            Toast.makeText(this, "Escaneie o QR Code no Linux ou aguarde a detecção automática", Toast.LENGTH_LONG).show()
        }
    }

    fun requestScreenCapture() {
        val mediaProjectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        screenCaptureLauncher.launch(mediaProjectionManager.createScreenCaptureIntent())
    }

    private fun startScreenCaptureService(resultCode: Int, data: Intent) {
        val intent = ScreenCaptureService.getStartIntent(this, resultCode, data)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        Toast.makeText(this, "Espelhamento de tela iniciado", Toast.LENGTH_SHORT).show()
    }
}
