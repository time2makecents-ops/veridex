# PATCH: add office.memos_list + office.memo_get safely, dispatcher-aware
$ErrorActionPreference = "Stop"
$root = Get-Location
$app = Join-Path $root "office_app\server\app.py"
if (!(Test-Path $app)) { throw "Missing: $app" }

$txt = Get-Content $app -Raw -Encoding UTF8

# 0) Abort if app.py doesn't contain the /call tool dispatcher (sanity)
if ($txt -notmatch 'Unknown tool') {
  throw "Could not find the tool dispatch error in app.py (pattern: 'Unknown tool'). Patch aborted."
}

# 1) Insert handlers exactly once (marked block)
$markerStart = "# === MEMO QUERY TOOLS START ==="
$markerEnd   = "# === MEMO QUERY TOOLS END ==="

if ($txt -notmatch [regex]::Escape($markerStart)) {
$handlers = @"
$markerStart
import os, json, glob
from fastapi import HTTPException

def _memo_dir() -> str:
    d = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "runtime", "memos"))
    os.makedirs(d, exist_ok=True)
    return d

def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def handle_memos_list(arguments):
    limit = int(arguments.get("limit", 25))
    limit = max(1, min(limit, 200))
    files = sorted(
        glob.glob(os.path.join(_memo_dir(), "*.json")),
        key=os.path.getmtime,
        reverse=True
    )[:limit]
    rows = []
    for f in files:
        obj = _load_json(f)
        # return a stable summary shape
        rows.append({
            "memo_id": obj.get("memo_id"),
            "created_utc": obj.get("created_utc"),
            "from_room": obj.get("from_room"),
            "to_room": obj.get("to_room"),
            "to_persona": obj.get("to_persona"),
            "subject": obj.get("subject"),
        })
    return {
        "structuredContent": { "count": len(rows), "memos": rows },
        "content": [{ "type": "text", "text": f"Found {len(rows)} memo(s)." }]
    }

def handle_memo_get(arguments):
    memo_id = str(arguments.get("memo_id", "")).strip()
    if not memo_id:
        raise HTTPException(status_code=400, detail="memo_id is required")
    path = os.path.join(_memo_dir(), memo_id + ".json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Memo not found: {memo_id}")
    obj = _load_json(path)
    body = obj.get("body", "")
    return {
        "structuredContent": obj,
        "content": [{
            "type": "text",
            "text": f"Memo {obj.get('memo_id')}\nFrom: {obj.get('from_room')}\nTo: {obj.get('to_room')} ({obj.get('to_persona')})\nSubject: {obj.get('subject')}\n\n{body}"
        }]
    }
$markerEnd
"@

  # Append handlers at end of file (safe; no dependency on internal layout)
  $txt = $txt.TrimEnd() + "`r`n`r`n" + $handlers + "`r`n"
}

# 2) Register tools in dispatcher (supports map-based OR if/elif based)
if ($txt -match 'TOOL_HANDLERS\s*=\s*\{') {
  # Map-based dispatcher
  if ($txt -notmatch '"office\.memos_list"\s*:') {
    $txt = [regex]::Replace(
      $txt,
      '(TOOL_HANDLERS\s*=\s*\{)',
      "`$1`r`n    `"office.memos_list`": handle_memos_list,`r`n    `"office.memo_get`": handle_memo_get,",
      1
    )
  }
} else {
  # if/elif chain: inject right before the Unknown tool raise
  if ($txt -notmatch 'elif tool == "office\.memos_list"') {
    $inject = @"
    elif tool == "office.memos_list":
        return handle_memos_list(arguments)
    elif tool == "office.memo_get":
        return handle_memo_get(arguments)
"@
    $txt = [regex]::Replace(
      $txt,
      '(?s)(\n\s*)raise HTTPException\([^\n]*Unknown tool[^\n]*\)\s*',
      "`r`n$inject`r`n`$0",
      1
    )
  }
}

# 3) Write file back
Set-Content -Path $app -Value $txt -Encoding UTF8
Write-Host "Patched app.py (handlers + dispatch registration)."

# 4) Compile check (fail-closed before restart)
Write-Host "Compile-checking server modules..."
python -m compileall office_app\server | Out-Host












C:\Users\Accordion to JR\Documents\Office-App>run_server.cmd
Starting Office App Server...
←[32mINFO←[0m:     Started server process [←[36m8364←[0m]
←[32mINFO←[0m:     Waiting for application startup.
←[32mINFO←[0m:     Application startup complete.
←[32mINFO←[0m:     Uvicorn running on ←[1mhttp://127.0.0.1:8000←[0m (Press CTRL+C to quit)
←[32mINFO←[0m:     127.0.0.1:55731 - "←[1mPOST /call HTTP/1.1←[0m" ←[91m500 Internal Server Error←[0m
←[31mERROR←[0m:    Exception in ASGI application
Traceback (most recent call last):
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\uvicorn\protocols\http\h11_impl.py", line 410, in run_asgi
    result = await app(  # type: ignore[func-returns-value]
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        self.scope, self.receive, self.send
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\uvicorn\middleware\proxy_headers.py", line 60, in __call__
    return await self.app(scope, receive, send)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\fastapi\applications.py", line 1160, in __call__
    await super().__call__(scope, receive, send)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\applications.py", line 107, in __call__
    await self.middleware_stack(scope, receive, send)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\middleware\errors.py", line 186, in __call__
    raise exc
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\middleware\errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\middleware\exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\fastapi\middleware\asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\routing.py", line 716, in __call__
    await self.middleware_stack(scope, receive, send)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\routing.py", line 736, in app
    await route.handle(scope, receive, send)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\routing.py", line 290, in handle
    await self.app(scope, receive, send)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\fastapi\routing.py", line 130, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\fastapi\routing.py", line 116, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\fastapi\routing.py", line 670, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
    )
    ^
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\fastapi\routing.py", line 326, in run_endpoint_function
    return await run_in_threadpool(dependant.call, **values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\starlette\concurrency.py", line 32, in run_in_threadpool
    return await anyio.to_thread.run_sync(func)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\anyio\to_thread.py", line 63, in run_sync
    return await get_async_backend().run_sync_in_worker_thread(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        func, args, abandon_on_cancel=abandon_on_cancel, limiter=limiter
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\anyio\_backends\_asyncio.py", line 2502, in run_sync_in_worker_thread
    return await future
           ^^^^^^^^^^^^
  File "C:\Users\Accordion to JR\AppData\Local\Programs\Python\Python313\Lib\site-packages\anyio\_backends\_asyncio.py", line 986, in run
    result = context.run(func, *args)
  File "C:\Users\Accordion to JR\Documents\Office-App\office_app\server\app.py", line 256, in call_tool
    return handle_memos_list(arguments)
                             ^^^^^^^^^
NameError: name 'arguments' is not defined


Write-Host "If no SyntaxError above, restart: run_server.cmd"