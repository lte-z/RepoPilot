"""Network context tools shared by MCP, CLI, and WebUI."""

from __future__ import annotations

import ipaddress
import socket
from email.message import Message
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from repopilot.config import AppConfig, load_config


ResponseFormat = Literal["markdown", "json"]


class FetchUrlInput(BaseModel):
    url: str = Field(description="HTTP or HTTPS URL to fetch.")
    max_chars: int | None = Field(default=None, ge=1, description="Maximum text characters to return.")
    response_format: ResponseFormat = "markdown"


def _format(data: dict[str, Any], markdown: str, response_format: ResponseFormat) -> str:
    if response_format == "json":
        import json

        return json.dumps(data, ensure_ascii=False, indent=2)
    return markdown


def _is_private_host(host: str) -> bool:
    lowered = host.lower()
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
        except socket.gaierror:
            return False
        return any(_is_private_host(item) for item in addresses)
    return address.is_private or address.is_loopback or address.is_link_local or address.is_multicast


def _domain_allowed(host: str, allowed_domains: list[str]) -> bool:
    if not allowed_domains:
        return True
    lowered = host.lower()
    for domain in allowed_domains:
        item = domain.lower().lstrip(".")
        if lowered == item or lowered.endswith("." + item):
            return True
    return False


def _charset(headers: Message) -> str:
    content_type = headers.get_content_type()
    if not (content_type.startswith("text/") or content_type in {"application/json", "application/xml"}):
        raise ValueError(f"拒绝读取非文本响应：{content_type}")
    return headers.get_content_charset() or "utf-8"


def web_fetch_url(params: FetchUrlInput, config: AppConfig | None = None) -> str:
    """Fetch bounded text content from an HTTP(S) URL."""

    cfg = config or load_config()
    if not cfg.network.allow_http_fetch:
        return "Error: network.allow_http_fetch=false，联网抓取已被配置禁用。"

    parsed = urlparse(params.url)
    if parsed.scheme not in {"http", "https"}:
        return "Error: 仅支持 http/https URL。"
    if not parsed.hostname:
        return "Error: URL 缺少 hostname。"
    if cfg.network.deny_private_hosts and _is_private_host(parsed.hostname):
        return f"Error: 拒绝访问 localhost 或私网地址：{parsed.hostname}"
    if not _domain_allowed(parsed.hostname, cfg.network.allowed_domains):
        allowed = ", ".join(cfg.network.allowed_domains)
        return f"Error: URL 域名不在 network.allowed_domains 内：{parsed.hostname}；允许域名：{allowed}"

    max_chars = params.max_chars or cfg.network.max_fetch_chars
    request = Request(
        params.url,
        headers={
            "Accept": "text/plain,text/markdown,text/html,application/json,application/xml;q=0.9,*/*;q=0.1",
            "User-Agent": "RepoPilot/0.1",
        },
    )
    try:
        with urlopen(request, timeout=cfg.network.timeout_seconds) as response:
            charset = _charset(response.headers)
            raw = response.read(max_chars * 4 + 1)
            text = raw.decode(charset, errors="replace")
            truncated = len(text) > max_chars
            text = text[:max_chars]
            status = getattr(response, "status", 200)
            content_type = response.headers.get("content-type", "unknown")
    except HTTPError as exc:
        return f"Error: HTTP 请求失败：{exc.code} {exc.reason}"
    except URLError as exc:
        return f"Error: URL 请求失败：{exc.reason}"
    except TimeoutError:
        return f"Error: URL 请求超时：{cfg.network.timeout_seconds:g} 秒。"
    except ValueError as exc:
        return f"Error: {exc}"

    markdown = [
        f"# URL：{params.url}",
        "",
        f"- HTTP 状态：`{status}`",
        f"- Content-Type：`{content_type}`",
        f"- 返回字符数：`{len(text)}`",
        "",
        "```text",
        text,
        "```",
    ]
    if truncated:
        markdown.append(f"\n已截断：返回前 {max_chars} 字符。")
    data = {
        "url": params.url,
        "status": status,
        "content_type": content_type,
        "content": text,
        "truncated": truncated,
        "returned_chars": len(text),
    }
    return _format(data, "\n".join(markdown), params.response_format)
