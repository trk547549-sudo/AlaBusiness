package com.alabusiness.app;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {

    private static final String SERVER = "http://127.0.0.1:5050";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private LinearLayout root;
    private LinearLayout content;
    private EditText messageInput;

    private int currentCustomerId = -1;
    private String currentCustomerName = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        showCustomers();
    }

    private TextView text(String value, float size) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextSize(size);
        t.setTextColor(Color.BLACK);
        t.setPadding(24, 20, 24, 20);
        return t;
    }

    private void base(String title) {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(20, 20, 20, 20);
        root.setBackgroundColor(Color.WHITE);

        TextView header = text(title, 25);
        header.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        header.setGravity(Gravity.CENTER);

        root.addView(header);

        ScrollView scroll = new ScrollView(this);

        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(5, 10, 5, 10);

        scroll.addView(content);

        root.addView(
                scroll,
                new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        0,
                        1
                )
        );

        setContentView(root);
    }

    private Button button(String label) {
        Button b = new Button(this);
        b.setText(label);
        b.setTextSize(16);
        return b;
    }

    private void showCustomers() {
        base("💬 AlaBusiness");

        TextView loading = text("جاري تحميل العملاء...", 18);
        content.addView(loading);

        executor.execute(() -> {
            try {
                String response = request("GET", SERVER + "/api/customers", null);
                JSONArray customers = new JSONArray(response);

                runOnUiThread(() -> {
                    content.removeAllViews();

                    if (customers.length() == 0) {
                        content.addView(text(
                                "لا يوجد عملاء حتى الآن.",
                                18
                        ));
                    }

                    for (int i = 0; i < customers.length(); i++) {
                        try {
                            JSONObject customer = customers.getJSONObject(i);

                            int id = customer.getInt("id");
                            String name = customer.getString("name");

                            Button customerButton =
                                    button("👤 " + name);

                            customerButton.setOnClickListener(v ->
                                    showChat(id, name)
                            );

                            content.addView(customerButton);
                        } catch (Exception ignored) {
                        }
                    }

                    Button add = button("➕ إضافة عميل");
                    add.setOnClickListener(v -> showAddCustomer());
                    content.addView(add);
                });

            } catch (Exception e) {
                runOnUiThread(() ->
                        showError("تعذر الاتصال بالخادم:\n" + e.getMessage())
                );
            }
        });
    }

    private void showAddCustomer() {
        base("➕ إضافة عميل");

        EditText name = new EditText(this);
        name.setHint("اسم العميل");
        name.setTextSize(18);

        content.addView(name);

        Button save = button("حفظ العميل");

        save.setOnClickListener(v -> {
            String customerName = name.getText().toString().trim();

            if (customerName.isEmpty()) {
                Toast.makeText(
                        this,
                        "اكتب اسم العميل",
                        Toast.LENGTH_SHORT
                ).show();
                return;
            }

            JSONObject data = new JSONObject();

            try {
                data.put("name", customerName);
            } catch (Exception e) {
                return;
            }

            executor.execute(() -> {
                try {
                    request(
                            "POST",
                            SERVER + "/api/customers",
                            data.toString()
                    );

                    runOnUiThread(this::showCustomers);

                } catch (Exception e) {
                    runOnUiThread(() ->
                            showError("فشل حفظ العميل:\n" + e.getMessage())
                    );
                }
            });
        });

        content.addView(save);

        Button back = button("↩ العودة");
        back.setOnClickListener(v -> showCustomers());
        content.addView(back);
    }

    private void showChat(int customerId, String customerName) {
        currentCustomerId = customerId;
        currentCustomerName = customerName;

        base("💬 " + customerName);

        Button refresh = button("🔄 تحديث");
        refresh.setOnClickListener(v ->
                loadMessages(customerId)
        );

        content.addView(refresh);

        messageInput = new EditText(this);
        messageInput.setHint("اكتب رسالة...");
        messageInput.setTextSize(17);

        root.addView(messageInput);

        Button send = button("إرسال");

        send.setOnClickListener(v -> sendMessage());

        root.addView(send);

        Button back = button("↩ العملاء");
        back.setOnClickListener(v -> showCustomers());

        root.addView(back);

        loadMessages(customerId);
    }

    private void loadMessages(int customerId) {
        executor.execute(() -> {
            try {
                String url = SERVER +
                        "/api/messages?customer_id=" +
                        URLEncoder.encode(
                                String.valueOf(customerId),
                                "UTF-8"
                        );

                String response = request("GET", url, null);
                JSONArray messages = new JSONArray(response);

                runOnUiThread(() -> {
                    content.removeAllViews();

                    for (int i = 0; i < messages.length(); i++) {
                        try {
                            JSONObject message =
                                    messages.getJSONObject(i);

                            String direction =
                                    message.getString("direction");

                            String messageText =
                                    message.getString("text");

                            TextView item = text(
                                    (direction.equals("outgoing")
                                            ? "أنت: "
                                            : "العميل: ")
                                            + messageText,
                                    17
                            );

                            content.addView(item);

                        } catch (Exception ignored) {
                        }
                    }
                });

            } catch (Exception e) {
                runOnUiThread(() ->
                        showError("فشل تحميل الرسائل:\n" + e.getMessage())
                );
            }
        });
    }

    private void sendMessage() {
        if (currentCustomerId == -1 || messageInput == null) {
            return;
        }

        String message =
                messageInput.getText().toString().trim();

        if (message.isEmpty()) {
            return;
        }

        JSONObject data = new JSONObject();

        try {
            data.put("customer_id", currentCustomerId);
            data.put("text", message);
        } catch (Exception e) {
            return;
        }

        executor.execute(() -> {
            try {
                request(
                        "POST",
                        SERVER + "/api/messages",
                        data.toString()
                );

                runOnUiThread(() -> {
                    messageInput.setText("");
                    loadMessages(currentCustomerId);
                });

            } catch (Exception e) {
                runOnUiThread(() ->
                        showError("فشل إرسال الرسالة:\n" + e.getMessage())
                );
            }
        });
    }

    private String request(
            String method,
            String urlString,
            String body
    ) throws Exception {

        URL url = new URL(urlString);

        HttpURLConnection connection =
                (HttpURLConnection) url.openConnection();

        connection.setRequestMethod(method);
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(5000);
        connection.setRequestProperty(
                "Content-Type",
                "application/json"
        );

        if (body != null) {
            connection.setDoOutput(true);

            OutputStream output =
                    connection.getOutputStream();

            output.write(body.getBytes("UTF-8"));
            output.flush();
            output.close();
        }

        int code = connection.getResponseCode();

        BufferedReader reader =
                new BufferedReader(
                        new InputStreamReader(
                                code >= 400
                                        ? connection.getErrorStream()
                                        : connection.getInputStream(),
                                "UTF-8"
                        )
                );

        StringBuilder result = new StringBuilder();

        String line;

        while ((line = reader.readLine()) != null) {
            result.append(line);
        }

        reader.close();
        connection.disconnect();

        if (code >= 400) {
            throw new Exception(
                    "HTTP " + code + ": " + result
            );
        }

        return result.toString();
    }

    private void showError(String message) {
        Toast.makeText(
                this,
                message,
                Toast.LENGTH_LONG
        ).show();
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }
}
