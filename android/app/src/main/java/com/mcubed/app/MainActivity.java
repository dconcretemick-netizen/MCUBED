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
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

/** Hosts the MCUBED gateway (embedded Python) and shows its dashboard full screen. */
public class MainActivity extends Activity {
    private static final String PREFS = "mcubed";
    private static final String KEY_CONFIGURED = "keys_configured";
    /** Provider key slots: environment variable name and label shown in the dialog. */
    private static final String[][] KEYS = {
            {"OPENROUTER_API_KEY", "OpenRouter (reaches every model)"},
            {"OPENAI_API_KEY", "OpenAI (direct)"},
            {"DEEPSEEK_API_KEY", "DeepSeek (direct)"},
            {"GITHUB_TOKEN", "GitHub token (auto-add repositories)"},
    };
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
                String scheme = u.getScheme();
                if ("http".equals(scheme) || "https".equals(scheme)) { // web pages open in the in-app browser
                    startActivity(new Intent(MainActivity.this, BrowserActivity.class)
                            .putExtra(BrowserActivity.EXTRA_URL, u.toString()));
                } else {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, u));
                    } catch (Exception ignored) {
                    }
                }
                return true;
            }
        });

        if (savedInstanceState == null && !prefs().getBoolean(KEY_CONFIGURED, false)) {
            askForKey(true);
        } else {
            startGateway();
        }
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    private void startGateway() {
        final String keys = keysJson();
        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
                final String url = Python.getInstance().getModule("android_main")
                        .callAttr("start", getFilesDir().getAbsolutePath() + "/gateway", keys).toString();
                runOnUiThread(() -> {
                    setContentView(web);
                    if (web.getUrl() == null) web.loadUrl(url);
                });
            } catch (Throwable t) {
                runOnUiThread(() -> status.setText("MCUBED failed to start:\n" + t.getMessage()));
            }
        }, "mcubed-start").start();
    }

    private String keysJson() {
        JSONObject o = new JSONObject();
        try {
            for (String[] k : KEYS) o.put(k[0], prefs().getString(k[0], ""));
        } catch (Exception ignored) {
        }
        return o.toString();
    }

    private void askForKey(final boolean firstRun) {
        final LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        box.setPadding(pad, pad / 2, pad, 0);
        final EditText[] fields = new EditText[KEYS.length];
        for (int i = 0; i < KEYS.length; i++) {
            TextView label = new TextView(this);
            label.setText(KEYS[i][1]);
            box.addView(label);
            EditText input = new EditText(this);
            input.setSingleLine(true);
            input.setHint(prefs().getString(KEYS[i][0], "").isEmpty() ? "not set" : "saved (leave blank to keep)");
            input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
            box.addView(input);
            fields[i] = input;
        }
        new AlertDialog.Builder(this)
                .setTitle("AI provider keys")
                .setMessage("Add any keys you have. They are stored only on this device. "
                        + "With no keys, MCUBED runs in demo mode with simulated replies.")
                .setView(box)
                .setCancelable(false)
                .setPositiveButton("Save", (d, w) -> {
                    SharedPreferences.Editor e = prefs().edit();
                    for (int i = 0; i < KEYS.length; i++) {
                        String v = fields[i].getText().toString().trim();
                        if (!v.isEmpty()) e.putString(KEYS[i][0], v);
                    }
                    e.putBoolean(KEY_CONFIGURED, true).apply();
                    applyKeys(firstRun);
                })
                .setNegativeButton(firstRun ? "Demo mode" : "Cancel", (d, w) -> {
                    if (firstRun) {
                        prefs().edit().putBoolean(KEY_CONFIGURED, true).apply();
                        applyKeys(true);
                    }
                })
                .setNeutralButton(firstRun ? null : "Remove all", firstRun ? null : (d, w) -> {
                    SharedPreferences.Editor e = prefs().edit();
                    for (String[] k : KEYS) e.remove(k[0]);
                    e.apply();
                    applyKeys(false);
                })
                .show();
    }

    private void applyKeys(boolean firstRun) {
        if (firstRun) {
            startGateway();
            return;
        }
        final String keys = keysJson();
        new Thread(() -> {
            try {
                if (Python.isStarted()) Python.getInstance().getModule("android_main").callAttr("set_keys", keys);
                runOnUiThread(() -> web.reload());
            } catch (Throwable ignored) {
            }
        }).start();
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, MENU_KEY, 0, "AI keys");
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
