'********************************************************************************************/
'* 文件名称       : StopRecording.vbs
'* 创建日期       : 2024-10-15 01:50:30
'* 作者           : Hmily
'* GitHub         : http://github.com/ihmily
'* 描述           : 用于终止直播录制相关进程的脚本
'* 修订说明       : 2026-08 重写进程匹配与结束顺序，要点：
'*                  1. 本文件必须保存为 UTF-16 LE（带 BOM）编码，不能用 UTF-8——
'*                     wscript/cscript 按系统 ANSI 代码页解释 .vbs，UTF-8 保存会让中文提示乱码；
'*                  2. 程序专属 exe 按映像名匹配；python / ffmpeg 属通用映像名，必须锚定：
'*                     python 须命令行含入口脚本（main.py / gui.py / web.py / douyin-recorder），
'*                     ffmpeg 须「父进程为已识别录制主进程」或「路径/命令行锚定到程序目录」，
'*                     避免误杀其他程序的 ffmpeg/python 进程（含项目 venv 内的编辑器工具进程）；
'*                  3. 先结束录制主进程（连带子进程树），后清理残留 ffmpeg，
'*                     消除「先杀 ffmpeg -> 主进程下一轮重新拉起」的竞态窗口；
'*                  4. 静默模式：cscript //nologo StopRecording.vbs -y
'*                     （跳过确认框，状态输出到控制台，便于自动化调用）
'* 已知残余       : 以不含上述入口脚本特征的自定义方式启动的源码进程可能不被匹配，
'*                  此时应把本脚本与程序放在同一目录运行，或在命令行按 Ctrl+C 优雅停止
'********************************************************************************************/

Option Explicit

' 常量定义
' 程序专属 exe：映像名唯一，可安全按名匹配（与 build_exe.py 产出的三个 exe 对应）
Const APP_EXE_CLI = "DouyinLiveRecorder.exe"
Const APP_EXE_GUI = "DouyinLiveRecorder-GUI.exe"
Const APP_EXE_WEB = "DouyinLiveRecorder-Web.exe"
' 通用映像名进程：必须经锚定规则确认后才允许结束
Const PROCESS_FFMPEG = "ffmpeg.exe"
Const PROCESS_PYTHON = "python.exe"
Const PROCESS_PYTHONW = "pythonw.exe"
' 录制入口脚本名：python 进程命令行含其一（且前紧邻路径分隔符/空格/引号）才认定属于本程序
Const ENTRY_SCRIPTS = "main.py|gui.py|web.py"
' pip 安装的命令行入口（douyin-recorder / douyin-recorder-gui / douyin-recorder-web 的启动器）
Const ENTRY_SHIM_KEY = "douyin-recorder"
' 程序目录锚点关键字：ffmpeg 的路径/命令行含「脚本所在目录」或该关键字（大小写不敏感）才认定
Const APP_DIR_KEY = "douyinliverecorder"
' 结束录制主进程后，等待系统回收子进程的秒数
Const WAIT_SECONDS = 3

' 变量声明
Dim objWMIService, objShell, objFSO
Dim appDir        ' 脚本所在目录（程序根目录），作为 ffmpeg 的锚点之一
Dim silentMode    ' 静默模式：携带任意命令行参数时为 True
Dim intResponse
Dim recorderList  ' Dictionary：录制主进程 PID -> 进程对象
Dim ffmpegList    ' Dictionary：待清理 ffmpeg PID -> 进程对象

' 主程序
silentMode = (WScript.Arguments.Count > 0)
appDir = ""

On Error Resume Next
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
On Error GoTo 0

If objShell Is Nothing Or objFSO Is Nothing Then
    Call ShowMessage("无法创建脚本运行所需对象，请手动结束相关进程", vbExclamation)
    WScript.Quit(1)
End If

appDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

If silentMode Then
    intResponse = vbYes
Else
    intResponse = MsgBox("确定要结束所有直播录制进程吗？" & vbCrLf & _
                         "仅结束本程序相关进程（按程序名与程序目录匹配），不会影响其他程序。", _
                         vbYesNo + vbQuestion, "确认结束进程")
