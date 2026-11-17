#!/usr/bin/env python3
"""Render private Xray/Mihomo deployment files; performs no network operations."""

import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import uuid
from urllib.parse import unquote, urlsplit

import yaml
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)

SKILL = Path(__file__).resolve().parents[1]
CLIENT_NAME = "Clash-VPS-住宅.yaml"
VPS = "VPS出口 · REALITY Vision"
HOME = "住宅出口 · REALITY Vision"
BUILTINS = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"}


def host(value):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if "%" in value:
        raise ValueError("不支持带接口作用域的公网地址")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    try:
        value = value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValueError("服务器或 SNI 域名无效") from None
    label = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
    if len(value) > 253 or not value or not all(label.fullmatch(x) for x in value.split(".")):
        raise ValueError("请输入纯 IP 或域名，端口通过独立参数指定")
    return value


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def write_private(path, content):
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_socks(path):
    if path is None:
        return None
    if path.stat().st_mode & 0o077:
        raise ValueError("住宅凭据文件须仅当前用户可读，例如权限 0600")
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    try:
        if len(lines) != 1:
            raise ValueError()
        parsed = urlsplit(lines[0])
        if (parsed.scheme not in {"socks5", "socks5h"} or not parsed.hostname
                or parsed.port is None or not 1 <= parsed.port <= 65535 or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise ValueError()
        settings = {"address": host(parsed.hostname), "port": parsed.port}
        if (parsed.username is None) != (parsed.password is None):
            raise ValueError()
        if parsed.username is not None:
            settings["user"] = unquote(parsed.username, errors="strict")
            settings["pass"] = unquote(parsed.password, errors="strict")
            if not all(1 <= len(settings[key].encode()) <= 255 for key in ("user", "pass")):
                raise ValueError()
        return settings
    except (ValueError, UnicodeError):
        raise ValueError("住宅凭据文件须含一条完整 SOCKS5 URL；认证信息中的特殊字符须 URL 编码") from None


def load_state(output, server):
    path = output / "deployment-private.json"
    if path.exists():
        state = json.loads(path.read_text())
        if state.get("schema_version") != 1 or state.get("server") != server:
            raise ValueError("输出目录属于其他目标或格式不受支持，请为本次 VPS 使用新的独立目录")
        key = X25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(state["private_key"] + "="))
        if b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)) != state["public_key"]:
            raise ValueError("已有状态中的 REALITY 密钥对不一致")
        for name in ("vps_uuid", "residential_uuid"):
            uuid.UUID(state[name])
        if not re.fullmatch(r"[a-f0-9]{16}", state["short_id"]):
            raise ValueError("已有状态的 short ID 无效")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", state["subscription_token"]):
            raise ValueError("已有状态的订阅令牌无效")
        return state
    if output.exists() and any(output.iterdir()):
        raise ValueError("输出目录已有其他文件，请指定新的独立目录")
    key = X25519PrivateKey.generate()
    return {
        "schema_version": 1, "server": server,
        "private_key": b64(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())),
        "public_key": b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)),
        "vps_uuid": str(uuid.uuid4()), "residential_uuid": str(uuid.uuid4()),
        "short_id": secrets.token_hex(8), "subscription_token": secrets.token_urlsafe(32),
    }


