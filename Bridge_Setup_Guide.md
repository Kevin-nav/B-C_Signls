# AutoSig Local Bridge - User & Setup Guide

---

## 1. Introduction

Welcome to the AutoSig Local Bridge!

This bridge is a small but powerful background application that runs on your local Windows machine. Its purpose is to create a stable, reliable, and permanent connection between your MetaTrader 5 (MT5) Expert Advisor (EA) and the main signal server on the VPS.

By handling all the complex networking tasks like authentication, heartbeats, and reconnections, it allows your EA to simply send trading signals without worrying about network issues.

**You only need to perform the setup process once.**

---

## 2. Files in the `local_bridge` Folder

When you open the `local_bridge` folder, you will see the following files. Here is what they do:

| File Name              | File Type (in Windows)     | Description                                                                        |
| ---------------------- | -------------------------- | ---------------------------------------------------------------------------------- |
| `install.bat`          | Windows Batch File         | **The main installer.** You only need to double-click this file once to set everything up. |
| `run_background.vbs`   | VBScript Script File       | Runs the bridge silently in the background. The startup shortcut points to this.    |
| `check_status.bat`     | Windows Batch File         | A utility you can run anytime to check if the bridge is currently active.         |
| `debug_run.bat`        | Windows Batch File         | **For developers.** Runs the bridge in a visible console to help with debugging.     |
| `bridge.py`            | Python File                | The core application logic for the bridge.                                         |
| `installer.py`         | Python File                | A helper script used by `install.bat` to create the startup shortcut.              |
| `config.ini`           | Configuration settings     | Contains all settings for the bridge (IPs, ports, secret key).                   |
| `requirements.txt`     | Text Document              | A list of Python libraries required by the installer.                              |

---

## 3. One-Time Installation

Follow these steps to install and configure the bridge on your Windows machine.

**Step 1: Configure the Bridge**

-   Before running the installer, open the `config.ini` file with a text editor.
-   Ensure the following values are correct:
    -   `vps_host`: Should be the IP address of your remote server (e.g., `35.208.6.252`).
    -   `secret_key`: Must exactly match the secret key used by your server.

**Step 2: Run the Installer**

-   Navigate to the `local_bridge` folder.
-   **Double-click the `install.bat` file.**
-   A green console window will appear with the title "AutoSig Local Bridge Installer".
-   Follow the on-screen prompts and press any key to advance through the phases.

This script will automatically create a Python virtual environment, install the necessary `pywin32` library, and create a shortcut in your Windows Startup folder. This shortcut ensures the bridge will launch automatically every time you log into Windows.

---

## 4. How to Use the Bridge

### Starting the Bridge

-   **Automatically (Recommended):** After running the installer, simply restart your computer or log out and log back in. The bridge will start automatically in the background.
-   **Manually:** If you need to start the bridge immediately without restarting, just double-click the `run_background.vbs` file.

### Checking the Bridge Status

-   At any time, you can double-click the **`check_status.bat`** file.
-   It will show a clear, color-coded message indicating if the bridge is `ACTIVE` or `NOT RUNNING`.

---

## 5. MQL5 Expert Advisor Configuration

To connect your EA to the bridge, make sure the following input parameters in your MetaTrader 5 terminal are set correctly:

-   `Inp_BridgeHost`: **`127.0.0.1`**
-   `Inp_BridgePort`: **`31415`**

Your EA should now connect to the local bridge, not directly to the VPS.

---

## 6. Troubleshooting

**Problem:** The `check_status.bat` script shows "NOT RUNNING".

-   **Solution:** Double-click `run_background.vbs` to start it manually. If it still doesn't work, run `debug_run.bat` and provide the output to your developer for analysis.

**Problem:** My EA gives a "Connection Refused" or `errno=10061` error.

-   **Solution:** This means the bridge is not running. Use `check_status.bat` to confirm its status and `run_background.vbs` to start it.
