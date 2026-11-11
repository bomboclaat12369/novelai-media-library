using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace NovelAI.MediaSuite;

// Each program has its own browser origin. Only the suite page may frame it.
internal sealed class ApplicationProxy : IDisposable
{
    private readonly Section section;
    private readonly string parent;
    private readonly HttpClient client;
    internal Uri Address { get; set; }
    internal volatile Uri Upstream;
    private static readonly string[] RequestHeaders = {"Accept","Range","If-Range","If-None-Match","If-Modified-Since","X-Review-Token","X-Game-Token"};
    private static readonly string[] ResponseHeaders = {"Accept-Ranges","Cache-Control","ETag","Referrer-Policy","X-Content-Type-Options","X-NovelAI-Filename"};

    internal ApplicationProxy(Section section, Uri shell)
    {
        this.section = section;
        parent = shell.GetLeftPart(UriPartial.Authority);
        var handler = new SocketsHttpHandler {
            UseProxy = false, AllowAutoRedirect = false, UseCookies = false, ConnectTimeout = TimeSpan.FromSeconds(4)
        };
        // The Python game server has a five-connection listen queue on Windows.
        if (section == Section.AfterHours) handler.MaxConnectionsPerServer = 4;
        client = new HttpClient(handler) {Timeout = Timeout.InfiniteTimeSpan};
    }

    private async Task<HttpResponseMessage> Send(HttpRequest req, Uri backend, string raw, CancellationToken cancellation)
    {
        string origin = backend.GetLeftPart(UriPartial.Authority);
        bool read = req.Method is "GET" or "HEAD" && req.ContentLength.GetValueOrDefault() == 0;
        for (int attempt = 0; ; attempt++)
        {
            using var outgoing = new HttpRequestMessage(new HttpMethod(req.Method), origin + raw);
            foreach (string header in RequestHeaders)
                if (req.Headers.TryGetValue(header, out var value)) outgoing.Headers.TryAddWithoutValidation(header, value.ToArray());
            if (req.Headers.ContainsKey("Origin")) outgoing.Headers.TryAddWithoutValidation("Origin", origin);
            if (!read && (req.ContentLength.HasValue || req.Method == "POST"))
            {
                outgoing.Content = new StreamContent(req.Body);
                outgoing.Content.Headers.ContentLength = req.ContentLength ?? 0;
                if (req.ContentType != null) outgoing.Content.Headers.TryAddWithoutValidation("Content-Type", req.ContentType);
            }
            bool retry = read && attempt < 2;
            try
            {
                var reply = await client.SendAsync(outgoing, HttpCompletionOption.ResponseHeadersRead, cancellation);
                if (!retry || reply.StatusCode is not (HttpStatusCode.BadGateway or HttpStatusCode.ServiceUnavailable or HttpStatusCode.GatewayTimeout))
                    return reply;
                reply.Dispose();
            }
            catch (Exception error) when (retry && !cancellation.IsCancellationRequested && error is HttpRequestException or IOException or OperationCanceledException)
            {
                Trace.TraceWarning("{0} upstream read interrupted: {1}", section, error.GetBaseException().Message);
            }
            await Task.Delay(150 * (attempt + 1), cancellation);
        }
    }

