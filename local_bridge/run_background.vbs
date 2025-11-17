' VBScript to run bridge.py in the background (no console window)
' This script ensures the working directory is set correctly

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get the directory where this VBScript is located
script_path = fso.GetParentFolderName(WScript.ScriptFullName)

' CRITICAL: Set the working directory to the script location
' This ensures config.ini and other files are found correctly
WshShell.CurrentDirectory = script_path

' Construct the full paths
python_exe = script_path & "\venv\Scripts\pythonw.exe"
bridge_script = script_path & "\bridge.py"
config_file = script_path & "\config.ini"

' Pre-flight checks
If Not fso.FileExists(python_exe) Then
    MsgBox "ERROR: Python virtual environment not found!" & vbCrLf & vbCrLf & _
           "Expected: " & python_exe & vbCrLf & vbCrLf & _
           "Please run QUICKSTART.bat first.", vbCritical, "Local Bridge Error"
    WScript.Quit 1
End If

If Not fso.FileExists(bridge_script) Then
    MsgBox "ERROR: bridge.py not found!" & vbCrLf & vbCrLf & _
           "Expected: " & bridge_script, vbCritical, "Local Bridge Error"
    WScript.Quit 1
End If

If Not fso.FileExists(config_file) Then
    MsgBox "ERROR: config.ini not found!" & vbCrLf & vbCrLf & _
           "Expected: " & config_file & vbCrLf & vbCrLf & _
           "Please create the configuration file.", vbCritical, "Local Bridge Error"
    WScript.Quit 1
End If

' Build the command with proper quoting for paths with spaces
command = """" & python_exe & """ """ & bridge_script & """"

' Run the command
' 0 = hide window, False = don't wait for it to finish
WshShell.Run command, 0, False

' Write a startup indicator file
Set statusFile = fso.CreateTextFile(script_path & "\bridge_started.txt", True)
statusFile.WriteLine Now & " - Bridge started via VBS"
statusFile.Close

' Optional: Show success message (comment out for completely silent operation)
' MsgBox "Local Bridge started successfully in background.", vbInformation, "Local Bridge"