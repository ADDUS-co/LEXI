package com.ada.lexi

import java.net.URI
import java.util.Locale

internal object SitePolicy {
    const val HOME_URL = "https://lexi-m388.onrender.com/#home"
    private const val HOST = "lexi-m388.onrender.com"

    fun isTrusted(url: String?): Boolean = parse(url)?.let {
        it.scheme.equals("https", ignoreCase = true) &&
            it.host.equals(HOST, ignoreCase = true) &&
            it.rawUserInfo == null && it.port in listOf(-1, 443)
    } ?: false

    fun canOpenExternally(url: String?): Boolean = parse(url)?.let {
        when (it.scheme?.lowercase(Locale.ROOT)) {
            "http", "https" -> !it.host.isNullOrEmpty() && it.rawUserInfo == null
            "mailto", "tel" -> !it.schemeSpecificPart.isNullOrBlank()
            else -> false
        }
    } ?: false

    private fun parse(url: String?): URI? = try {
        url?.takeIf { it.length <= 8192 }?.let(::URI)
    } catch (_: Exception) {
        null
    }
}