End If

If intResponse = vbYes Then
    Call InitializeWMIService()

    If objWMIService Is Nothing Then
        ' 备用方案：WMI 服务不可用时仅按程序专属映像名结束
        Call TerminateAllProcesses_CommandLine()
    Else
        Call StopRecordingProcesses()
    End If
Else
    Call ShowMessage("已取消结束录制操作", vbExclamation)
End If

Call Cleanup()
WScript.Quit(0)


'--------------------------------------------------------------------------------
' 过程：主停止流程（WMI 可用）
'--------------------------------------------------------------------------------
Sub StopRecordingProcesses()
    Set recorderList = CreateObject("Scripting.Dictionary")
    Set ffmpegList = CreateObject("Scripting.Dictionary")

    Call SafeCollectProcesses()

    If recorderList.Count = 0 And ffmpegList.Count = 0 Then
        Call ShowMessage("没有找到录制程序的进程", vbExclamation)
        Exit Sub
    End If

    Call ShowProgress("找到录制主进程 " & recorderList.Count & " 个、关联 ffmpeg " & _
                      ffmpegList.Count & " 个，开始结束...")

    ' 阶段1：先结束录制主进程。taskkill /t 连带结束其子进程树（含 ffmpeg），
    ' 避免主进程存活期间下一轮重新拉起 ffmpeg 的竞态
    Call TerminateProcesses(recorderList, True)

    ' 等待系统回收子进程后，清理仍存活的 ffmpeg（含此前遗留的孤儿进程）
    WScript.Sleep WAIT_SECONDS * 1000
    Call TerminateProcesses(ffmpegList, False)

    ' 复核：重新枚举一次，如实报告结果
    Set recorderList = CreateObject("Scripting.Dictionary")
    Set ffmpegList = CreateObject("Scripting.Dictionary")
    Call SafeCollectProcesses()

    If recorderList.Count = 0 And ffmpegList.Count = 0 Then
        Call ShowMessage("已成功结束所有直播录制进程！", vbInformation)
    Else
        Call ShowMessage("仍有 " & (recorderList.Count + ffmpegList.Count) & _
                         " 个相关进程未能结束，可能需要以管理员身份运行本脚本后重试", vbExclamation)
    End If
End Sub


'--------------------------------------------------------------------------------
' 过程：枚举并归类相关进程（查询失败时集合保持为空，由上层按「未找到」处理）
'--------------------------------------------------------------------------------
Sub SafeCollectProcesses()
    On Error Resume Next
    Err.Clear
    Call CollectProcesses()
    If Err.Number <> 0 Then Err.Clear
    On Error GoTo 0
End Sub


