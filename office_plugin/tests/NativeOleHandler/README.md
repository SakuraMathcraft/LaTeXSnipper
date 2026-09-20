# 原生 OLE handler 行为测试

直接加载指定架构的 handler DLL，通过 `DllGetClassObject` 创建正式 COM 对象，不修改注册表。使用真实 EMF 与包含完整字体快照、中文和 LaTeX 的 schema 3 payload，验证结构化存储加载、物理尺寸、EMF 提取、保存重开，以及无效字号被拒绝后原公式保持可用。

测试前关闭 Office；若发现待插入 payload，测试拒绝运行，避免消费用户的待处理公式。x64 与 Win32 各自加载同架构 DLL：

```powershell
$nativeBuild = 'D:\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe'
foreach ($architecture in @('x64', 'Win32')) {
    & $nativeBuild office_plugin/tests/NativeOleHandler/NativeOleHandler.vcxproj /p:Configuration=Release "/p:Platform=$architecture" /v:minimal /nologo
    if ($LASTEXITCODE -ne 0) { throw 'Native test build failed.' }
    & "office_plugin/tests/NativeOleHandler/bin/$architecture/NativeOleHandler.exe" (Resolve-Path "office_plugin/hosts/OleFormulaObjectNative/bin/$architecture/Release/LaTeXSnipper.OfficePlugin.OleFormulaObject.Handler.dll")
    if ($LASTEXITCODE -ne 0) { throw 'Native handler test failed.' }
}
```

handler 本身先由 `office_plugin/tools/Build-NativeOleHandler.ps1` 编译。本测试不代表 Word/PPT 的注册激活、双击编辑或转换链路已通过，这些须使用匹配的托管插件与 handler 在 Office 中另行验证。
