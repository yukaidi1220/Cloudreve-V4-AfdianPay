"""Cloudreve 签名验证服务

POST 请求签名格式：Authorization: Bearer Cr SIGNATURE:TIMESTAMP
GET  请求签名格式：sign URL 参数，值为 SIGNATURE:TIMESTAMP（URL 编码）
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import time
from typing import Mapping


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode()


def verify_post(
    *,
    headers: Mapping[str, str],
    body: str,
    path: str,
    signature: str,
    timestamp: str,
    communication_key: str,
) -> tuple[bool, str]:
    """验证 Cloudreve POST 请求签名"""
    # 检查时间戳是否过期（Cloudreve 发送的是过期时间）
    if time.time() > int(timestamp):
        return False, "签名已过期"

    # 收集 X-Cr-* 前缀的请求头，格式 key=value，排序后 & 拼接
    signed = []
    for k, v in headers.items():
        if k.startswith("X-Cr-"):
            signed.append(f"{k}={v}")
    signed.sort()
    signed_str = "&".join(signed)

    # 构造待签名内容
    sign_raw = {
        "Path": path or "/",
        "Header": signed_str,
        "Body": body,
    }
    sign_content = json.dumps(sign_raw, separators=(",", ":"), ensure_ascii=False)
    # Python json.dumps 不会转义 &，但 Cloudreve 的 Go 实现会，必须手动替换
    sign_content = sign_content.replace("&", "\\u0026")

    return _verify(sign_content, timestamp, signature, communication_key)


def verify_get(
    *,
    path: str,
    signature: str,
    timestamp: str,
    communication_key: str,
) -> tuple[bool, str]:
    """验证 Cloudreve GET 请求签名"""
    if time.time() > int(timestamp):
        return False, "签名已过期"

    sign_content = path or "/"
    return _verify(sign_content, timestamp, signature, communication_key)


def _verify(
    sign_content: str,
    timestamp: str,
    signature: str,
    communication_key: str,
) -> tuple[bool, str]:
    """核心验签逻辑：signContent:timestamp → HMAC-SHA256 → base64url"""
    sign_content_final = f"{sign_content}:{timestamp}"
    h = _hmac.new(
        communication_key.encode(),
        sign_content_final.encode(),
        hashlib.sha256,
    )
    expected = _b64url(h.digest())
    if not _hmac.compare_digest(expected, signature):
        return False, "签名无效"
    return True, ""


def parse_authorization(auth_header: str) -> tuple[str, str] | None:
    """从 Authorization: Bearer Cr SIGNATURE:TIMESTAMP 中提取签名和时间戳"""
    if not auth_header.startswith("Bearer Cr "):
        return None
    parts = auth_header[len("Bearer Cr "):].split(":")
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def parse_sign_param(sign_param: str) -> tuple[str, str] | None:
    """从 URL 参数 sign 中提取签名和时间戳（已解码）"""
    parts = sign_param.split(":")
    if len(parts) != 2:
        return None
    return parts[0], parts[1]
