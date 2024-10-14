'************************************************************************/
'* File Name       : StopRecording.vbs
'* Creation Date   : 2024-10-15 01:50:30
'* Author          : Hmily
'* Blog              : http://github.com/ihmily
'* Description     : This script is designed to terminate the process of a live
'************************************************************************/

Dim objWMIService, colProcesses, objProcess
Dim intResponse
strComputer = "."
On Error Resume Next
intResponse = MsgBox("确定要结束所有后台直播录制进程吗？", vbYesNo + vbQuestion, "确认结束进程")

If intResponse = vbYes Then
    Set objWMIService = GetObject("winmgmts:\\" & strComputer & "\root\cimv2")
    If Err.Number <> 0 Then
        Err.Clear
    End If

    Set colProcesses = objWMIService.ExecQuery("Select * from Win32_Process Where Name = 'ffmpeg.exe'")
    Set colProcesses2 = objWMIService.ExecQuery("Select * from Win32_Process Where Name = 'pythonw.exe'")
    Set colProcesses3 = objWMIService.ExecQuery("Select * from Win32_Process Where Name = 'DouyinLiveRecorder.exe'")
    If Err.Number <> 0 Then
        Err.Clear
    End If

    If Not objWMIService Is Nothing And Not colProcesses Is Nothing  And Not colProcesses2 Is Nothing Then
        If colProcesses2.Count = 0 And colProcesses3.Count = 0 Then
            MsgBox "没有找到录制程序的进程", vbExclamation, "提示信息"
            WScript.Quit(1)
        Else
            For Each objProcess in colProcesses
                objProcess.Terminate()
                If Err.Number <> 0 Then
                    objShell.Run "taskkill /f /im " & objProcess.Name, 0, True
                    Err.Clear
                End If                
            Next
        End If
    Else
        objShell.Run "taskkill /f /im " & objProcess.Name, 0, True
    End If
    MsgBox "已成功结束正在录制直播的进程！" & vbCrLf & "关闭此窗口30秒后自动停止录制程序", vbInformation, "提示信息"

    WScript.Sleep 10000
    If colProcesses3.Count <> 0 Then
        Set colProcesses_ = colProcesses3
    Else
        Set colProcesses_ = colProcesses2
    End If
    For Each objProcess in colProcesses_
        objProcess.Terminate()
        If Err.Number <> 0 Then
            objShell.Run "taskkill /f /im " & objProcess.Name, 0, True
            Err.Clear
        End If         
    Next
Else
    MsgBox "已取消结束录制操作", vbExclamation, "提示信息"
End If

On Error GoTo 0
Set objWMIService = Nothing
Set colProcesses = Nothing
Set colProcesses2 = Nothing
Set colProcesses3 = Nothing
Set objProcess = Nothing
Set objShell = Nothing