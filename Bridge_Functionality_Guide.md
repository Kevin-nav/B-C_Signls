# AutoSig Local Bridge - Functionality Guide

---

## 1. Overview

The AutoSig Local Bridge is a standalone Python application that acts as a highly reliable "middleman" or "proxy" between your MQL5 Expert Advisor (EA) running on your local machine and the main signal processing server running on your remote VPS.

Its primary purpose is to handle all network complexity, providing a simple and stable connection point for the EA, while managing a robust and persistent connection to the server.

---

## 2. Core Functionality

### A. Dual-Connection Architecture

The bridge operates by managing two separate TCP connections simultaneously:

1.  **Local Server for MQL5:**
    - It starts a TCP server that listens locally on your Windows machine (at `127.0.0.1:5050`).
    - Your MQL5 EA connects to this local server. This connection is extremely fast and reliable as it never leaves your machine.
    - It is built using `asyncio` and can handle connections from multiple EAs or charts at the same time.

2.  **Persistent Client for VPS:**
    - Upon startup, the bridge initiates a single, persistent TCP connection to your remote VPS server (e.g., `35.208.6.252:5200`).
    - It authenticates once with the server using the `secret_key` from the `config.ini` file and keeps this connection open indefinitely.

### B. Intelligent Message Routing

The bridge is more than just a simple relay. It intelligently manages the flow of information.

-   **Signal Forwarding:** When a signal is received from an MQL5 EA, the bridge places it in an internal queue and forwards it to the VPS over the persistent connection.
-   **Confirmation Routing:** When the VPS sends a confirmation message back, the bridge inspects the `client_msg_id` in the message. It uses this ID to find the *exact* MQL5 client that sent the original request and relays the confirmation back to that specific client.

This ensures that even if you are running multiple EAs on different charts, each one receives the correct confirmation for the signals it sends.

---

## 3. Reliability & Resilience Features

These features are built-in to ensure the system runs continuously without manual intervention.

-   **Automatic Reconnect:** If the connection to the VPS is lost for any reason (e.g., internet outage, server restart), the bridge will automatically attempt to reconnect every 10 seconds until the connection is re-established.
-   **Heartbeat Management:** The bridge sends a `ping` message to the VPS every 30 seconds. If the server doesn't respond, the bridge knows the connection is dead and triggers the auto-reconnect logic. This prevents "zombie" connections.
-   **Self-Healing Local Server:** If the bridge's local server fails to start for any reason (e.g., the port is temporarily in use), it will automatically retry every 10 seconds until it succeeds.
-   **Message Size Protection:** The bridge will immediately reject and close any connection that attempts to send a message larger than 4MB, protecting the system from malformed data or potential abuse.

---

## 4. User-Facing Features

These components are designed to make the bridge easy to install and manage for any user.

-   **One-Click Installation:** The `install.bat` script provides a professional, fully automated setup experience with clear, color-coded feedback.
-   **Automatic Startup:** Once installed, the bridge is registered with the Windows Startup folder, ensuring it launches automatically in the background every time you log in.
-   **On-Demand Status Check:** The `check_status.bat` utility provides a simple way to see if the bridge is currently `ACTIVE` or `NOT RUNNING`.
-   **Developer Debug Mode:** The `debug_run.bat` script allows developers to run the bridge in a visible console window to monitor live activity and troubleshoot issues.
