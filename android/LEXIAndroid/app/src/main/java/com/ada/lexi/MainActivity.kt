package com.ada.lexi

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.view.Gravity
import android.view.View
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.net.toUri
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : ComponentActivity() {
    private lateinit var webView: WebView
    private lateinit var loading: TextView
    private lateinit var failure: LinearLayout
    private lateinit var progress: ProgressBar
    private var showingError = false
    private var destroyed = false
    private var pageGeneration = 0
    private var lastUrl = SitePolicy.HOME_URL
    private var photoCallback: ValueCallback<Array<Uri>>? = null
    private var pendingExport: String? = null
    private var speech: TextToSpeech? = null
    private var speechReady = false
    private val fileWriter = Executors.newSingleThreadExecutor()

    private val photoPicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        photoCallback?.onReceiveValue(uri?.let { arrayOf(it) })
        photoCallback = null
    }

    private val exportPicker = registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        val json = pendingExport
        pendingExport = null
        if (uri != null && json != null) {
            fileWriter.execute {
                val saved = runCatching {
                    requireNotNull(contentResolver.openOutputStream(uri, "wt")).use {
                        it.write(json.toByteArray(Charsets.UTF_8))
                    }
                }.isSuccess
                runOnUiThread {
                    if (!destroyed) notifyUser(if (saved) R.string.export_saved else R.string.export_failed)
                }
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        val background = Color.rgb(17, 18, 22)
        val root = FrameLayout(this).apply { setBackgroundColor(background) }
        webView = WebView(this).apply {
            setBackgroundColor(background)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.allowFileAccess = false
            // Only a user-selected image URI is passed to the file input.
            settings.allowContentAccess = true
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            settings.setSupportMultipleWindows(false)
            settings.javaScriptCanOpenWindowsAutomatically = false
            settings.mediaPlaybackRequiresUserGesture = true
        }
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, false)
        }
        root.addView(webView, FrameLayout.LayoutParams(-1, -1))

        loading = TextView(this).apply {
            setText(R.string.loading)
            textSize = 18f
            setTextColor(Color.WHITE)
            setBackgroundColor(background)
            gravity = Gravity.CENTER
        }
        root.addView(loading, FrameLayout.LayoutParams(-1, -1))
        failure = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28), dp(28), dp(28), dp(28))
            setBackgroundColor(background)
            visibility = View.GONE
            addView(TextView(this@MainActivity).apply {
                setText(R.string.load_error)
                setTextColor(Color.WHITE)
                textSize = 17f
                gravity = Gravity.CENTER
            })
            addView(Button(this@MainActivity).apply {
                setText(R.string.retry)
                setOnClickListener { webView.loadUrl(lastUrl) }
            })
        }
        root.addView(failure, FrameLayout.LayoutParams(-1, -1))
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            progressTintList = ColorStateList.valueOf(Color.rgb(160, 172, 121))
        }
        root.addView(progress, FrameLayout.LayoutParams(-1, dp(3), Gravity.TOP))
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val space = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or
                    WindowInsetsCompat.Type.displayCutout() or WindowInsetsCompat.Type.ime(),
            )
            view.setPadding(space.left, space.top, space.right, space.bottom)
            WindowInsetsCompat.CONSUMED
        }
        setContentView(root)
        ViewCompat.requestApplyInsets(root)

        val adapter = assets.open("lexi-android.js").bufferedReader().use { it.readText() }
        // This bridge exposes no credentials or file-reading methods. Main-frame
        // navigation and network subresources are restricted to the owned origin.
        webView.addJavascriptInterface(AndroidBridge(), "LexiAndroid")
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                if (SitePolicy.isTrusted(url)) return false
                if (request.isForMainFrame && request.hasGesture()) openExternal(url)
                return true
            }

            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val scheme = request.url.scheme?.lowercase(Locale.ROOT)
                if ((scheme in listOf("http", "https") && !SitePolicy.isTrusted(request.url.toString())) ||
                    scheme in listOf("file", "content")) {
                    return WebResourceResponse(
                        "text/plain", "UTF-8", 403, "Blocked", emptyMap(),
                        ByteArrayInputStream(ByteArray(0)),
                    )
                }
                return null
            }

            override fun onPageStarted(view: WebView, url: String, favicon: android.graphics.Bitmap?) {
                pageGeneration += 1
                if (!SitePolicy.isTrusted(url)) {
                    view.stopLoading()
                    showError()
                    return
                }
                lastUrl = url
                showingError = false
                failure.visibility = View.GONE
                loading.visibility = View.VISIBLE
                progress.visibility = View.VISIBLE
                speech?.stop()
            }

            override fun onPageCommitVisible(view: WebView, url: String) {
                if (!showingError && SitePolicy.isTrusted(url)) loading.visibility = View.GONE
            }

            override fun onPageFinished(view: WebView, url: String) {
                progress.visibility = View.GONE
                if (!showingError && SitePolicy.isTrusted(url)) {
                    loading.visibility = View.GONE
                    val page = pageGeneration
                    // A hosting warm-up/error page can also return HTTP 200.
                    // Keep Retry available until the actual LEXI shell appears.
                    view.evaluateJavascript(
                        "Boolean(document.querySelector('#auth-screen') && document.querySelector('#learning-app'))",
                    ) { ready ->
                        if (!destroyed && page == pageGeneration && SitePolicy.isTrusted(view.url)) {
                            if (ready == "true") view.evaluateJavascript(adapter, null) else showError()
                        }
                    }
                }
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) showError()
            }

            override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
                if (request.isForMainFrame && response.statusCode >= 400) showError()
            }
            // Default WebView behavior cancels TLS errors; never bypass it.
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, value: Int) {
                progress.progress = value
                progress.visibility = if (value < 100 && !showingError) View.VISIBLE else View.GONE
            }

            override fun onShowFileChooser(
                view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams,
            ): Boolean {
                if (!SitePolicy.isTrusted(view.url)) return false
                photoCallback?.onReceiveValue(null)
                photoCallback = callback
                try {
                    photoPicker.launch(arrayOf("image/jpeg", "image/png", "image/webp"))
                } catch (_: ActivityNotFoundException) {
                    photoCallback?.onReceiveValue(null)
                    photoCallback = null
                    notifyUser(R.string.photo_unavailable)
                }
                return true
            }
        }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                webView.evaluateJavascript(
                    """(function(){var dialogs=document.querySelectorAll('dialog[open]');
                    var dialog=dialogs[dialogs.length-1];if(!dialog)return false;
                    if(dialog.dispatchEvent(new Event('cancel',{cancelable:true})))dialog.close();return true;})()""",
                ) { handled ->
                    if (!destroyed && handled != "true") {
                        if (webView.canGoBack()) webView.goBack() else finish()
                    }
                }
            }
        })
        configureSpeech()
        lastUrl = savedInstanceState?.getString("lexiUrl")?.takeIf(SitePolicy::isTrusted) ?: SitePolicy.HOME_URL
        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) webView.loadUrl(lastUrl)
    }

    private fun configureSpeech() {
        speech = TextToSpeech(this) { status ->
            speechReady = status == TextToSpeech.SUCCESS
            if (speechReady) speech?.language = Locale.UK
        }
        speech?.setSpeechRate(0.8f)
        speech?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) = speechState(true)
            override fun onDone(utteranceId: String?) = speechState(false)
            override fun onStop(utteranceId: String?, interrupted: Boolean) = speechState(false)
            @Deprecated("Required Android callback")
            override fun onError(utteranceId: String?) = speechState(false)
        })
    }

    private fun speechState(speaking: Boolean) = onTrustedPage {
        webView.evaluateJavascript(
            "window.dispatchEvent(new CustomEvent('lexi:android-speech',{detail:{speaking:$speaking}}));", null,
        )
    }

    private fun onTrustedPage(action: () -> Unit) = runOnUiThread {
        if (!destroyed && SitePolicy.isTrusted(webView.url)) action()
    }

    inner class AndroidBridge {
        @JavascriptInterface
        fun speak(word: String) = onTrustedPage {
            if (word.isBlank() || word.length > 200) return@onTrustedPage
            val engine = speech
            if (!speechReady || engine == null || engine.isLanguageAvailable(Locale.ENGLISH) < TextToSpeech.LANG_AVAILABLE) {
                notifyUser(R.string.voice_unavailable)
                return@onTrustedPage
            }
            if (engine.isSpeaking) engine.stop() else {
                engine.language = Locale.UK
                engine.speak(word, TextToSpeech.QUEUE_FLUSH, null, "lexi-word")
            }
        }

        @JavascriptInterface
        fun stopSpeech() = onTrustedPage { speech?.stop(); speechState(false) }

        @JavascriptInterface
        fun share(text: String) = onTrustedPage {
            if (text.isBlank() || text.length > 8192) return@onTrustedPage
            val send = Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text) }
            try { startActivity(Intent.createChooser(send, getString(R.string.share_word))) }
            catch (_: ActivityNotFoundException) { notifyUser(R.string.link_unavailable) }
        }

        @JavascriptInterface
        fun exportProgress(json: String) = onTrustedPage {
            if (pendingExport != null) { notifyUser(R.string.export_pending); return@onTrustedPage }
            if (json.length > 2 * 1024 * 1024 || runCatching {
                    val data = JSONObject(json)
                    data.optString("app") == "LEXI" && data.optJSONObject("preferences") != null
                }.getOrDefault(false).not()) {
                notifyUser(R.string.export_failed)
                return@onTrustedPage
            }
            pendingExport = json
            try { exportPicker.launch("LEXI-my-data.json") }
            catch (_: ActivityNotFoundException) { pendingExport = null; notifyUser(R.string.export_failed) }
        }
    }

    private fun openExternal(url: String) {
        if (!SitePolicy.canOpenExternally(url)) return
        try { startActivity(Intent(Intent.ACTION_VIEW, url.toUri()).addCategory(Intent.CATEGORY_BROWSABLE)) }
        catch (_: ActivityNotFoundException) { notifyUser(R.string.link_unavailable) }
    }

    private fun showError() {
        showingError = true
        loading.visibility = View.GONE
        progress.visibility = View.GONE
        failure.visibility = View.VISIBLE
    }

    private fun notifyUser(message: Int) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("lexiUrl", lastUrl)
        webView.saveState(outState)
        super.onSaveInstanceState(outState)
    }
    override fun onResume() { super.onResume(); webView.onResume() }
    override fun onPause() { speech?.stop(); webView.onPause(); super.onPause() }
    override fun onStop() { CookieManager.getInstance().flush(); super.onStop() }
    override fun onDestroy() {
        destroyed = true
        photoCallback?.onReceiveValue(null)
        photoCallback = null
        pendingExport = null
        speech?.shutdown()
        fileWriter.shutdownNow()
        webView.removeJavascriptInterface("LexiAndroid")
        webView.stopLoading()
        webView.destroy()
        super.onDestroy()
    }
}
