' VBScript to run a Python script in the background (no console window)

Set WshShell = CreateObject("WScript.Shell")

' Get the directory where this VBScript is located
Set fso = CreateObject("Scripting.FileSystemObject")
script_path = fso.GetParentFolderName(WScript.ScriptFullName)

' Construct the full path to the python executable and the bridge script
python_exe = script_path & "\venv\Scripts\pythonw.exe"
bridge_script = script_path & "\bridge.py"

' Build the command with proper quoting for paths that might contain spaces
command = """" & python_exe & """ """ & bridge_script & """"

' WshShell.Run command, 0 = hide window, False = don't wait for it to finish
WshShell.Run command, 0, False