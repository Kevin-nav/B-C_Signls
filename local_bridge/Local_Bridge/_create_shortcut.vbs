
        On Error Resume Next
        Set oWS = WScript.CreateObject("WScript.Shell")
        Set oLink = oWS.CreateShortcut("C:\Users\MORO\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\run_bridge.lnk")
        oLink.TargetPath = "C:\Users\MORO\Project\EA\AutoSig\local_bridge\run_background.vbs"
        oLink.WindowStyle = 7
        oLink.Description = "Start the AutoSig Local Bridge"
        oLink.WorkingDirectory = "C:\Users\MORO\Project\EA\AutoSig\local_bridge"
        oLink.Save
        If Err.Number <> 0 Then
            WScript.StdErr.WriteLine "VBScript Error: " & Err.Description
            WScript.Quit(1)
        End If
        