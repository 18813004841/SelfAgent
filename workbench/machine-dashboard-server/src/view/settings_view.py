from . import router


@router.route("GET", "/api/settings/storage", "/api/settings/storage/open")
@router.route("POST", "/api/settings/storage", "/api/settings/storage/reset", "/api/settings/storage/choose", "/api/settings/storage/open")
def handle(ctx):
    """Client filesystem settings belong exclusively to the loopback agent."""
    ctx.request.send_json(409, {
        "ok": False,
        "error": "Client storage settings require the local agent at http://127.0.0.1:18991",
        "code": "client_local_only",
    })
    return True
