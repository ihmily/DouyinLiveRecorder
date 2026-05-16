'********************************************************************************************/
'* 文件名称       : StopRecording.vbs
'* 创建日期     : 2024-10-15 01:50:30
'* 作者            : Hmily
'* GitHub        : http://github.com/ihmily
'* 描述            : 用于终止直播录制相关进程的脚本
'********************************************************************************************/

Option Explicit

' 常量定义
Const PROCESS_FFMPEG = "ffmpeg.exe"
Const PROCESS_PYTHON = "pythonw.exe"
Const PROCESS_APP = "DouyinLiveRecorder.exe"
Const WAIT_SECONDS = 10

' 变量声明
Dim objWMIService, objShell
Dim colProcesses_FFmpeg, colProcesses_Python, colProcesses_App
Dim objProcess, colProcesses_
Dim intResponse
Dim strComputer

' 主程序
On Error Resume Next

strComputer = "."
Set objShell = CreateObject("WScript.Shell")

' 显示确认对话框
intResponse = MsgBox("确定要结束所有后台直播录制进程吗？", vbYesNo + vbQuestion, "确认结束进程")

If intResponse = vbYes Then
    ' 初始化 WMI 服务
    Call InitializeWMIService()
    
    If objWMIService Is Nothing Then
        ' 备用方案：使用命令行方式终止进程
        Call TerminateAllProcesses_CommandLine()
        WScript.Quit(0)
    End If
    
    ' 查询所有相关进程
    Call QueryProcesses()
    
    ' 检查是否有正在运行的录制进程
    If Not HasRunningProcesses() Then
        MsgBox "没有找到录制程序的进程", vbExclamation, "提示信息"
        Call Cleanup()
        WScript.Quit(1)
    End If
    
    ' 阶段1：先终止 ffmpeg 进程
    Call TerminateProcessCollection(colProcesses_FFmpeg, PROCESS_FFMPEG)
    
    ' 等待一段时间，确保 ffmpeg 进程完全退出
    WScript.Sleep WAIT_SECONDS * 1000
    
    ' 阶段2：终止 Python/GUI 进程
    If colProcesses_App.Count > 0 Then
        Call TerminateProcessCollection(colProcesses_App, PROCESS_APP)
    Else
        Call TerminateProcessCollection(colProcesses_Python, PROCESS_PYTHON)
    End If
    
    ' 显示完成消息
    MsgBox "已成功结束正在录制直播的进程！" & vbCrLf & _
           "录制程序将在后台自动关闭", vbInformation, "提示信息"
Else
    MsgBox "已取消结束录制操作", vbExclamation, "提示信息"
End If

' 清理资源
Call Cleanup()

On Error GoTo 0
WScript.Quit(0)


'--------------------------------------------------------------------------------
' 函数：初始化 WMI 服务
'--------------------------------------------------------------------------------
Sub InitializeWMIService()
    Set objWMIService = GetObject("winmgmts:\\" & strComputer & "\root\cimv2")
    If Err.Number <> 0 Then
        Err.Clear
        Set objWMIService = Nothing
    End If
End Sub


'--------------------------------------------------------------------------------
' 函数：查询所有相关进程
'--------------------------------------------------------------------------------
Sub QueryProcesses()
    If objWMIService Is Nothing Then Exit Sub
    
    Set colProcesses_FFmpeg = objWMIService.ExecQuery( _
        "Select * from Win32_Process Where Name = '" & PROCESS_FFMPEG & "'")
    
    Set colProcesses_Python = objWMIService.ExecQuery( _
        "Select * from Win32_Process Where Name = '" & PROCESS_PYTHON & "'")
    
    Set colProcesses_App = objWMIService.ExecQuery( _
        "Select * from Win32_Process Where Name = '" & PROCESS_APP & "'")
End Sub


'--------------------------------------------------------------------------------
' 函数：检查是否有正在运行的进程
'--------------------------------------------------------------------------------
Function HasRunningProcesses()
    HasRunningProcesses = False
    
    If objWMIService Is Nothing Then
        HasRunningProcesses = (colProcesses_App.Count > 0 Or colProcesses_Python.Count > 0)
        Exit Function
    End If
    
    If Not colProcesses_FFmpeg Is Nothing Then
        If colProcesses_FFmpeg.Count > 0 Then
            HasRunningProcesses = True
            Exit Function
        End If
    End If
    
    If Not colProcesses_App Is Nothing Then
        If colProcesses_App.Count > 0 Then
            HasRunningProcesses = True
            Exit Function
        End If
    End If
    
    If Not colProcesses_Python Is Nothing Then
        If colProcesses_Python.Count > 0 Then
            HasRunningProcesses = True
        End If
    End If
End Function


'--------------------------------------------------------------------------------
' 过程：终止指定进程集合中的所有进程
'--------------------------------------------------------------------------------
Sub TerminateProcessCollection(colProcesses, processName)
    If colProcesses Is Nothing Then Exit Sub
    
    Dim objProc
    For Each objProc In colProcesses
        On Error Resume Next
        objProc.Terminate()
        
        If Err.Number <> 0 Then
            ' 备用方案：使用 taskkill 命令
            Err.Clear
            objShell.Run "taskkill /f /t /im " & processName, 0, True
        End If
        On Error GoTo 0
    Next
End Sub


'--------------------------------------------------------------------------------
' 过程：使用命令行方式终止所有进程（备用方案）
'--------------------------------------------------------------------------------
Sub TerminateAllProcesses_CommandLine()
    ' 终止 ffmpeg 进程
    objShell.Run "taskkill /f /t /im " & PROCESS_FFMPEG, 0, True
    
    ' 终止 Python 进程
    objShell.Run "taskkill /f /t /im " & PROCESS_PYTHON, 0, True
    
    ' 终止应用程序进程
    objShell.Run "taskkill /f /t /im " & PROCESS_APP, 0, True
    
    MsgBox "已使用命令行方式结束录制进程", vbInformation, "提示信息"
End Sub


'--------------------------------------------------------------------------------
' 过程：清理对象资源
'--------------------------------------------------------------------------------
Sub Cleanup()
    Set colProcesses_FFmpeg = Nothing
    Set colProcesses_Python = Nothing
    Set colProcesses_App = Nothing
    Set objProcess = Nothing
    Set colProcesses_ = Nothing
    Set objWMIService = Nothing
    Set objShell = Nothing
End Sub
