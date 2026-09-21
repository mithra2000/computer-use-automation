"""Local-only, synthetic legacy UI with deterministic fault injection."""
from html import escape
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MEMBERS = {
    "12345": ("Sample Member Alpha", "2500.50", "USD"),
    "67890": ("Sample Member Beta", "8100.25", "USD"),
    "11111": ("Sample Member Gamma", "42.00", "USD"),
    "22222": ("Sample Member Delta", "150.75", "USD"),
}
SCENARIOS = {"normal", "slow_load", "session_expired", "permission_denied", "ambiguous", "wrong_member", "unknown_version", "never_load"}


def scenario_of(request: Request) -> str:
    value = request.query_params.get("scenario", request.cookies.get("scenario", "normal"))
    return value if value in SCENARIOS else "normal"


def page(title: str, body: str, scenario: str = "normal") -> HTMLResponse:
    version = "9.0" if scenario == "unknown_version" else "1.0"
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)} | LedgerDesk</title>
<style>body{{font:16px system-ui;margin:0;background:#eef1f4;color:#203047}}header{{background:#16304b;color:white;padding:22px 32px}}main{{margin:32px auto;max-width:850px;background:white;padding:30px;border:1px solid #ccd4dc}}h1{{font-size:25px}}table{{border-collapse:collapse;width:100%;margin:20px 0}}td,th{{border:1px solid #c6cfd8;padding:12px;text-align:left}}button,a{{color:#075d9c}}button{{padding:10px 20px;cursor:pointer}}input{{padding:9px;margin:10px}}iframe{{width:100%;height:390px;border:1px solid #ccd4dc}}footer{{font-size:12px;padding:18px;color:#52657a}}.notice{{padding:16px;background:#fff4d2}}</style></head>
<body><header>LEDGERDESK / OPERATIONS<br><small>Synthetic training environment</small></header>
<main><h1>{escape(title)}</h1>{body}</main><footer>LedgerDesk sandbox · version {version}</footer></body></html>""")


def auth(request: Request):
    if request.cookies.get("sandbox_session") != "synthetic-active":
        return page("Session expired", '<p>Start a sandbox session from the entry page.</p><a href="/">Entry</a>')
    return None


@app.get("/")
def entry(request: Request):
    scenario = scenario_of(request)
    return page("Sandbox entry", f'<p>No real credentials are used. All data is synthetic.</p><form action="/enter" method="post"><input type="hidden" name="scenario" value="{scenario}"><button>Enter sandbox</button></form>', scenario)


@app.post("/enter")
def enter(scenario: str = Form("normal")):
    response = RedirectResponse("/search", status_code=303)
    response.set_cookie("sandbox_session", "synthetic-active", httponly=True, samesite="strict")
    response.set_cookie("scenario", scenario if scenario in SCENARIOS else "normal", httponly=True)
    response.delete_cookie("restored")
    return response


@app.get("/search")
def search(request: Request):
    return auth(request) or page("Member search", '<form action="/results"><label for="member">Member ID</label><input id="member" name="member_id" required pattern="[0-9]{5}" maxlength="5"><button>Search</button></form>', scenario_of(request))


@app.get("/results")
def results(request: Request, member_id: str = ""):
    if error := auth(request):
        return error
    if len(member_id) != 5 or not member_id.isdigit():
        return page("Search results", '<p role="alert">Invalid member ID</p>')
    if member_id not in MEMBERS:
        return page("Search results", '<p role="status">No member found</p><a href="/search">Back to search</a>')
    scenario = scenario_of(request)
    name, _, _ = MEMBERS[member_id]
    link = f'<a href="/member/{member_id}">View member</a>'
    if scenario == "ambiguous":
        link += f' <a href="/member/{member_id}">View member</a>'
    table = f'<table aria-label="Search results"><tr><th>Member ID</th><th>Name</th><th>Action</th></tr><tr><td>{member_id}</td><td data-sensitive="name">{escape(name)}</td><td>{link}</td></tr></table>'
    if scenario in {"slow_load", "never_load"}:
        delay = 1600 if scenario == "slow_load" else 60000
        body = f'<p role="status" id="loading">Loading results…</p><section hidden id="results">{table}</section><script>setTimeout(()=>{{document.getElementById("loading").remove();document.getElementById("results").hidden=false}}, {delay})</script>'
    else:
        body = table
    return page("Search results", body, scenario)


@app.get("/member/{member_id}")
def member(request: Request, member_id: str):
    if error := auth(request):
        return error
    scenario = scenario_of(request)
    if scenario == "permission_denied":
        return page("Access denied", '<p role="alert">Permission denied for account access.</p>')
    if scenario == "session_expired" and request.cookies.get("restored") != "yes":
        return page("Session expired", f'<p class="notice">Your sandbox session expired. An operator must restore it.</p><form method="post" action="/restore"><input type="hidden" name="member_id" value="{escape(member_id)}"><label for="pass">Sandbox password (any value)</label><input id="pass" type="password" name="password" autocomplete="off"><button>Restore session</button></form><a href="/search">Back to search</a>')
    if member_id not in MEMBERS:
        return page("Search results", '<p role="status">No member found</p>')
    shown_id = "11111" if scenario == "wrong_member" else member_id
    return page("Member details", f'<table aria-label="Member details"><tr><th>Member ID</th><td>{shown_id}</td></tr><tr><th>Name</th><td data-sensitive="name">{escape(MEMBERS[member_id][0])}</td></tr></table><iframe name="accounts" title="Member accounts" src="/accounts/{member_id}"></iframe><a href="/search">Back to search</a>', scenario)


@app.post("/restore")
def restore(member_id: str = Form(...)):
    if member_id not in MEMBERS:
        return page("Access denied", "Invalid sandbox member.")
    response = RedirectResponse(f"/member/{member_id}", status_code=303)
    response.set_cookie("restored", "yes", httponly=True, samesite="strict")
    return response


@app.get("/accounts/{member_id}")
def accounts(request: Request, member_id: str):
    return auth(request) or page("Accounts", f'<table><tr><th>Account type</th><th>Open</th></tr><tr><td>Savings</td><td><a href="/balance/{escape(member_id)}">Savings account</a></td></tr></table>')


@app.get("/balance/{member_id}")
def balance(request: Request, member_id: str):
    if error := auth(request):
        return error
    if member_id not in MEMBERS:
        return page("Search results", '<p role="status">No member found</p>')
    _, amount, currency = MEMBERS[member_id]
    return page("Savings account", f'<table aria-label="Account summary"><tr><th>Member ID</th><td>{member_id}</td></tr><tr><th>Account type</th><td>Savings</td></tr><tr><th>Balance</th><td>{amount}</td></tr><tr><th>Currency</th><td>{currency}</td></tr></table><button>Transfer Funds</button>')
