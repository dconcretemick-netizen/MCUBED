package com.mcubed.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.Menu;
import android.view.MenuItem;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.TextView;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

/** Hosts the MCUBED gateway (embedded Python) and shows its dashboard full screen. */
public class MainActivity extends Activity {
    private static final String PREFS = "mcubed";
    private static final String KEY_OPENROUTER = "openrouter_key";
    private static final int MENU_KEY = 1, MENU_RELOAD = 2;

    private WebView web;
    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        status = new TextView(this);
        status.setText("Starting MCUBED gateway…");
        status.setTextColor(Color.parseColor("#9aa8a6"));
        status.setGravity(Gravity.CENTER);
        setContentView(status);

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0f1417"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if ("127.0.0.1".equals(u.getHost())) return false;
                startActivity(new Intent(Intent.ACTION_VIEW, u)); // external links open in the browser
                return true;
            }
        });

        if (savedInstanceState == null && prefs().getString(KEY_OPENROUTER, null) == null) {
            askForKey(true);
        } else {
            startGateway();
        }
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    private void startGateway() {
        final String key = prefs().getString(KEY_OPENROUTER, "");
        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
                final String url = Python.getInstance().getModule("android_main")
                        .callAttr("start", getFilesDir().getAbsolutePath() + "/gateway", key).toString();
                runOnUiThread(() -> {
                    setContentView(web);
                    if (web.getUrl() == null) web.loadUrl(url);
                });
            } catch (Throwable t) {
                runOnUiThread(() -> status.setText("MCUBED failed to start:\n" + t.getMessage()));
            }
        }, "mcubed-start").start();
    }

    private void askForKey(final boolean firstRun) {
        final EditText input = new EditText(this);
        input.setHint("sk-or-…");
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        new AlertDialog.Builder(this)
                .setTitle("OpenRouter API key")
                .setMessage("One OpenRouter key reaches every model in MCUBED. It is stored only on this "
                        + "device. Skip to explore in demo mode with simulated replies.")
                .setView(input)
                .setCancelable(false)
                .setPositiveButton("Save", (d, w) -> saveKey(input.getText().toString().trim(), firstRun))
                .setNegativeButton(firstRun ? "Demo mode" : "Cancel", (d, w) -> {
                    if (firstRun) saveKey("", true);
                })
                .setNeutralButton(firstRun ? null : "Remove key", firstRun ? null
                        : (d, w) -> saveKey("", false))
                .show();
    }

    private void saveKey(String key, boolean firstRun) {
        prefs().edit().putString(KEY_OPENROUTER, key).apply();
        if (firstRun) {
            startGateway();
            return;
        }
        new Thread(() -> {
            try {
                if (Python.isStarted()) Python.getInstance().getModule("android_main").callAttr("set_key", key);
                runOnUiThread(() -> web.reload());
            } catch (Throwable ignored) {
            }
        }).start();
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, MENU_KEY, 0, "API key");
        menu.add(0, MENU_RELOAD, 1, "Reload");
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == MENU_KEY) {
            askForKey(false);
            return true;
        }
        if (item.getItemId() == MENU_RELOAD) {
            web.reload();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
