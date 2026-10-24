package com.ada.lexi

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SitePolicyTest {
    @Test fun allowsOnlyTheOwnedHttpsOrigin() {
        listOf(
            SitePolicy.HOME_URL,
            "https://lexi-m388.onrender.com/api/account/session",
            "https://LEXI-M388.ONRENDER.COM:443/#saved",
        ).forEach { assertTrue(it, SitePolicy.isTrusted(it)) }
        listOf(
            "http://lexi-m388.onrender.com/",
            "https://lexi-m388.onrender.com.evil.example/",
            "https://evil.lexi-m388.onrender.com/",
            "https://lexi-m388.onrender.com@evil.example/",
            "https://user@lexi-m388.onrender.com/",
            "https://lexi-m388.onrender.com:444/",
            "file:///data/data/com.ada.lexi/",
            "javascript:alert(1)",
            "data:text/html,hello",
            "not a url",
        ).forEach { assertFalse(it, SitePolicy.isTrusted(it)) }
        assertFalse(SitePolicy.isTrusted(null))
    }

    @Test fun rejectsPrivilegedAndMalformedExternalLinks() {
        listOf("https://en.wiktionary.org/wiki/word", "mailto:hello@example.com", "tel:+996555123456")
            .forEach { assertTrue(it, SitePolicy.canOpenExternally(it)) }
        listOf("intent://settings", "javascript:alert(1)", "file:///sdcard/", "content://private/", "https://user:pass@evil.example/")
            .forEach { assertFalse(it, SitePolicy.canOpenExternally(it)) }
    }
}
