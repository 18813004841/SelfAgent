using System;
using System.IO;
using UnityEditor;
using UnityEditor.Compilation;
using UnityEngine;

// Temporary task bridge copied into the Unity project before opening it.
[InitializeOnLoad]
public static class Project37SessionBridge
{
    private static string DirectoryPath;
    private static bool Held;
    private static bool Exported;
    private static bool ExportFinished;
    private static bool CompileStarted;
    private static bool CompileFailed;
    private static int OwnerPid;
    private static double NextOwnerCheck;

    static Project37SessionBridge()
    {
        var dir = Environment.GetEnvironmentVariable("PROJECT37_SESSION_DIR");
        if (!string.IsNullOrWhiteSpace(dir) && File.Exists(Path.Combine(dir, "compile.result")))
        {
            var result = File.ReadAllText(Path.Combine(dir, "compile.result")).Trim();
            EditorApplication.delayCall += () => EditorApplication.Exit(result == "ok" ? 0 : 1);
        }
    }

    public static void Start()
    {
        DirectoryPath = Environment.GetEnvironmentVariable("PROJECT37_SESSION_DIR");
        if (string.IsNullOrWhiteSpace(DirectoryPath) || !Directory.Exists(DirectoryPath))
            throw new InvalidOperationException("Missing project37 session directory");
        if (!int.TryParse(Environment.GetEnvironmentVariable("PROJECT37_OWNER_PID"), out OwnerPid))
            throw new InvalidOperationException("Missing project37 owner PID");
        AssetDatabase.DisallowAutoRefresh();
        EditorApplication.LockReloadAssemblies();
        Held = true;
        CompilationPipeline.compilationStarted += OnCompilationStarted;
        CompilationPipeline.assemblyCompilationFinished += OnAssemblyFinished;
        CompilationPipeline.compilationFinished += OnCompilationFinished;
        EditorApplication.update += Poll;
        File.WriteAllText(Path.Combine(DirectoryPath, "ready"), "ok");
    }

    private static void Poll()
    {
        if (EditorApplication.timeSinceStartup >= NextOwnerCheck)
        {
            NextOwnerCheck = EditorApplication.timeSinceStartup + 10;
            try
            {
                using (var owner = System.Diagnostics.Process.GetProcessById(OwnerPid))
                    if (owner.HasExited) { Release(); EditorApplication.Exit(1); return; }
            }
            catch (ArgumentException) { Release(); EditorApplication.Exit(1); return; }
            catch (InvalidOperationException) { Release(); EditorApplication.Exit(1); return; }
        }
        if (File.Exists(Path.Combine(DirectoryPath, "cancel")))
        {
            Release();
            EditorApplication.Exit(1);
            return;
        }
        if (Exported || !File.Exists(Path.Combine(DirectoryPath, "export"))) return;
        Exported = true;
        try
        {
            Config2.FlatBuffersConfig.GenerateFromCommandLine();
            File.WriteAllText(Path.Combine(DirectoryPath, "export.ok"), "ok");
            ExportFinished = true;
            Release();
            CompilationPipeline.RequestScriptCompilation();
        }
        catch (Exception e)
        {
            File.WriteAllText(Path.Combine(DirectoryPath, "export.error"), e.ToString());
            Release();
            EditorApplication.Exit(1);
        }
    }

    private static void OnCompilationStarted(object context)
    {
        if (Exported) CompileStarted = true;
    }

    private static void OnAssemblyFinished(string assembly, CompilerMessage[] messages)
    {
        if (!Exported) return;
        foreach (var message in messages)
        {
            if (message.type != CompilerMessageType.Error) continue;
            CompileFailed = true;
            File.AppendAllText(Path.Combine(DirectoryPath, "compile.errors"), message.message + Environment.NewLine);
        }
    }

    private static void OnCompilationFinished(object context)
    {
        if (!ExportFinished || !CompileStarted) return;
        File.WriteAllText(Path.Combine(DirectoryPath, "compile.result"), CompileFailed ? "failed" : "ok");
        var exitCode = CompileFailed ? 1 : 0;
        EditorApplication.delayCall += () => EditorApplication.Exit(exitCode);
    }

    private static void Release()
    {
        if (!Held) return;
        Held = false;
        EditorApplication.UnlockReloadAssemblies();
        AssetDatabase.AllowAutoRefresh();
    }
}
