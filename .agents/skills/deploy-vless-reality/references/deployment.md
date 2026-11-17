# 部署、兼容与验收参考

仅在执行部署或排查相关问题时读取。这里记录已验证做法，不把示例版本、端口和目标站点当作未来部署的固定条件。

## 握手兼容

本流程曾在 **Xray 26.10.31 + Mihomo 1.19.33** 上完整验证。

- 两端都用 VLESS、TCP/RAW、REALITY 和 `xtls-rprx-vision`；客户端使用支持 REALITY 的 Mihomo 内核。保持 `tls: true` 和有效的 REALITY 公钥、short ID、SNI。
- 当时 Xray 默认的最低客户端版本会拒绝 Mihomo 在握手中报告的 `1.8.2`。生成器显式设置 `realitySettings.minClientVer: "1.8.2"`；`--min-client-version` 可调整。部署时核对所用版本的实现和上游说明，不为排错一味放宽所有验证。
- 当时 Mihomo 默认会移除 X25519MLKEM768 key share，新版 REALITY 服务端会拒绝此类握手。因此生成器在客户端加入 `reality-opts.support-x25519mlkem768: true`，并使用 `client-fingerprint: chrome`。未来版本仍须验证实际指纹和密钥交换支持，不能只看 YAML 能否加载。
- 失败时先核对实际加载的配置、密钥对、公私钥对应、SNI、short ID、时钟、版本门槛、key share，再看目标站 TLS 和服务端日志。读取诊断时过滤 AuthKey、私钥、密码、UUID 和其他可复用凭据；临时调试结束后恢复正常日志级别。
- 目标 SNI 要从 VPS 实测。注意 Xray 的目标站警告及官方当前建议；不固定使用 Microsoft，也不因为某个站点曾连通就宣称长期稳定或无法识别。

官方参考：

