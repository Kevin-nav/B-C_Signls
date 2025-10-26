# MQL5 Integration Guide for B/C Signals (TCP Protocol)

This guide provides instructions for an MQL5 developer to integrate an Expert Advisor (EA) with the B/C Signals Python backend using a secure and persistent TCP socket connection.

---

## 1. Overview of the TCP Protocol

We have moved from stateless HTTP requests to a stateful TCP connection for improved performance and reliability. The process is as follows:

1.  **Persistent Connection**: The EA establishes a long-lived TCP connection to the server.
2.  **Authentication**: Upon connecting, the EA must immediately send the secret key to authenticate itself.
3.  **Message Framing**: All messages (both from client and server) are prefixed with a 4-byte header indicating the length of the JSON payload that follows. This ensures message integrity.
4.  **Resilience**: The EA is responsible for detecting connection drops and automatically reconnecting.

---

## 2. Prerequisites

1.  **Server IP & Port**: The public IP address of your server and the designated TCP port (`5200`).
2.  **Secret Key**: The `WEBHOOK_SECRET_KEY` from your `.env` file.
3.  **`stunnel`**: For SSL/TLS encryption, you will need to install `stunnel` on the same machine where MetaTrader 5 is running. Download it from the official website: [stunnel.org](https://www.stunnel.org/downloads.html)

---

## 3. `stunnel` Configuration for Secure Communication

`stunnel` creates a secure SSL tunnel, allowing the EA to connect locally while `stunnel` handles the encryption to the remote server. This is the recommended and most robust method for securing the connection.

1.  After installing `stunnel`, open its configuration file (`stunnel.conf`).
2.  Add the following configuration block. This tells `stunnel` to listen for local connections on port `5201` and forward them securely to your server on port `5200`.

```ini
[autosig-tunnel]
client = yes
accept = 127.0.0.1:5201
connect = <YOUR_SERVER_IP>:5200
```

*   Replace `<YOUR_SERVER_IP>` with your server's actual IP address.
*   **Important**: The MQL5 EA will now connect to `127.0.0.1:5201`.

3.  Run `stunnel`. It will now manage the secure connection in the background.

---

## 4. MQL5 Code Integration

This code provides a complete solution for connecting to the server and sending signals. Save it as `BC_Signals_TCP_Integration.mqh`.

### `BC_Signals_TCP_Integration.mqh`

```mql5
//+------------------------------------------------------------------+
//|                                 BC_Signals_TCP_Integration.mqh       |
//|                   MQL5 TCP Integration for B/C Signals            |
//+------------------------------------------------------------------+
#property copyright "Your Name"
#property link      "Your Website"

// =====================================================================
// CONFIGURATION
// =====================================================================

#define SERVER_IP   "127.0.0.1"       // Connect to local stunnel
#define SERVER_PORT 5201              // The stunnel listening port
#define SECRET_KEY  "YOUR_SECURE_SECRET_KEY_HERE" // The key from the .env file
#define RECONNECT_TIMEOUT 5000        // Time in ms to wait before reconnecting

// =====================================================================
// GLOBALS
// =====================================================================

int  g_socket_handle = -1;
long g_last_connect_attempt = 0;

// =====================================================================
// CORE FUNCTIONS
// =====================================================================

/**
 * Connects to the server if disconnected. Handles authentication.
 * @return - true if connected and authenticated, otherwise false.
 */
bool EnsureConnected()
{
    // If already connected, do nothing
    if (g_socket_handle != -1 && SocketIsConnected(g_socket_handle))
    {
        return true;
    }

    // If recently tried to connect, wait before trying again
    if (GetTickCount64() - g_last_connect_attempt < RECONNECT_TIMEOUT)
    {
        return false;
    }

    g_last_connect_attempt = GetTickCount64();
    Print("[B/C Signals] Attempting to connect to server...");

    // Close previous handle if it exists
    if (g_socket_handle != -1)
    {
        SocketClose(g_socket_handle);
    }

    // Create a new TCP socket
    g_socket_handle = SocketCreate(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (g_socket_handle == -1)
    {
        PrintFormat("[B/C Signals] Failed to create socket. Error: %d", GetLastError());
        return false;
    }

    // Connect to the server (stunnel)
    if (!SocketConnect(g_socket_handle, SERVER_IP, SERVER_PORT, 1000))
    {
        PrintFormat("[B/C Signals] Failed to connect to %s:%d. Error: %d", SERVER_IP, SERVER_PORT, GetLastError());
        SocketClose(g_socket_handle);
        g_socket_handle = -1;
        return false;
    }

    Print("[B/C Signals] Connected! Authenticating...");

    // Authenticate immediately after connecting
    string auth_payload = StringFormat("{\"secret_key\":\"%s\"}", SECRET_KEY);
    if (!SendMessage(auth_payload))
    {
        Print("[B/C Signals] Failed to send authentication key.");
        SocketClose(g_socket_handle);
        g_socket_handle = -1;
        return false;
    }
    
    // Optional: Wait for server auth confirmation
    // For simplicity, this example assumes immediate success.

    Print("[B/C Signals] Authentication sent. Connection established.");
    return true;
}

/**
 * Sends a length-prefixed message to the server.
 * @param payload - The JSON string to send.
 * @return - true if successful, otherwise false.
 */
bool SendMessage(string payload)
{
    if (g_socket_handle == -1 || !SocketIsConnected(g_socket_handle))
    {
        Print("[B/C Signals] Cannot send message, not connected.");
        return false;
    }

    // 1. Convert payload to char array
    char payload_data[];
    int payload_size = StringToCharArray(payload, payload_data, 0, -1, CP_UTF8) - 1;

    // 2. Create 4-byte length header (Big Endian)
    char header[4];
    header[0] = (char)((payload_size >> 24) & 0xFF);
    header[1] = (char)((payload_size >> 16) & 0xFF);
    header[2] = (char)((payload_size >> 8) & 0xFF);
    header[3] = (char)(payload_size & 0xFF);

    // 3. Send header
    if (SocketSend(g_socket_handle, header, 4) != 4)
    {
        Print("[B/C Signals] Failed to send message header.");
        return false;
    }

    // 4. Send payload
    if (SocketSend(g_socket_handle, payload_data, payload_size) != payload_size)
    {
        Print("[B/C Signals] Failed to send message payload.");
        return false;
    }

    return true;
}

/**
 * Main function to send a trade signal.
 * @param action - "BUY", "SELL", or "CLOSE".
 * @param symbol - The trading symbol.
 * @param price - The action price.
 * @param open_signal_id - Required for "CLOSE" actions.
 * @return - true if the signal was sent successfully.
 */
bool SendTradeSignal(string action, string symbol, double price, int open_signal_id = 0)
{
    if (!EnsureConnected())
    {
        return false;
    }

    // Build JSON payload
    string json_data = StringFormat(
        "{\"action\":\"%s\",\"symbol\":\"%s\",\"price\":%.5f",
        action,
        symbol,
        price
    );

    if (action == "CLOSE" && open_signal_id > 0)
    {
        json_data += StringFormat(",\"open_signal_id\":%d}", open_signal_id);
    }
    else
    {
        json_data += "}";
    }

    PrintFormat("[B/C Signals] Sending signal: %s", json_data);
    return SendMessage(json_data);
}

/**
 * Reads a length-prefixed message from the server (for receiving responses).
 * @param result_payload - The char array to fill with the payload.
 * @return - true if a message was read successfully.
 */
bool ReadMessage(char &result_payload[])
{
    if (g_socket_handle == -1 || !SocketIsConnected(g_socket_handle) || SocketIsReadable(g_socket_handle) <= 0)
    {
        return false;
    }

    // 1. Read 4-byte header
    char header[4];
    if (SocketRead(g_socket_handle, header, 4, 1000) != 4)
    {
        return false;
    }
    int payload_size = (header[0] << 24) | (header[1] << 16) | (header[2] << 8) | header[3];

    // 2. Read payload
    if (payload_size > 0 && SocketRead(g_socket_handle, result_payload, payload_size, 2000) == payload_size)
    {
        return true;
    }

    return false;
}

// Call this in OnDeinit() of your EA
void DeinitializeConnection()
{
    if(g_socket_handle != -1)
    {
        SocketClose(g_socket_handle);
        g_socket_handle = -1;
        Print("[B/C Signals] Connection closed.");
    }
}
```

### Example Usage in Your EA

```mql5
#include "BC_Signals_TCP_Integration.mqh"

// In OnInit(), attempt initial connection
int OnInit()
{
    EnsureConnected();
    return(INIT_SUCCEEDED);
}

// In OnDeinit(), clean up the connection
void OnDeinit(const int reason)
{
    DeinitializeConnection();
}

// In OnTick(), check for responses and send signals
void OnTick()
{
    // Always ensure connection is active
    EnsureConnected();

    // --- Example: Read and print server responses ---
    char response[];
    if(ReadMessage(response))
    {
        PrintFormat("[B/C Signals] Server Response: %s", CharArrayToString(response));
    }

    // --- Example: Open a BUY position ---
    if (/* your buy condition is met */)
    {
        double entry_price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        SendTradeSignal("BUY", _Symbol, entry_price);
    }

    // --- Example: Close a position ---
    if (/* your close condition is met */) 
    {
        // You must have stored the signal ID when you opened the position.
        int signal_to_close = 123; // Example ID
        double close_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        SendTradeSignal("CLOSE", _Symbol, close_price, signal_to_close);
    }
}
```

---

## 5. Generating SSL Certificates (for the Server)

Your Python server requires an SSL certificate and private key. For development or private use, you can generate a self-signed certificate using `openssl`.

Run this command in your server's terminal:

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -sha256 -days 365 -nodes -subj "/C=XX/ST=State/L=City/O=Organization/OU=OrgUnit/CN=your.server.ip"
```

This will create `key.pem` and `cert.pem`. Make sure the `SSL_CERT_PATH` and `SSL_KEY_PATH` in your `.env` file point to these files.