'--------------------------------------------------------------------------------
' 过程：枚举并归类相关进程
'       程序专属 exe 一律命中；python 须命中入口脚本；ffmpeg 须二次确认（父进程或路径锚定）
'--------------------------------------------------------------------------------
Sub CollectProcesses()
    Dim colProcesses, objProcess, allFfmpeg
    Dim pid, procName, cmdLine, exePath, parentPid, item

    Set allFfmpeg = CreateObject("Scripting.Dictionary")

    Set colProcesses = objWMIService.ExecQuery( _
        "Select * from Win32_Process Where Name='" & PROCESS_FFMPEG & "'" & _
        " Or Name='" & PROCESS_PYTHON & "'" & _
        " Or Name='" & PROCESS_PYTHONW & "'" & _
        " Or Name='" & APP_EXE_CLI & "'" & _
        " Or Name='" & APP_EXE_GUI & "'" & _
        " Or Name='" & APP_EXE_WEB & "'")

    ' 第一遍：归类录制主进程，ffmpeg 先暂存待二次确认
    For Each objProcess In colProcesses
        procName = "" : pid = -1 : cmdLine = "" : exePath = "" : parentPid = -1
        On Error Resume Next
        procName = LCase(objProcess.Name)
        pid = CLng(objProcess.ProcessId)
        parentPid = CLng(objProcess.ParentProcessId)
        If Not IsNull(objProcess.CommandLine) Then cmdLine = CStr(objProcess.CommandLine)
        If Not IsNull(objProcess.ExecutablePath) Then exePath = CStr(objProcess.ExecutablePath)
        On Error GoTo 0

        If pid < 0 Or procName = "" Then
            ' 属性读取失败，跳过该进程
        ElseIf procName = LCase(APP_EXE_CLI) Or procName = LCase(APP_EXE_GUI) Or procName = LCase(APP_EXE_WEB) Then
            recorderList.Add pid, objProcess
        ElseIf procName = LCase(PROCESS_PYTHON) Or procName = LCase(PROCESS_PYTHONW) Then
            If IsRecorderPython(cmdLine) Then recorderList.Add pid, objProcess
        ElseIf procName = LCase(PROCESS_FFMPEG) Then
            allFfmpeg.Add pid, Array(objProcess, parentPid, cmdLine, exePath)
        End If
    Next

    ' 第二遍：ffmpeg 须「父进程为录制主进程」或「路径/命令行锚定到程序目录」才命中
    For Each pid In allFfmpeg.Keys
        item = allFfmpeg(pid)
        Set objProcess = item(0)
        parentPid = item(1)
        cmdLine = item(2)
        exePath = item(3)
        If recorderList.Exists(parentPid) Or IsPathAnchored(cmdLine) Or IsPathAnchored(exePath) Then
            ffmpegList.Add pid, objProcess
        End If
    Next
End Sub


'--------------------------------------------------------------------------------
' 函数：判断 python 进程是否在运行本程序
'       命中条件（其一）：命令行含入口脚本 main.py / gui.py / web.py（其前紧邻路径分隔符、
'       空格或引号，避免误匹配 test_main.py 之类同名子串）；或含 pip 启动器名 douyin-recorder。
'       刻意不按「项目目录」匹配——venv 内的工具进程（isort 语言服务器等）路径同样指向
'       项目目录，按目录匹配会误杀它们。
'--------------------------------------------------------------------------------
Function IsRecorderPython(cmdLine)
    Dim s, names, i, pos, prev
    IsRecorderPython = False
    If IsNull(cmdLine) Then Exit Function
    s = LCase(CStr(cmdLine))
    If s = "" Then Exit Function

    If InStr(1, s, ENTRY_SHIM_KEY) > 0 Then
        IsRecorderPython = True
        Exit Function
    End If

    names = Split(ENTRY_SCRIPTS, "|")
    For i = 0 To UBound(names)
        pos = InStr(1, s, names(i))
        Do While pos > 0
            If pos = 1 Then
                IsRecorderPython = True
                Exit Function
            End If
            prev = Mid(s, pos - 1, 1)
            If prev = "\" Or prev = "/" Or prev = " " Or prev = Chr(34) Then
                IsRecorderPython = True
                Exit Function
            End If
            pos = InStr(pos + 1, s, names(i))
        Loop
    Next
End Function


'--------------------------------------------------------------------------------
' 函数：判断进程路径 / 命令行是否锚定到本程序（ffmpeg 二次确认用）
'       （包含脚本所在目录，或包含程序名关键字；大小写不敏感）
'--------------------------------------------------------------------------------
Function IsPathAnchored(pathText)
    Dim s
    IsPathAnchored = False
    If IsNull(pathText) Then Exit Function
    s = LCase(Trim(CStr(pathText)))
    If s = "" Then Exit Function
    ' 目录锚点须深于盘符根，避免退化为「盘符:\」匹配一切命令行
    If Len(appDir) > 3 Then
        If InStr(1, s, LCase(appDir), vbTextCompare) > 0 Then
            IsPathAnchored = True
            Exit Function
        End If
    End If
    If InStr(1, s, APP_DIR_KEY, vbTextCompare) > 0 Then IsPathAnchored = True
End Function