def client_config(state, residential, rules_path):
    client = yaml.safe_load((SKILL / "assets" / CLIENT_NAME).read_text())
    if rules_path is not None:
        extra = yaml.safe_load(rules_path.read_text())
        if not isinstance(extra, dict) or "rules" not in extra:
            raise ValueError("自定义规则文件必须包含 rules 列表")
        client["rules"] = extra["rules"]
        if "proxy-groups" in extra:
            client["proxy-groups"] = extra["proxy-groups"]
    rules = client.get("rules")
    if not isinstance(rules, list) or not rules or not all(isinstance(x, str) for x in rules):
        raise ValueError("必须保留非空的分流规则列表")
    client["proxies"] = []
    choices = [(VPS, "vps_uuid", True)]
    if residential:
        choices.append((HOME, "residential_uuid", False))
    for name, field, udp in choices:
        client["proxies"].append({
            "name": name, "type": "vless", "server": state["server"],
            "port": state["vless_port"], "uuid": state[field], "network": "tcp",
            "tls": True, "flow": "xtls-rprx-vision", "udp": udp, "packet-encoding": "xudp",
            "servername": state["sni"], "client-fingerprint": "chrome",
            "reality-opts": {"public-key": state["public_key"], "short-id": state["short_id"],
                             "support-x25519mlkem768": True},
        })
    groups = client.get("proxy-groups")
    if not isinstance(groups, list) or not groups or not all(isinstance(g, dict) for g in groups):
        raise ValueError("配置必须包含有效的代理分组")
    group_names = [g.get("name") for g in groups]
    node_names = [p["name"] for p in client["proxies"]]
    if (not all(isinstance(n, str) and n for n in group_names)
            or len(set(group_names + node_names)) != len(group_names + node_names)):
        raise ValueError("代理分组或节点名称无效或重复")
    allowed = set(group_names + node_names) | BUILTINS
    for group in groups:
        members = group.get("proxies", [])
        if not isinstance(members, list) or not all(isinstance(x, str) for x in members):
            raise ValueError("代理分组的 proxies 必须是名称列表")
        if not residential:
            members = [x for x in members if x != HOME]
            group["proxies"] = members
        if any(x not in allowed for x in members):
            raise ValueError("代理分组引用了未定义的节点或分组")
        if not members and not group.get("include-all"):
            raise ValueError("代理分组没有可用节点，请检查自定义规则与住宅选项")
    edges = {g["name"]: [x for x in g.get("proxies", []) if x in group_names] for g in groups}
    active, visited = set(), set()

    def visit(name):
        if name in active:
            raise ValueError("代理分组存在循环引用")
        if name in visited:
            return
        active.add(name)
        for member in edges[name]:
            visit(member)
        active.remove(name)
        visited.add(name)

    for name in group_names:
        visit(name)
    for rule in rules:
        parts = rule.split(",")
        if parts[-1] == "no-resolve":
            parts.pop()
        if len(parts) < 2 or parts[-1] not in allowed:
            raise ValueError("分流规则引用了未定义的策略，请检查自定义规则分组")
    return client


def server_config(state, socks, minimum):
    clients = [{"id": state["vps_uuid"], "email": "vps@reality.local", "flow": "xtls-rprx-vision"}]
    outbounds = [{"tag": "vps", "protocol": "freedom", "settings": {},
                  "streamSettings": {"sockopt": {"domainStrategy": "UseIPv4"}}}]
    routes = [{"type": "field", "user": ["vps@reality.local"], "outboundTag": "vps"}]
    if socks is not None:
        clients.append({"id": state["residential_uuid"], "email": "residential@reality.local", "flow": "xtls-rprx-vision"})
        outbounds.append({"tag": "residential", "protocol": "socks", "settings": socks})
        routes.insert(0, {"type": "field", "user": ["residential@reality.local"], "outboundTag": "residential"})
    return {"log": {"loglevel": "warning"}, "inbounds": [{
        "tag": "reality-vision", "listen": "::" if ":" in state["server"] else "0.0.0.0",
        "port": state["vless_port"], "protocol": "vless",
        "settings": {"clients": clients, "decryption": "none"},
        "streamSettings": {"network": "raw", "security": "reality", "realitySettings": {
            "show": False, "target": state["sni"] + ":443", "xver": 0,
            "serverNames": [state["sni"]], "privateKey": state["private_key"],
            "shortIds": [state["short_id"]], "minClientVer": minimum,
        }},
    }], "outbounds": outbounds, "routing": {"domainStrategy": "AsIs", "rules": routes}}


