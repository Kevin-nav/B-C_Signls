# installer.py
# This script's only job is to create the Windows startup shortcut.
# It is called by install.bat and MUST be run using the Python executable
# from within the virtual environment where pywin32 is installed.

import os
import sys
import platform

def create_shortcut():
    """Creates a startup shortcut using the pywin32 library."""
    print("  - Attempting to create the startup shortcut...")
    
    if platform.system() != "Windows":
        print("  - INFO: Shortcut creation is only supported on Windows.")
        return True

    try:
        import win32com.client
    except ImportError:
        print("  - ERROR: The 'pywin32' library was not found in this Python environment.", file=sys.stderr)
        print("  - HINT: This script should be run automatically by install.bat.", file=sys.stderr)
        return False

    try:
        VBS_RUNNER_FILE = "run_background.vbs"
        SHORTCUT_NAME = "run_bridge.lnk"

        script_dir = os.path.dirname(os.path.abspath(__file__))
        target_path = os.path.join(script_dir, VBS_RUNNER_FILE)
        startup_folder = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
        shortcut_path = os.path.join(startup_folder, SHORTCUT_NAME)

        os.makedirs(startup_folder, exist_ok=True)

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(shortcut_path)
        shortcut.TargetPath = target_path
        shortcut.WorkingDirectory = script_dir
        shortcut.WindowStyle = 7
        shortcut.Description = "Start the AutoSig Local Bridge"
        shortcut.Save()

        print(f"  - SUCCESS: Shortcut created in your Startup folder.")
        return True

    except Exception as e:
        print(f"  - ERROR: Failed to create shortcut: {e}", file=sys.stderr)
        print("  - HINT: If this is a permission error, try running 'install.bat' as an administrator.", file=sys.stderr)
        return False

if __name__ == "__main__":
    if not create_shortcut():
        sys.exit(1) # Exit with a non-zero code to signal failure to the batch script