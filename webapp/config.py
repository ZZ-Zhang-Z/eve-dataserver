# webapp/config.py
# 集中管理应用配置：EVE SSO 常量、本地 ESI 凭据读取、Flask secret_key 逻辑。

import hashlib
import json
import os

import paths

# ===== EVE SSO (OAuth2 + PKCE) 配置 =====
EVE_SSO_AUTHORIZE_URL = "https://login.eveonline.com/v2/oauth/authorize"
EVE_SSO_TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
EVE_SSO_USER_AGENT = "EVE Helper/1.0 (zzk.linyi@gmail.com)"

# 本地 ESI 应用凭据文件（位于项目根目录）
CREDENTIALS_PATH = os.path.join(paths.BASE_DIR, 'esi_credentials.json')


def load_esi_credentials():
    """读取本地 ESI 应用凭据（esi_credentials.json）。"""
    try:
        with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取 esi_credentials.json 失败: {e}")
        return {}


ESI_CREDENTIALS = load_esi_credentials()
EVE_CLIENT_ID = ESI_CREDENTIALS.get('client_id', '')
EVE_CLIENT_SECRET = ESI_CREDENTIALS.get('client_secret', '')
EVE_CALLBACK_URL = ESI_CREDENTIALS.get('callback_url', 'http://localhost:5000/callback')
EVE_SCOPES = ESI_CREDENTIALS.get('scopes', [])


def get_secret_key():
    """Flask session 密钥（用于保存 PKCE 状态与令牌）。"""
    return os.environ.get('EVE_HELPER_SECRET_KEY') or hashlib.sha256(
        (EVE_CLIENT_SECRET or 'eve-helper-dev-key').encode('utf-8')
    ).hexdigest()