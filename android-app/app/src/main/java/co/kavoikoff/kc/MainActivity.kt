package co.kavoikoff.kc

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { KCApp() }
    }
}

private val Bg = Color(0xFF07090D)
private val Card = Color(0xFF171A20)
private val Text = Color(0xFFF4F6F8)
private val Muted = Color(0xFF9299A5)
private val VpnGreen = Color(0xFF29D463)
private val ProxyBlue = Color(0xFF3EA6FF)
private val Warn = Color(0xFFFFB02E)
private val Error = Color(0xFFFF4D57)

@Composable
fun KCApp() {
    var tab by remember { mutableStateOf(0) }
    MaterialTheme(colorScheme = darkColorScheme(background = Bg, surface = Card)) {
        Scaffold(
            containerColor = Bg,
            bottomBar = {
                NavigationBar(containerColor = Color(0xFF0B0E13)) {
                    listOf("VPN", "Чаты", "Профиль").forEachIndexed { index, label ->
                        NavigationBarItem(
                            selected = tab == index,
                            onClick = { tab = index },
                            icon = { Text(if (index == 0) "●" else if (index == 1) "✦" else "◦", color = if (tab == index) ProxyBlue else Muted) },
                            label = { Text(label) }
                        )
                    }
                }
            }
        ) { padding ->
            Box(Modifier.padding(padding).fillMaxSize()) {
                when (tab) {
                    0 -> NetworkHome()
                    1 -> CenterMessage("Чаты", "Здесь будет K&C GPT и история диалогов")
                    else -> CenterMessage("Профиль", "Аккаунт, подписка, устройства и настройки")
                }
            }
        }
    }
}

@Composable
private fun NetworkHome() {
    var mode by remember { mutableStateOf("Proxy") }
    var source by remember { mutableStateOf("VK") }
    var connected by remember { mutableStateOf(true) }
    val accent = if (mode == "VPN") VpnGreen else ProxyBlue

    Column(
        modifier = Modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("K&C", color = Text, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            Text("⚙", color = Muted, fontSize = 24.sp)
        }

        Segmented(listOf("VPN", "Proxy"), mode, accent) { mode = it }

        if (mode == "Proxy") {
            Segmented(listOf("VK", "MAX", "AUTO"), source, ProxyBlue) { source = it }
        }

        CardBox {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusLamp(if (connected) accent else Error)
                Spacer(Modifier.width(10.dp))
                Column {
                    Text((if (connected) mode + " подключён" else mode + " отключён"), color = Text, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text((if (mode == "Proxy") "Через " + source + " · Server1" else "Server1"), color = Muted, fontSize = 13.sp)
                }
                Spacer(Modifier.weight(1f))
                Text("39 ms", color = Text, fontWeight = FontWeight.SemiBold)
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Metric("↑ TX", "1014.3 MB", "40.2 KB/s", accent, Modifier.weight(1f))
            Metric("↓ RX", "4.6 GB", "2.4 KB/s", accent, Modifier.weight(1f))
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SmallMetric("TURN RTT", "39 ms", VpnGreen, Modifier.weight(1f))
            SmallMetric("DTLS HS", "612 ms", Warn, Modifier.weight(1f))
            SmallMetric("Internet", "259 ms", VpnGreen, Modifier.weight(1f))
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SmallMetric("Conns", "30/231", VpnGreen, Modifier.weight(1f))
            SmallMetric("Reconnects", "0", VpnGreen, Modifier.weight(1f))
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SmallMetric("Uptime", "46:30:46", VpnGreen, Modifier.weight(1f))
            SmallMetric("Pool", "6/6/6/6", VpnGreen, Modifier.weight(1f))
        }

        Button(
            onClick = { connected = !connected },
            modifier = Modifier.fillMaxWidth().height(52.dp),
            colors = ButtonDefaults.buttonColors(containerColor = if (connected) Error else accent),
            shape = RoundedCornerShape(16.dp)
        ) {
            Text(if (connected) "Отключить" else "Подключить", fontWeight = FontWeight.Bold)
        }

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround) {
            Text("Logs", color = ProxyBlue)
            Text("Speed test", color = ProxyBlue)
            Text("Settings", color = ProxyBlue)
        }
    }
}

@Composable
private fun Segmented(items: List<String>, selected: String, accent: Color, onSelect: (String) -> Unit) {
    Row(
        Modifier.fillMaxWidth().background(Card, RoundedCornerShape(16.dp)).padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        items.forEach { item ->
            Box(
                Modifier.weight(1f)
                    .background(if (item == selected) accent.copy(alpha = 0.22f) else Color.Transparent, RoundedCornerShape(12.dp))
                    .clickable { onSelect(item) }
                    .padding(vertical = 11.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(item, color = if (item == selected) accent else Muted, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun CardBox(content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth().background(Card, RoundedCornerShape(22.dp)).padding(16.dp), content = content)
}

@Composable
private fun Metric(label: String, value: String, detail: String, accent: Color, modifier: Modifier = Modifier) {
    Column(modifier.background(Card, RoundedCornerShape(18.dp)).padding(14.dp)) {
        Text(label, color = Muted, fontSize = 12.sp)
        Text(value, color = Text, fontSize = 24.sp, fontWeight = FontWeight.Medium)
        Text(detail, color = accent, fontSize = 12.sp)
    }
}

@Composable
private fun SmallMetric(label: String, value: String, lamp: Color, modifier: Modifier = Modifier) {
    Row(modifier.background(Card, RoundedCornerShape(14.dp)).padding(horizontal = 11.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(label, color = Muted, fontSize = 10.sp)
            Text(value, color = Text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        }
        StatusLamp(lamp, 7)
    }
}

@Composable
private fun StatusLamp(color: Color, size: Int = 12) {
    Box(Modifier.size(size.dp).background(color, RoundedCornerShape(50)))
}

@Composable
private fun CenterMessage(title: String, subtitle: String) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(title, color = Text, fontSize = 28.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(subtitle, color = Muted)
    }
}
