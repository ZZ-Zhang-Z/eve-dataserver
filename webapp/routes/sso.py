# webapp/routes/sso.py
# EVE SSO 登录路由：/login 与 /callback（OAuth2 + PKCE）。

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.request
from urllib.parse import urlencode

from flask import Blueprint, jsonify, redirect, request, session

from ..config import (
    EVE_CALLBACK_URL,
    EVE_CLIENT_ID,
    EVE_CLIENT_SECRET,
    EVE_SCOPES,
    EVE_SSO_AUTHORIZE_URL,
    EVE_SSO_TOKEN_URL,
    EVE_SSO_USER_AGENT,
)

bp = Blueprint('sso', __name__)


def _pkce_pair():
    """生成 PKCE 的 code_verifier 与 code_challenge(S256)。"""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return verifier, challenge


def _decode_jwt_payload(token):
    """解析 JWT 载荷（不校验签名；令牌由 EVE 经 TLS 直接返回，可信）。"""
    try:
        payload_b64 = token.split('.')[1]
        padding = '=' * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(payload.decode('utf-8'))
    except Exception:
        return {}


@bp.route('/login')
def login():
    """跳转到 EVE SSO 授权页（PKCE）。"""
    if not EVE_CLIENT_ID or not EVE_CLIENT_SECRET:
        return jsonify({"success": False, "error": "未找到 ESI 应用凭据，请检查 esi_credentials.json"}), 500

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    session['pkce_verifier'] = verifier
    session['oauth_state'] = state

    params = {
        'response_type': 'code',
        'redirect_uri': EVE_CALLBACK_URL,
        'client_id': EVE_CLIENT_ID,
        'scope': ' '.join(EVE_SCOPES),
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    return redirect(f"{EVE_SSO_AUTHORIZE_URL}?{urlencode(params)}")


@bp.route('/callback')
def callback():
    """EVE SSO 回调：校验 state 并用授权码（+PKCE）换取令牌。"""
    error = request.args.get('error')
    if error:
        return jsonify({
            "success": False,
            "error": error,
            "error_description": request.args.get('error_description', '')
        }), 400

    code = request.args.get('code')
    state = request.args.get('state')
    expected_state = session.pop('oauth_state', None)
    verifier = session.pop('pkce_verifier', None)

    if not code:
        return jsonify({"success": False, "error": "缺少授权码 code"}), 400
    if not expected_state or state != expected_state:
        return jsonify({"success": False, "error": "state 校验失败，可能存在 CSRF"}), 400

    data = urlencode({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': EVE_CALLBACK_URL,
        'code_verifier': verifier or '',
    }).encode('utf-8')

    basic = base64.b64encode(f"{EVE_CLIENT_ID}:{EVE_CLIENT_SECRET}".encode('utf-8')).decode('utf-8')
    req = urllib.request.Request(
        EVE_SSO_TOKEN_URL,
        data=data,
        headers={
            'Authorization': f'Basic {basic}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Host': 'login.eveonline.com',
            'User-Agent': EVE_SSO_USER_AGENT,
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='ignore')
        return jsonify({"success": False, "error": f"换取令牌失败: HTTP {e.code}", "detail": detail}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"换取令牌失败: {e}"}), 500

    access_token = token_data.get('access_token', '')
    payload = _decode_jwt_payload(access_token)
    sub = payload.get('sub', '')
    character_id = sub.split(':')[-1] if sub else None

    session['access_token'] = access_token
    session['refresh_token'] = token_data.get('refresh_token', '')
    session['character_id'] = character_id
    session['character_name'] = payload.get('name', '')
    session['token_expires_in'] = token_data.get('expires_in')

    return jsonify({
        "success": True,
        "character_id": character_id,
        "character_name": payload.get('name', ''),
        "scopes": payload.get('scp', []),
        "expires_in": token_data.get('expires_in'),
        "message": "登录成功，令牌已保存到会话。",
    })