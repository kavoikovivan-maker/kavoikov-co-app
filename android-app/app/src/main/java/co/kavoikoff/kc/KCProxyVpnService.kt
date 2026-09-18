package co.kavoikoff.kc

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import androidx.core.app.NotificationCompat

class KCProxyVpnService : VpnService() {
    companion object {
        const val ACTION_CONNECT = "co.kavoikoff.kc.CONNECT"
        const val ACTION_DISCONNECT = "co.kavoikoff.kc.DISCONNECT"
        const val CHANNEL_ID = "kc_vpn"
        const val NOTIFICATION_ID = 1001
    }

    private var tun: ParcelFileDescriptor? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_DISCONNECT -> stopTunnel()
            else -> startTunnel()
        }
        return START_STICKY
    }

    private fun startTunnel() {
        if (tun != null) return

        val configureIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle("K&C")
            .setContentText("VPN/Proxy активен")
            .setOngoing(true)
            .setContentIntent(configureIntent)
            .build()

        startForeground(NOTIFICATION_ID, notification)

        tun = Builder()
            .setSession("K&C")
            .setMtu(1300)
            .addAddress("10.88.0.2", 24)
            .addRoute("0.0.0.0", 0)
            .addDnsServer("1.1.1.1")
            .establish()

        // Следующий слой: TUN fd -> общий Go/TURN/WireGuard движок.
        // Сам fd уже создаётся реальным Android VpnService.
    }

    private fun stopTunnel() {
        tun?.close()
        tun = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        stopTunnel()
        super.onDestroy()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "K&C VPN",
                    NotificationManager.IMPORTANCE_LOW
                )
            )
        }
    }
}
