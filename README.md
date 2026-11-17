# Deep Tutorial：海外网络环境与 AI 服务全流程指南

本教程旨在提供一套从零开始的**海外登录信息准备、网络环境搭建、海外 AI 会员订阅支付、账号获取、反向代理配置到最终客户端/代码接入**的完整实操总览。

---

## 📚 教程目录总览

### [第一章：海外环境与个人梯子搭建](./01-overseas-env-proxy/README.md)
介绍如何准备纯净的海外网络环境，包括海外 VPS 选购、个人专属代理节点（梯子）搭建、指纹浏览器/防关联环境配置，以及海外常用基础登录信息（邮箱、接码等）准备。

### [第二章：海外 AI 会员购买（支付）](./02-ai-subscription-payment/README.md)
讲解主流海外 AI 服务（如 ChatGPT Plus/Pro、Claude Pro、Gemini Advanced、Cursor 等）的官方订阅流程，涵盖虚拟信用卡（VCC）、海外 PayPal、Apple ID 美区礼品卡等合规支付方式与防风控技巧。

### [第三章：卡网购买账号](./03-account-purchase/README.md)
针对不便自行注册或需要批量/现成账号的场景，介绍如何甄别与使用发卡网（卡网）购买成品号、API Key 或共享/独享会员账号，以及改密、绑定二次验证（2FA）等售后安全检查。

### [第四章：反代（反向代理）](./04-reverse-proxy/README.md)
讲解如何通过 Cloudflare Workers、Nginx、Docker 或开源中转服务搭建 API 与 Web 反向代理，解决国内直连受限、跨域、多账号负载均衡及 Key 分发管理问题。

### [第五章：接入](./05-integration/README.md)
介绍如何将获取到的海外 AI 账号或反代 API 接入到实际工具与工作流中，包括开源客户端（NextChat、LobeChat、Cherry Studio）、IDE 插件（Cursor、VS Code、Antigravity）以及业务代码 SDK 调用。

---

## 📁 仓库结构

```text
deep-tutorial/
├── README.md                        # 教程总览（当前文件）
├── .agents/skills/                  # 内置 AI 自动化技能目录（克隆到本地即可被主流 Agent 自动加载）
│   └── deploy-vless-reality/        # VPS 梯子一键部署与 Clash 订阅生成技能
├── 01-overseas-env-proxy/           # 第一章：海外环境与个人梯子搭建
├── 02-ai-subscription-payment/      # 第二章：海外 AI 会员购买（支付）
├── 03-account-purchase/             # 第三章：卡网购买账号
├── 04-reverse-proxy/                # 第四章：反代
└── 05-integration/                  # 第五章：接入
```