- [Xray 发布](https://github.com/XTLS/Xray-core/releases/latest)
- [REALITY 配置](https://xtls.github.io/en/config/transports/reality.html)
- [VLESS 入站和 Vision](https://xtls.github.io/en/config/inbounds/vless.html)
- [Mihomo REALITY 版本门槛问题](https://github.com/MetaCubeX/mihomo/issues/2967)
- [Mihomo REALITY 客户端实现](https://github.com/MetaCubeX/mihomo/blob/Meta/component/tls/reality.go)
- [Mihomo VLESS](https://wiki.metacubex.one/config/proxies/vless/)

## 安装与服务

Linux/systemd 下可隔离使用这些路径，已有约定时沿用实际环境：

- Xray 二进制：`/opt/reality-vless/bin/xray`。
- 服务端配置：`/etc/reality-vless/config.json`，例如 `root:reality-vless`、`0640`，父目录 `0750`。
- 独立服务：`reality-vless.service`；使用专用系统账户，低端口所需 `CAP_NET_BIND_SERVICE`，设置失败重启和开机启动。
- 订阅文件：`/var/lib/reality-subscription/config.yaml`，Web 工作账户只读；没有必要暴露原始 SOCKS5 端口或额外管理面板。

默认代理端口 `443`、HTTPS 订阅端口 `8443`、HTTP-01 验证端口 `80`，它们与 SSH 端口相互独立。先检查占用、系统防火墙及云端安全组。只开放本次需要的入口，不清空规则，不调整无关服务或 SSH 登录策略。

配置生成器把直连出口的域名策略放在 `streamSettings.sockopt.domainStrategy`，避免复用已弃用的 `freedom.settings.domainStrategy`。

有住宅时，两个入站用户分别标记为 `vps@reality.local`、`residential@reality.local`。后者由服务端路由至 SOCKS5；无住宅时只有 VPS 用户与直接出口。原始住宅认证只出现在服务端所需的私密配置中。

本流程在上述 Xray 版本使用并实测通过的是扁平 `settings.address/port/user/pass` SOCKS 出站结构。不要凭旧版示例擅自改成 `servers/users`；核心版本不同时，核对该版本的 [官方 SOCKS 出站配置](https://xtls.github.io/en/config/outbounds/socks.html)。

## 订阅与续期

生成器输出：

- `Clash-VPS-住宅.yaml`：完整客户端配置与分流。
- `server.json`：Xray 服务端配置。
- `deployment-private.json`：本次密钥、UUID、端口和令牌状态；重试复用，跨 VPS 使用新的输出目录。
- `subscription.url`：拟用的 HTTPS 地址；外部验证通过后才能宣布上线。
- `acme-webroot-nginx.conf`：证书签发前的 HTTP-01 入口。
- `subscription-nginx.conf`：证书存在后启用的 HTTP-01 和 HTTPS 订阅入口。

生成器的校验不覆盖 Mihomo 全部规则语法。用户提供新规则时，必须用拟部署的 Mihomo 内核校验；只有离线文件且没有内核时，将语法兼容性标记为未验证。仅本地准备无需提供 SSH 认证，候选 SNI 也不得被描述为已经探测通过。

这些 Nginx 文件是独立站点片段。先检查已安装的 Web 服务和配置结构，合并、备份并测试后再加载，不用它们覆盖整份主配置。脚本中的证书路径采用 `/etc/letsencrypt/live/<server>/`；实际证书名称不同或使用其他 ACME 客户端时，要对应调整。

有域名就验证域名解析和所用 ACME 验证方式。只有公网 IP 时，核对当前 CA 与 ACME 客户端是否支持 IP 证书。在已验证的方案中：

1. 用 HTTP-only 配置提供 `/.well-known/acme-challenge/`，先从公网验证端口 80 可达。
2. Certbot **5.4 或更新版本**可使用 webroot 申请 IP 证书，选择 Let's Encrypt 的 `shortlived` profile；域名证书使用对应域名参数。优先使用独立虚拟环境，避免替换系统 Python。
3. IP 签发示例：

   ```bash
   certbot certonly --webroot -w /var/www/reality-acme --preferred-profile shortlived --ip-address 198.51.100.10 --cert-name 198.51.100.10
   ```

   示例 IP 是文档地址，实际命令使用用户的 IP；账户注册、联系邮箱与非交互参数按实际授权和环境配置。

4. 证书就绪后再加载 HTTPS 配置，保持订阅只在随机令牌路径可读，不提供整个输出目录，也不托管 `server.json` 或私密状态文件。
5. IP 证书期限较短，应配置自动续期，例如 systemd timer 每 12 小时检查一次，`Persistent=true`，并加适度随机延迟。部署钩子先 `nginx -t`，再重载 Nginx；HTTP-01 路径持续可达。
6. 用 `certbot renew --dry-run --run-deploy-hooks --no-random-sleep-on-renew` 验证续期与钩子，并检查定时器实际运行状态。

没有可信证书或托管受阻时，交付可导入的本地 YAML，明确说明订阅尚未发布。不要擅自使用公开第三方订阅转换服务上传节点凭据，不把 HTTP 或自签证书伪装成已验证的可信 HTTPS。

官方参考：[Let's Encrypt IP 证书与 Certbot](https://letsencrypt.org/2026/03/11/shorter-certs-certbot.html)。上述参数有版本条件，实施时重新核对。

## 端到端验证

1. 在 VPS 先测直接出口；有住宅时，通过受保护文件向 SOCKS5 提供认证，测得真实住宅出口。服务地址可能是网关，不能据此猜测出口 IP。
2. 运行服务端配置测试，启动并检查服务，再把最终客户端 YAML 下载到本地私密目录。
3. 使用独立的 Mihomo 测试目录、未占用的本地代理端口；控制 API 只绑定 `127.0.0.1` 并设置私密令牌。不改用户日常代理或全局网络设置。
4. 用实际配置测试每个节点。可通过控制 API 切换 `PROXY`，保留其他分组跟随 `PROXY`，确保目标不会命中 `DIRECT`。`https://api.ipify.org` 与 `https://www.cloudflare.com/cdn-cgi/trace` 曾用于两个独立 HTTPS 目标；不可达时换同等目标，不把服务商拒绝访问与握手失败混为一谈。
5. 测试 curl 显式指定本次本地代理，并使用 `--noproxy ''` 避免环境变量绕过。核对实际路由、TLS 成功和出口 IP；只测服务器 curl、TCP 端口或配置语法都不等于节点可用。
6. 无住宅只宣告一个节点；有住宅必须逐个验证。TCP 验证不能证明 UDP 可用。若用户要求住宅 UDP，另测 SOCKS5 UDP ASSOCIATE 及完整链路，再启用客户端 UDP。

首次启动可能要下载 GEOIP 数据，因为规则含 `GEOIP,CN,DIRECT`。下载失败时使用官方数据源补齐；SFTP 可限制预取并发为 32。传到独立临时文件，确认大小、完整性与传输完成后原子替换，**不要在文件仍下载时让 Mihomo 加载，也不要覆盖活跃写入中的文件**。测试完关闭临时进程和端口。

## 分流与 TUN

内置模板保留 247 条规则的原始顺序：DeepSeek 直连规则优先于后面的 AI 规则，国内 IP 直连，未命中流量进入“国外网站”。`PROXY` 默认 VPS；AI、流媒体、国外网站分组默认跟随 `PROXY`，也可以单独选节点。

- TUN 接管进入虚拟网卡的流量，运行模式仍决定后续分流；开启 TUN 不自动变成全局住宅。
- 规则模式下，`PROXY` 选住宅后，命中 `DIRECT` 的流量仍直连；跟随 `PROXY` 的分组走住宅，单独选其他节点的分组按各自选择。
- 用户明确要求全局时，说明“开启 TUN → 运行模式全局 → `GLOBAL` 选住宅”。这不保证未被 TUN 接管的流量、DNS、IPv6 或不受支持的 UDP 都从住宅出口发出。
- 仅解释上述行为不需要登录 VPS 或修改订阅。用户未要求改模式时，保留规则模式及现有规则。

官方参考：[运行模式](https://wiki.metacubex.one/config/general/#运行模式)、[TUN](https://wiki.metacubex.one/config/inbound/tun/)。