'--------------------------------------------------------------------------------
' 过程：结束进程集合。killTree=True 时首选 taskkill /t 连带子进程树（录制主进程用），
'       失败回退 WMI 单进程终止；killTree=False 时先 WMI Terminate、失败回退 taskkill
'--------------------------------------------------------------------------------
Sub TerminateProcesses(procDict, killTree)
    Dim pid, objProcess, rc
    For Each pid In procDict.Keys
        Set objProcess = procDict(pid)
        If killTree Then
            rc = 1
            If Not objShell Is Nothing Then
                rc = objShell.Run("taskkill /f /t /pid " & pid, 0, True)
            End If
            ' taskkill 返回 0=成功；128=进程已不存在（可能已被连带结束）；其余回退 WMI 终止
            If rc <> 0 And rc <> 128 Then
                If Not TerminateByWmi(objProcess) And Not objShell Is Nothing Then
                    objShell.Run "taskkill /f /pid " & pid, 0, True
                End If
            End If
        Else
            If Not TerminateByWmi(objProcess) And Not objShell Is Nothing Then
                objShell.Run "taskkill /f /pid " & pid, 0, True
            End If
        End If
    Next
End Sub


'--------------------------------------------------------------------------------
' 函数：用 WMI 终止单个进程，返回是否成功（进程已不存在时按失败处理，由上层回退）
'--------------------------------------------------------------------------------
Function TerminateByWmi(objProcess)
    Dim rc
    TerminateByWmi = False
    If objWMIService Is Nothing Then Exit Function
    On Error Resume Next
    rc = objProcess.Terminate()
    On Error GoTo 0
    If Not IsEmpty(rc) Then
        If rc = 0 Then TerminateByWmi = True
    End If
End Function


'--------------------------------------------------------------------------------
' 过程：初始化 WMI 服务（失败时置 Nothing，由上层走命令行兜底）
'--------------------------------------------------------------------------------
Sub InitializeWMIService()
    Set objWMIService = Nothing
    On Error Resume Next
    Set objWMIService = GetObject("winmgmts:\\.\root\cimv2")
    On Error GoTo 0
End Sub


'--------------------------------------------------------------------------------
' 过程：命令行方式结束所有进程（备用方案，WMI 不可用时）
'       仅按程序专属映像名结束（/t 连带子进程树，其 ffmpeg / python 子进程一并结束）；
'       python / ffmpeg 为通用映像名，无法在此安全过滤，不做无差别击杀
'--------------------------------------------------------------------------------
Sub TerminateAllProcesses_CommandLine()
    If objShell Is Nothing Then
        Call ShowMessage("无法创建 Shell 对象，请手动结束相关进程", vbExclamation)
        Exit Sub
    End If
    objShell.Run "taskkill /f /t /im " & APP_EXE_CLI, 0, True
    objShell.Run "taskkill /f /t /im " & APP_EXE_GUI, 0, True
    objShell.Run "taskkill /f /t /im " & APP_EXE_WEB, 0, True
    Call ShowMessage("已按程序名结束录制进程（WMI 不可用，未匹配 python / ffmpeg 通用名进程）", vbInformation)
End Sub


'--------------------------------------------------------------------------------
' 过程：输出消息（静默模式写控制台，交互模式弹对话框）
'--------------------------------------------------------------------------------
Sub ShowMessage(msgText, msgIcon)
    If silentMode Then
        WScript.Echo msgText
    Else
        MsgBox msgText, msgIcon, "提示信息"
    End If
End Sub


'--------------------------------------------------------------------------------
' 过程：输出进度信息（仅静默模式输出，交互模式不打断用户）
'--------------------------------------------------------------------------------
Sub ShowProgress(msgText)
    If silentMode Then WScript.Echo msgText
End Sub


'--------------------------------------------------------------------------------
' 过程：清理对象资源
'--------------------------------------------------------------------------------
Sub Cleanup()
    Set recorderList = Nothing
    Set ffmpegList = Nothing
    Set objWMIService = Nothing
    Set objShell = Nothing
    Set objFSO = Nothing
End Sub
