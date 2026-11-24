using Microsoft.AspNetCore.Http;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace NovelAI.MediaSuite;

internal sealed partial class BrowserHost
{
    internal Func<string> FindLauncher { get; set; }
    internal Action<string> ReplaceLauncher { get; set; }
    private sealed record TabReply(string tab, string id, string reason);
    private sealed record UpdateRun(string id, string phase, string message, ApplicationUpdates.Plan plan = null)
    {
        [JsonIgnore] public bool Active => phase is "checking" or "preparing" or "applying" or "restarting";
    }
    private UpdateRun update = new("", "idle", "");
    private readonly Dictionary<string,int> tabs = new();
    private readonly HashSet<string> readyTabs = new();
    private TaskCompletionSource changed = NewSignal();
    private static TaskCompletionSource NewSignal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private UpdateRun UpdateStatus() { lock (requestLock) return update; }
    internal bool Updating => UpdateStatus().Active;

    // Called with requestLock held. Wake every open profile, including background tabs.
    private void SetUpdate(UpdateRun state)
    {
        update = state;
        var previous = changed;
        changed = NewSignal();
        previous.TrySetResult();
    }

    private async Task TabPresence(HttpContext context)
    {
        string tab = context.Request.Query["tab"];
        if (!Guid.TryParseExact(tab, "D", out _)) tab = Guid.NewGuid().ToString();
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(closing.Token, context.RequestAborted);
        var ct = lifetime.Token;
        lock (requestLock) tabs[tab] = tabs.GetValueOrDefault(tab) + 1;
        try
        {
            context.Response.ContentType = "text/event-stream";
            UpdateRun last = null;
            while (!ct.IsCancellationRequested)
            {
                UpdateRun current;
                Task signal;
                lock (requestLock) { current = update; signal = changed.Task; }
                string data = current == last ? ": keepalive\n\n"
                    : "event: suite-update\ndata: " + JsonSerializer.Serialize(current) + "\n\n";
                await context.Response.WriteAsync(data, ct);
                await context.Response.Body.FlushAsync(ct);
                last = current;
                try { await signal.WaitAsync(TimeSpan.FromSeconds(5), ct); } catch (TimeoutException) { }
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { }
        catch (IOException) { }
        finally { lock (requestLock) { if (--tabs[tab] == 0) tabs.Remove(tab); } }
    }

    private void StartUpdate(string initiator)
    {
        lock (requestLock)
        {
            if (update.Active) return;
            readyTabs.Clear();
            var id = Guid.NewGuid().ToString();
            SetUpdate(new(id, "checking", "Checking all suite programs…"));
            _ = Task.Run(() => RunUpdate(id, initiator));
        }
    }

    private void AnswerUpdate(TabReply reply)
    {
        lock (requestLock)
        {
            if (update.id != reply.id || update.phase != "preparing") return;
            if (string.IsNullOrWhiteSpace(reply.reason)) readyTabs.Add(reply.tab);
            else SetUpdate(update with {phase = "deferred", message = reply.reason[..Math.Min(reply.reason.Length, 300)]});
        }
    }

    private async Task RunUpdate(string id, string initiator)
    {
        TaskCompletionSource exclusive = null;
        try
        {
            await Updates.Check();
            string replacement = FindLauncher?.Invoke();
            var plan = Updates.Prepared(replacement != null);
            lock (requestLock) SetUpdate(new(id, "preparing", "Saving your place in the open suite tabs…", plan));
            var deadline = System.Diagnostics.Stopwatch.StartNew();
            while (true)
            {
                lock (requestLock)
                {
                    if (update.id != id || update.phase != "preparing") return;
                    if (tabs.ContainsKey(initiator) && readyTabs.Contains(initiator) && tabs.Keys.All(readyTabs.Contains)
                        && activeRequests == tabs.Values.Sum() && maintenance == null)
                    {
                        maintenance = exclusive = NewSignal();
                        SetUpdate(update with {phase = "applying", message = "Applying verified updates…"});
                        break;
                    }
                    if (deadline.Elapsed > TimeSpan.FromSeconds(45))
                    {
                        SetUpdate(update with {phase = "deferred", message = "A suite tab or operation is still busy. Return to that tab, finish the active work, then press Update Media Suite again."});
                        return;
                    }
                }
                await Task.Delay(100, closing.Token);
            }
            await Updates.ApplyFromTab();
            var result = Updates.Applied(plan);
            lock (requestLock)
            {
                if (replacement == null) SetUpdate(update with {phase = "done", message = "Update check finished. See each program’s result below.", plan = result});
                else
                {
                    // No new requests can enter between draining the proxies and releasing the listeners.
                    handingOff = true;
                    SetUpdate(update with {phase = "restarting", message = "Reconnecting this tab to the updated launcher…"});
                }
            }
            if (replacement != null) ReplaceLauncher(replacement);
        }
        catch (Exception e)
        {
            lock (requestLock) if (update.id == id)
            {
                handingOff = false;
                SetUpdate(update with {phase = "error", message = e.GetBaseException().Message});
            }
        }
        finally
        {
            if (exclusive != null) lock (requestLock) { maintenance = null; exclusive.TrySetResult(); }
        }
    }
}
