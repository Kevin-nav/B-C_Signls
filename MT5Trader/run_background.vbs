' VBScript to run the MT5Trader server in the background (no console window)
' NOTE: This script assumes you have already run run.bat at least once
' to create the virtual environment and install dependencies.

Set WshShell = CreateObject("WScript.Shell")

' Get the directory where this VBScript is located
Set fso = CreateObject("Scripting.FileSystemObject")
script_path = fso.GetParentFolderName(WScript.ScriptFullName)

' Construct the full path to the windowless python executable and the server script
python_exe = script_path & "\venv\Scripts\pythonw.exe"
server_script = script_path & "\trade_server.py"

' Check if the pythonw.exe exists before trying to run it
if not fso.FileExists(python_exe) then
    MsgBox "Error: pythonw.exe not found." & vbCrLf & "Please run run.bat first to set up the virtual environment.", vbCritical, "MT5Trader Startup Error"
    WScript.Quit
end if

' Build the command with proper quoting for paths that might contain spaces
command = """" & python_exe & """ """ & server_script & """"

' WshShell.Run command, 0 = hide window, False = don't wait for it to finish
WshShell.Run command, 0, False

Set WshShell = Nothing
Set fso = Nothing