def nginx_configs(state):
    server = state["server"]
    ipv6 = ":" in server
    display_host = "[" + server + "]" if ipv6 else server
    acme = f"""server {{
    listen {'[::]:80' if ipv6 else '80'};
    server_name {display_host};
    access_log off;
    location ^~ /.well-known/acme-challenge/ {{ root /var/www/reality-acme; }}
    location / {{ return 404; }}
}}
"""
    listen = ("[::]:" if ipv6 else "") + str(state["subscription_port"])
    full = acme + f"""server {{
    listen {listen} ssl;
    server_name {display_host};
    ssl_certificate /etc/letsencrypt/live/{server}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{server}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    server_tokens off;
    access_log off;
    location = /sub/{state['subscription_token']}/config.yaml {{
        alias /var/lib/reality-subscription/config.yaml;
        default_type application/yaml;
        add_header Cache-Control "no-store" always;
        add_header X-Content-Type-Options nosniff always;
        add_header profile-update-interval "24";
    }}
    location / {{ return 404; }}
}}
"""
    url = f"https://{display_host}:{state['subscription_port']}/sub/{state['subscription_token']}/config.yaml\n"
    return acme, full, url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, help="VPS IP or domain; no credentials")
    parser.add_argument("--sni", required=True, help="REALITY hostname already tested from the VPS")
    parser.add_argument("--output", required=True, type=Path, help="Independent private output directory")
    parser.add_argument("--residential-secret-file", type=Path, help="Private file containing one SOCKS5 URL")
    parser.add_argument("--rules-file", type=Path, help="Explicit replacement rules, optionally proxy-groups")
    parser.add_argument("--vless-port", type=int, default=443)
    parser.add_argument("--subscription-port", type=int, default=8443)
    parser.add_argument("--min-client-version", default="1.8.2")
    args = parser.parse_args()
    try:
        server, sni = host(args.server), host(args.sni)
        if ":" in sni or re.fullmatch(r"[0-9.]+", sni):
            raise ValueError("此生成器需要经过验证的 REALITY SNI 域名")
        ports = (args.vless_port, args.subscription_port)
        if any(not 1 <= p <= 65535 or p == 80 for p in ports) or len(set(ports)) != 2:
            raise ValueError("代理和订阅端口须不同、有效，且为 HTTP-01 保留端口 80")
        if (not re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}", args.min_client_version)
                or any(int(p) > 255 for p in args.min_client_version.split("."))):
            raise ValueError("最低客户端版本须为三个 0–255 整数，如 1.8.2")
        socks = read_socks(args.residential_secret_file)
        state = load_state(args.output, server)
        state.update({"sni": sni, "vless_port": ports[0], "subscription_port": ports[1],
                      "residential_enabled": socks is not None})
        client = client_config(state, socks is not None, args.rules_file)
        xray = server_config(state, socks, args.min_client_version)
        acme, nginx, url = nginx_configs(state)
        args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
        args.output.chmod(0o700)
        files = {
            CLIENT_NAME: "# 完整分流配置；住宅节点仅在提供可用住宅代理时生成。\n" + yaml.safe_dump(client, allow_unicode=True, sort_keys=False),
            "server.json": json.dumps(xray, ensure_ascii=False, indent=2) + "\n",
            "deployment-private.json": json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            "acme-webroot-nginx.conf": acme, "subscription-nginx.conf": nginx, "subscription.url": url,
        }
        for name, content in files.items():
            write_private(args.output / name, content)
        print(json.dumps({"status": "generated-locally-not-published", "output": str(args.output),
                          "nodes": len(client["proxies"]), "rules": len(client["rules"]),
                          "core_validation": "not-run", "network_validation": "not-run",
                          "files": list(files)}, ensure_ascii=False))
    except yaml.YAMLError:
        parser.exit(2, "error: YAML 格式无效，请检查模板或规则文件；未回显文件内容。\n")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "输入或私密状态文件无效，请检查路径和格式"
        parser.exit(2, "error: " + message + "\n")


if __name__ == "__main__":
    main()