    internal async Task Handle(HttpContext context)
    {
        var req = context.Request;
        var res = context.Response;
        var backend = Upstream;
        if (backend == null || Address == null) { res.StatusCode = 503; return; }
        string self = Address.GetLeftPart(UriPartial.Authority);
        string site = req.Headers["Sec-Fetch-Site"];
        bool fromShell = req.Method == "GET" && req.Headers["Sec-Fetch-Dest"] == "iframe" &&
            Uri.TryCreate(req.Headers.Referer, UriKind.Absolute, out var referrer) && referrer.GetLeftPart(UriPartial.Authority) == parent;
        if ((req.Headers.ContainsKey("Origin") && req.Headers.Origin != self) ||
            ((site == "cross-site" || site == "same-site") && !fromShell))
        { res.StatusCode = 403; return; }
        if (req.Method is not ("GET" or "HEAD" or "POST" or "DELETE" or "OPTIONS")) { res.StatusCode = 405; return; }
        if (req.Method is "POST" or "DELETE" && req.Headers.Origin != self) { res.StatusCode = 403; return; }
        if (req.Path == "/_media-suite/battles.js" && section == Section.Library && req.Method == "GET")
        { await BrowserHost.Asset(context, "battles.js", "text/javascript; charset=utf-8"); return; }
        string raw = context.Features.Get<IHttpRequestFeature>()?.RawTarget;
        if (string.IsNullOrEmpty(raw) || !raw.StartsWith('/') || raw.StartsWith("//") || raw.Contains('\\'))
        { res.StatusCode = 400; return; }
        if (req.Headers.ContainsKey("Transfer-Encoding") && !req.ContentLength.HasValue) { res.StatusCode = 411; return; }
        try
        {
            using var reply = await Send(req, backend, raw, context.RequestAborted);
            res.StatusCode = (int)reply.StatusCode;
            foreach (var header in ResponseHeaders)
                if (reply.Headers.TryGetValues(header, out var values)) res.Headers[header] = string.Join(", ", values);
            if (reply.Headers.Location != null)
            {
                var location = new Uri(backend, reply.Headers.Location);
                if (location.GetLeftPart(UriPartial.Authority) != backend.GetLeftPart(UriPartial.Authority)) { res.StatusCode = 502; return; }
                res.Headers.Location = self + location.PathAndQuery + location.Fragment;
            }
            foreach (var h in reply.Content.Headers)
                if (h.Key is "Content-Type" or "Content-Disposition" or "Content-Range" or "Last-Modified" or "Content-Encoding")
                    res.Headers[h.Key] = string.Join(", ", h.Value);
            string policy = reply.Headers.TryGetValues("Content-Security-Policy", out var policies) ? string.Join("; ", policies) : "";
            // Keep script nonces, media restrictions and sandbox directives from the original response.
            policy = Regex.Replace(policy, @"(?:^|;)\s*frame-ancestors\s+[^;]*", "", RegexOptions.IgnoreCase);
            res.Headers["Content-Security-Policy"] = (policy.Trim(' ', ';') + "; frame-ancestors " + parent).TrimStart(';',' ');
            if (section == Section.Library && req.Method == "GET" && reply.IsSuccessStatusCode &&
                req.Path.Value is "/" or "/library" or "/library/" && reply.Content.Headers.ContentType?.MediaType == "text/html")
            {
                // The standalone transport validates the canonical companion URL before making a relative XHR.
                // Direct media URLs and that port guard must use the same origin in the Chrome copy.
                string html = await reply.Content.ReadAsStringAsync(context.RequestAborted);
                html = html.Replace("http://127.0.0.1:8765", self)
                    .Replace("\"8765\"", "\"" + Address.Port + "\"").Replace("'8765'", "'" + Address.Port + "'");
                const string head = "</head>";
                int end = html.IndexOf(head, StringComparison.OrdinalIgnoreCase);
                if (end >= 0) html = html.Insert(end, "<script src=\"/_media-suite/battles.js\" data-parent=\"" + parent + "\" defer></script>");
                await res.WriteAsync(html, Encoding.UTF8, context.RequestAborted);
                return;
            }
            res.ContentLength = reply.Content.Headers.ContentLength;
            if (req.Method != "HEAD") await reply.Content.CopyToAsync(res.Body, context.RequestAborted);
        }
        catch (Exception e) when (e is HttpRequestException or IOException or OperationCanceledException && !context.RequestAborted.IsCancellationRequested)
        {
            Trace.TraceWarning("{0} upstream request failed: {1}", section, e.GetBaseException().Message);
            if (res.HasStarted) { context.Abort(); return; }
            res.Clear(); res.StatusCode = 502;
            await res.WriteAsync("The local program disconnected. Reopen its section to reconnect.");
        }
    }

    public void Dispose() => client.Dispose();
}
