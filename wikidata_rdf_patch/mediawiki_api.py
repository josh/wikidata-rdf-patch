import http.cookiejar
import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from wikidata_rdf_patch.wikidata_typing import (
    Descriptions,
    Entity,
    Labels,
    Statement,
)

logger = logging.getLogger("mediawiki-api")

DEFAULT_USER_AGENT = (
    "wikidata-rdf-patch/1.0 (https://github.com/josh/wikidata-rdf-patch)"
)


class Error(Exception):
    code: str
    info: str

    def __init__(self, code: str, info: str):
        self.code = code
        self.info = info
        super().__init__(f"[{code}] {info}")


# https://www.wikidata.org/w/api.php?action=help
def _request(
    action: str,
    method: Literal["GET", "POST"],
    params: dict[str, str],
    cookies: http.cookiejar.CookieJar,
    user_agent: str,
) -> dict[str, Any]:
    url = "https://www.wikidata.org/w/api.php"
    headers: dict[str, str] = {
        "User-Agent": user_agent,
    }
    params["action"] = action
    params["format"] = "json"
    params["maxlag"] = "5"
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

    if api_error := api_data.get("error", {}):
        logger.error(api_data["error"]["info"])
        raise Error(code=api_error["code"], info=api_error["info"])

    warnings = api_data.get("warnings", {}).get(action, {})
    for warning in warnings.values():
        logger.warning("[%s] %s", action, warning)

    return api_data


# https://www.wikidata.org/w/api.php?action=help&modules=query%2Btokens
def _token(
    type: Literal["login", "csrf"],
    cookies: http.cookiejar.CookieJar,
    user_agent: str,
) -> str:
    params = {"meta": "tokens", "type": type}
    resp = _request(
        method="GET",
        action="query",
        params=params,
        cookies=cookies,
        user_agent=user_agent,
    )
    token = resp["query"]["tokens"][f"{type}token"]
    assert isinstance(token, str)
    return token


@dataclass
class Session:
    cookies: http.cookiejar.CookieJar
    user_agent: str
    csrf_token: str
    login_token: str
    username: str
    password: str


class LoginError(Exception):
    pass


# https://www.wikidata.org/w/api.php?action=help&modules=login
def _login(session: Session) -> None:
    session.login_token = _token(
        type="login",
        cookies=session.cookies,
        user_agent=session.user_agent,
    )
    params = {
        "lgname": session.username,
        "lgpassword": session.password,
        "lgtoken": session.login_token,
    }
    resp = _request(
        method="POST",
        action="login",
        params=params,
        cookies=session.cookies,
        user_agent=session.user_agent,
    )
    result: str = resp["login"]["result"]
    if result == "Success":
        session.csrf_token = _token(
            type="csrf",
            cookies=session.cookies,
            user_agent=session.user_agent,
        )
    else:
        raise LoginError(resp["login"]["reason"])


# https://www.wikidata.org/w/api.php?action=help&modules=login
def login(username: str, password: str, user_agent: str) -> Session:
    session = Session(
        cookies=http.cookiejar.CookieJar(),
        csrf_token="",
        login_token="",
        username=username,
        password=password,
        user_agent=user_agent,
    )
    _login(session=session)
    return session


# https://www.wikidata.org/w/api.php?action=help&modules=logout
def logout(session: Session) -> None:
    params = {"token": session.csrf_token}
    _request(
        method="POST",
        action="logout",
        params=params,
        cookies=session.cookies,
        user_agent=session.user_agent,
    )
    return None


class WikibaseEditEntityData(TypedDict, total=False):
    labels: Labels
    descriptions: Descriptions
    claims: list[Statement]


# https://www.wikidata.org/w/api.php?action=help&modules=wbeditentity
def wbeditentity(
    session: Session,
    qid: str,
    edit_data: WikibaseEditEntityData,
    baserevid: int | None = None,
    summary: str | None = None,
    retries: int = 5,
) -> None:
    assert qid.startswith("Q"), "QID must start with Q"

    while retries > 0:
        try:
            params = {
                "id": qid,
                "token": session.csrf_token,
                "bot": "1",
                "assert": "bot",
                "data": json.dumps(edit_data),
            }
            if baserevid:
                params["baserevid"] = str(baserevid)
            if summary:
                params["summary"] = summary

            retries -= 1
            resp = _request(
                method="POST",
                action="wbeditentity",
                params=params,
                cookies=session.cookies,
                user_agent=session.user_agent,
            )

            success: int = resp.get("success", 0)
            if success == 1:
                return
            else:
                continue

        except Error as e:
            # https://www.mediawiki.org/wiki/Manual:Maxlag_parameter
            if e.code == "maxlag" and retries > 0:
                logger.warning("Waiting for %.1f seconds", 5)
                time.sleep(5)
                continue
            elif e.code == "assertbotfailed" and retries > 0:
                logger.warning("session expired, logging in again")
                _login(session=session)
                continue
            else:
                raise e

    raise Exception("out of retries")


def wbgetentities(ids: list[str], user_agent: str) -> dict[str, Entity]:
    assert len(ids) > 0, "must specify at least one ID"
    assert len(ids) <= 50, "must specify at most 50 IDs"
    resp = _request(
        method="GET",
        action="wbgetentities",
        params={"ids": "|".join(ids)},
        cookies=http.cookiejar.CookieJar(),
        user_agent=user_agent,
    )
    assert resp.get("success") == 1, "wbgetentities failed"
    entities: dict[str, Entity] = resp["entities"]
    return entities
