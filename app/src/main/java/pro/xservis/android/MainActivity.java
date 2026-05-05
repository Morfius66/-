package pro.xservis.android;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final String API_BASE = "https://xservis.pro";
    private static final String PROFILE_NAME = "Xservis";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private Button connectButton;
    private Button v2raytunButton;
    private Button hiddifyButton;
    private Button clashButton;
    private Button copyButton;
    private EditText userIdField;
    private EditText tokenField;
    private EditText subUrlField;
    private LinearLayout manualActions;
    private ProgressBar progressBar;
    private TextView noticeText;
    private TextView statusText;
    private TextView statusTitle;
    private ConnectionConfig currentConfig;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();
        hydrateFromIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        hydrateFromIntent(intent);
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private void buildUi() {
        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(Color.rgb(7, 19, 13));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(22), dp(28), dp(22), dp(28));
        scrollView.addView(root, new ScrollView.LayoutParams(-1, -2));

        TextView mark = new TextView(this);
        mark.setText("X");
        mark.setTextColor(Color.rgb(6, 32, 18));
        mark.setTextSize(28);
        mark.setTypeface(Typeface.DEFAULT_BOLD);
        mark.setGravity(Gravity.CENTER);
        mark.setBackgroundColor(Color.rgb(45, 244, 138));
        root.addView(mark, new LinearLayout.LayoutParams(dp(56), dp(56)));

        TextView eyebrow = label("Защищённое подключение", 13, Color.argb(176, 244, 255, 248), true);
        eyebrow.setGravity(Gravity.CENTER);
        root.addView(eyebrow, topMargin(-1, -2, 18));

        TextView title = label("Xservis", 44, Color.rgb(244, 255, 248), true);
        title.setGravity(Gravity.CENTER);
        root.addView(title, topMargin(-1, -2, 2));

        TextView hero = label("Нажмите одну кнопку. Xservis проверит сеть, получит профиль и откроет VPN-приложение для импорта.", 16, Color.argb(176, 244, 255, 248), false);
        hero.setGravity(Gravity.CENTER);
        root.addView(hero, topMargin(-1, -2, 20));

        statusTitle = label("Готово к подключению", 20, Color.rgb(244, 255, 248), true);
        statusTitle.setGravity(Gravity.CENTER);
        root.addView(statusTitle, topMargin(-1, -2, 22));

        statusText = label("Проверка начнётся после нажатия кнопки.", 14, Color.argb(176, 244, 255, 248), false);
        statusText.setGravity(Gravity.CENTER);
        root.addView(statusText, topMargin(-1, -2, 6));

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        progressBar.setProgress(16);
        root.addView(progressBar, topMargin(-1, dp(12), 18));

        userIdField = input("user_id из Xservis бота");
        root.addView(userIdField, topMargin(-1, dp(52), 18));

        tokenField = input("token подписки");
        root.addView(tokenField, topMargin(-1, dp(52), 10));

        subUrlField = input("или готовый sub_url");
        root.addView(subUrlField, topMargin(-1, dp(52), 10));

        connectButton = primaryButton("Подключиться");
        connectButton.setOnClickListener(view -> startConnection());
        root.addView(connectButton, topMargin(-1, dp(60), 18));

        manualActions = new LinearLayout(this);
        manualActions.setOrientation(LinearLayout.VERTICAL);
        manualActions.setVisibility(View.GONE);
        root.addView(manualActions, topMargin(-1, -2, 12));

        hiddifyButton = secondaryButton("Открыть в Hiddify");
        hiddifyButton.setOnClickListener(view -> openDeepLink(currentConfig.hiddifyLink));
        manualActions.addView(hiddifyButton, topMargin(-1, dp(50), 0));

        v2raytunButton = secondaryButton("Открыть в V2RayTun");
        v2raytunButton.setOnClickListener(view -> openDeepLink(currentConfig.v2raytunLink));
        manualActions.addView(v2raytunButton, topMargin(-1, dp(50), 8));

        clashButton = secondaryButton("Открыть в Clash");
        clashButton.setOnClickListener(view -> openDeepLink(currentConfig.clashLink));
        manualActions.addView(clashButton, topMargin(-1, dp(50), 8));

        copyButton = secondaryButton("Скопировать подписку");
        copyButton.setOnClickListener(view -> copySubscription());
        manualActions.addView(copyButton, topMargin(-1, dp(50), 8));

        noticeText = label("", 13, Color.rgb(255, 231, 173), false);
        noticeText.setGravity(Gravity.CENTER);
        noticeText.setVisibility(View.GONE);
        root.addView(noticeText, topMargin(-1, -2, 16));

        setContentView(scrollView);
    }

    private void hydrateFromIntent(Intent intent) {
        Uri data = intent.getData();
        if (data == null) {
            return;
        }
        setIfPresent(userIdField, data.getQueryParameter("user_id"));
        setIfPresent(userIdField, data.getQueryParameter("uid"));
        setIfPresent(tokenField, data.getQueryParameter("token"));
        setIfPresent(tokenField, data.getQueryParameter("t"));
        setIfPresent(subUrlField, data.getQueryParameter("sub_url"));
        setIfPresent(subUrlField, data.getQueryParameter("subscription_url"));
    }

    private void startConnection() {
        setBusy(true);
        showNotice("");
        setStatus("Проверяем сеть", "Подбираем рабочий способ подключения.", 28);

        executor.execute(() -> {
            NetworkScan scan = scanNetwork();
            runOnUiThread(() -> setStatus("Генерируем конфигурацию", "Получаем профиль Xservis для вашей сети.", 66));
            try {
                ConnectionConfig config = getConnectionConfig(scan);
                currentConfig = config;
                runOnUiThread(() -> {
                    setStatus("Подключение готово", "Профиль Xservis открыт в приложении. Если приложение не открылось, выберите его ниже.", 100);
                    manualActions.setVisibility(View.VISIBLE);
                    setBusy(false);
                    openRecommendedClient(config);
                });
                executor.execute(() -> sendTelemetry(scan, config));
            } catch (MissingSubscriptionException error) {
                ConnectionConfig fallback = buildFallbackConfig(scan);
                currentConfig = fallback;
                runOnUiThread(() -> {
                    setStatus("Нужны данные подписки", "Введите user_id + token или готовый sub_url.", 100);
                    manualActions.setVisibility(View.VISIBLE);
                    showNotice("Откройте приложение из бота Xservis или вставьте данные подписки вручную.");
                    setBusy(false);
                });
                executor.execute(() -> sendTelemetry(scan, fallback));
            }
        });
    }

    private NetworkScan scanNetwork() {
        List<ProbeResult> probes = new ArrayList<>();
        probes.add(timeRequest("xservis-api", API_BASE + "/api/health", "GET", null));
        probes.add(timeRequest("xservis-subscription", buildSubscriptionUrl(), "GET", null));
        probes.add(timeRequest("internet-204", "https://www.gstatic.com/generate_204", "GET", null));
        probes.add(timeRequest("dns-google", "https://dns.google/resolve?name=xservis.pro&type=A", "GET", null));
        return new NetworkScan(probes, detectBlockingMethod(probes), chooseClient());
    }

    private ConnectionConfig getConnectionConfig(NetworkScan scan) throws MissingSubscriptionException {
        JSONObject payload = new JSONObject();
        try {
            payload.put("profileName", PROFILE_NAME);
            payload.put("userId", text(userIdField));
            payload.put("token", text(tokenField));
            payload.put("scan", scan.toJson());
        } catch (JSONException ignored) {
        }

        ProbeResult response = timeRequest("auto-config", API_BASE + "/api/connect/auto-config", "POST", payload.toString());
        if (response.ok && response.body.length() > 0) {
            try {
                return normalizeConfig(new JSONObject(response.body), scan);
            } catch (JSONException ignored) {
            }
        }

        if (text(subUrlField).isEmpty() && (text(userIdField).isEmpty() || text(tokenField).isEmpty())) {
            throw new MissingSubscriptionException();
        }
        return buildFallbackConfig(scan);
    }

    private void sendTelemetry(NetworkScan scan, ConnectionConfig config) {
        JSONObject payload = new JSONObject();
        try {
            JSONObject configJson = new JSONObject();
            configJson.put("blockingMethod", config.blockingMethod);
            configJson.put("recommendedClient", config.recommendedClient);
            configJson.put("subscriptionUrl", scrubUrl(config.subscriptionUrl));
            payload.put("type", "network_scan");
            payload.put("profileName", PROFILE_NAME);
            payload.put("scan", scan.toJson());
            payload.put("config", configJson);
            timeRequest("telemetry", API_BASE + "/api/telemetry/network-scan", "POST", payload.toString());
        } catch (JSONException ignored) {
        }
    }

    private ConnectionConfig normalizeConfig(JSONObject data, NetworkScan scan) {
        String subscriptionUrl = data.optString("subscriptionUrl", data.optString("subscription_url", buildSubscriptionUrl()));
        JSONObject deepLinks = data.optJSONObject("deepLinks");
        if (deepLinks == null) {
            deepLinks = data.optJSONObject("deep_links");
        }
        String blockingMethod = data.optString("blockingMethod", data.optString("blocking_method", scan.blockingMethod));
        String recommendedClient = data.optString("recommendedClient", data.optString("recommended_client", scan.recommendedClient));
        return buildConfig(subscriptionUrl, blockingMethod, recommendedClient, deepLinks);
    }

    private ConnectionConfig buildFallbackConfig(NetworkScan scan) {
        return buildConfig(buildSubscriptionUrl(), scan.blockingMethod, scan.recommendedClient, null);
    }

    private ConnectionConfig buildConfig(String subscriptionUrl, String blockingMethod, String recommendedClient, JSONObject deepLinks) {
        String encoded = urlEncode(subscriptionUrl);
        String name = urlEncode(PROFILE_NAME);
        String v2raytun = optDeepLink(deepLinks, "v2raytun", "v2raytun://import/" + encoded + "?name=" + name);
        String hiddify = optDeepLink(deepLinks, "hiddify", "hiddify://install-config?url=" + encoded + "&name=" + name);
        String clash = optDeepLink(deepLinks, "clash", "clash://install-config?url=" + encoded + "&name=" + name);
        return new ConnectionConfig(subscriptionUrl, blockingMethod, recommendedClient, v2raytun, hiddify, clash);
    }

    private String buildSubscriptionUrl() {
        if (!text(subUrlField).isEmpty()) {
            return text(subUrlField);
        }
        String id = text(userIdField).isEmpty() ? "telegram" : text(userIdField);
        String url = API_BASE + "/api/sub/" + urlEncode(id);
        if (!text(tokenField).isEmpty()) {
            url += "?token=" + urlEncode(text(tokenField));
        }
        return url;
    }

    private ProbeResult timeRequest(String name, String value, String method, String body) {
        long started = System.nanoTime();
        HttpURLConnection connection = null;
        try {
            URL url = new URL(value);
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(5500);
            connection.setReadTimeout(5500);
            connection.setRequestMethod(method);
            connection.setUseCaches(false);
            if (body != null) {
                connection.setDoOutput(true);
                connection.setRequestProperty("content-type", "application/json; charset=utf-8");
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                connection.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream output = connection.getOutputStream()) {
                    output.write(bytes);
                }
            }
            int status = connection.getResponseCode();
            String responseBody = readBody(status >= 400 ? connection.getErrorStream() : connection.getInputStream());
            return new ProbeResult(name, status >= 200 && status < 500, status, elapsedMs(started), "", responseBody);
        } catch (IOException error) {
            return new ProbeResult(name, false, 0, elapsedMs(started), error.getClass().getSimpleName(), "");
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private String detectBlockingMethod(List<ProbeResult> probes) {
        boolean ownReachable = isOk(probes, "xservis-api") || isOk(probes, "xservis-subscription");
        boolean internetReachable = isOk(probes, "internet-204");
        boolean dnsReachable = isOk(probes, "dns-google");
        if (!isOnline() || (!internetReachable && !dnsReachable)) {
            return "offline_or_network_firewall";
        }
        if (!ownReachable && dnsReachable && internetReachable) {
            return "domain_or_tls_block";
        }
        if (!dnsReachable && internetReachable) {
            return "dns_interference";
        }
        if (ownReachable && internetReachable) {
            return "direct";
        }
        return "restricted_network";
    }

    private boolean isOnline() {
        ConnectivityManager manager = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        if (manager == null || manager.getActiveNetwork() == null) {
            return false;
        }
        NetworkCapabilities capabilities = manager.getNetworkCapabilities(manager.getActiveNetwork());
        return capabilities != null && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }

    private boolean isOk(List<ProbeResult> probes, String name) {
        for (ProbeResult probe : probes) {
            if (probe.name.equals(name)) {
                return probe.ok;
            }
        }
        return false;
    }

    private String chooseClient() {
        if (isPackageInstalled("app.hiddify.com")) {
            return "hiddify";
        }
        if (isPackageInstalled("com.v2raytun.android")) {
            return "v2raytun";
        }
        return "hiddify";
    }

    private boolean isPackageInstalled(String packageName) {
        try {
            getPackageManager().getPackageInfo(packageName, 0);
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    private void openRecommendedClient(ConnectionConfig config) {
        if ("v2raytun".equals(config.recommendedClient)) {
            openDeepLink(config.v2raytunLink);
        } else if ("clash".equals(config.recommendedClient)) {
            openDeepLink(config.clashLink);
        } else {
            openDeepLink(config.hiddifyLink);
        }
    }

    private void openDeepLink(String link) {
        if (link == null || link.isEmpty()) {
            return;
        }
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(link));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        } catch (ActivityNotFoundException error) {
            showNotice("VPN-приложение не установлено. Установите Hiddify, V2RayTun или Clash и повторите импорт.");
        }
    }

    private void copySubscription() {
        if (currentConfig == null) {
            currentConfig = buildFallbackConfig(new NetworkScan(new ArrayList<>(), "unknown", chooseClient()));
        }
        ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        clipboard.setPrimaryClip(ClipData.newPlainText("Xservis subscription", currentConfig.subscriptionUrl));
        Toast.makeText(this, "Ссылка подписки скопирована", Toast.LENGTH_SHORT).show();
        showNotice("Ссылка подписки скопирована.");
    }

    private String readBody(InputStream stream) throws IOException {
        if (stream == null) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
            }
        }
        return builder.toString();
    }

    private long elapsedMs(long started) {
        return Math.round((System.nanoTime() - started) / 1_000_000.0);
    }

    private String scrubUrl(String value) {
        return value.replaceAll("([?&](token|t)=)[^&]+", "$1hidden");
    }

    private String optDeepLink(JSONObject deepLinks, String key, String fallback) {
        if (deepLinks == null) {
            return fallback;
        }
        return deepLinks.optString(key, fallback);
    }

    private String urlEncode(String value) {
        try {
            return URLEncoder.encode(value, "UTF-8").replace("+", "%20");
        } catch (Exception ignored) {
            return value;
        }
    }

    private void setBusy(boolean busy) {
        connectButton.setEnabled(!busy);
        connectButton.setText(busy ? "Подключаем..." : "Подключиться");
    }

    private void setStatus(String title, String text, int progress) {
        statusTitle.setText(title);
        statusText.setText(text);
        progressBar.setProgress(Math.max(8, Math.min(100, progress)));
    }

    private void showNotice(String text) {
        noticeText.setText(text);
        noticeText.setVisibility(text.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private String text(EditText input) {
        return input.getText().toString().trim();
    }

    private void setIfPresent(EditText input, String value) {
        if (value != null && !value.isEmpty()) {
            input.setText(value);
        }
    }

    private TextView label(String value, int sp, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        if (bold) {
            view.setTypeface(Typeface.DEFAULT_BOLD);
        }
        return view;
    }

    private EditText input(String hint) {
        EditText input = new EditText(this);
        input.setHint(hint);
        input.setSingleLine(true);
        input.setTextColor(Color.rgb(244, 255, 248));
        input.setHintTextColor(Color.argb(126, 244, 255, 248));
        input.setTextSize(15);
        input.setPadding(dp(16), 0, dp(16), 0);
        return input;
    }

    private Button primaryButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(Color.rgb(5, 33, 19));
        button.setTextSize(18);
        button.setTypeface(Typeface.DEFAULT_BOLD);
        button.setBackgroundColor(Color.rgb(45, 244, 138));
        return button;
    }

    private Button secondaryButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextColor(Color.rgb(244, 255, 248));
        button.setTextSize(15);
        button.setBackgroundColor(Color.rgb(22, 44, 32));
        return button;
    }

    private LinearLayout.LayoutParams topMargin(int width, int height, int topDp) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(width, height);
        params.topMargin = dp(topDp);
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static final class ConnectionConfig {
        final String subscriptionUrl;
        final String blockingMethod;
        final String recommendedClient;
        final String v2raytunLink;
        final String hiddifyLink;
        final String clashLink;

        ConnectionConfig(String subscriptionUrl, String blockingMethod, String recommendedClient, String v2raytunLink, String hiddifyLink, String clashLink) {
            this.subscriptionUrl = subscriptionUrl;
            this.blockingMethod = blockingMethod;
            this.recommendedClient = recommendedClient;
            this.v2raytunLink = v2raytunLink;
            this.hiddifyLink = hiddifyLink;
            this.clashLink = clashLink;
        }
    }

    private static final class NetworkScan {
        final List<ProbeResult> probes;
        final String blockingMethod;
        final String recommendedClient;

        NetworkScan(List<ProbeResult> probes, String blockingMethod, String recommendedClient) {
            this.probes = probes;
            this.blockingMethod = blockingMethod;
            this.recommendedClient = recommendedClient;
        }

        JSONObject toJson() throws JSONException {
            JSONObject json = new JSONObject();
            JSONArray probeArray = new JSONArray();
            for (ProbeResult probe : probes) {
                probeArray.put(probe.toJson());
            }
            json.put("app", "xservis-android");
            json.put("version", "1.0.0");
            json.put("blockingMethod", blockingMethod);
            json.put("recommendedClient", recommendedClient);
            json.put("locale", Locale.getDefault().toLanguageTag());
            json.put("probes", probeArray);
            return json;
        }
    }

    private static final class ProbeResult {
        final String name;
        final boolean ok;
        final int status;
        final long latencyMs;
        final String error;
        final String body;

        ProbeResult(String name, boolean ok, int status, long latencyMs, String error, String body) {
            this.name = name;
            this.ok = ok;
            this.status = status;
            this.latencyMs = latencyMs;
            this.error = error;
            this.body = body;
        }

        JSONObject toJson() throws JSONException {
            JSONObject json = new JSONObject();
            json.put("name", name);
            json.put("ok", ok);
            json.put("status", status);
            json.put("latencyMs", latencyMs);
            if (!error.isEmpty()) {
                json.put("error", error);
            }
            return json;
        }
    }

    private static final class MissingSubscriptionException extends Exception {
    }
}
