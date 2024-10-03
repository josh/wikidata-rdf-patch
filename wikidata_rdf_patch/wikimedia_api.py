import http.cookiejar
import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Literal

logger = logging.getLogger(__name__)


def _request(
    cookies: http.cookiejar.CookieJar,
    params: dict[str, str],
    method: Literal["GET", "POST"] = "GET",
) -> dict[str, Any]:
    url = "https://www.wikidata.org/w/api.php"
    headers: dict[str, str] = {}
    params["format"] = "json"
    encoded_params = urllib.parse.urlencode(params)
    post_data: bytes | None = None
    if method == "GET":
        url = f"{url}?{encoded_params}"
    elif method == "POST":
        post_data = encoded_params.encode("utf-8")
    req = urllib.request.Request(url, data=post_data, headers=headers, method=method)
    cookies.add_cookie_header(req)
    with urllib.request.urlopen(req) as response:
        data = response.read()
        assert isinstance(data, bytes)
        cookies.extract_cookies(response, req)
    api_data: dict[str, Any] = json.loads(data)
    warnings = api_data.get("warnings", {})
    for group_name, group_warnings in warnings.items():
        for warning in group_warnings.values():
            logger.warning("[%s] %s", group_name, warning)
    return api_data


def userinfo(cookies: http.cookiejar.CookieJar) -> dict[str, Any]:
    params = {
        "action": "query",
        "meta": "userinfo",
        "uiprop": "blockinfo|groups|hasmsg|ratelimits|rights",
    }
    return _request(params=params, cookies=cookies)


def get_token(
    type: Literal["login", "csrf"],
    cookies: http.cookiejar.CookieJar,
) -> str:
    params = {
        "action": "query",
        "meta": "tokens",
        "type": type,
    }
    resp = _request(params=params, cookies=cookies)
    token: str = ""
    if type == "login":
        token = resp["query"]["tokens"]["logintoken"]
    elif type == "csrf":
        token = resp["query"]["tokens"]["csrftoken"]
    return token


def login(
    cookies: http.cookiejar.CookieJar,
    lgname: str,
    lgpassword: str,
) -> bool:
    lgtoken = get_token(type="login", cookies=cookies)
    params = {
        "action": "login",
        "lgname": lgname,
        "lgpassword": lgpassword,
        "lgtoken": lgtoken,
    }
    resp = _request(params=params, method="POST", cookies=cookies)
    result: str = resp["login"]["result"]
    return result == "Success"


def wbeditentity(
    qid: str,
    baserevid: int,
    edit_data: dict[str, Any],
    summary: str,
    csrf_token: str,
    cookies: http.cookiejar.CookieJar,
) -> dict[str, Any]:
    params = {
        "action": "wbeditentity",
        "id": qid,
        "baserevid": str(baserevid),
        "summary": summary,
        "token": csrf_token,
        "bot": "1",
        "assert": "bot",
        "data": json.dumps(edit_data),
    }
    resp = _request(
        method="POST",
        params=params,
        cookies=cookies,
    )
    return resp
