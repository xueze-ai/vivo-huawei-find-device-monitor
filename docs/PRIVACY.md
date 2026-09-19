# 隐私与安全

这个项目处理登录会话、精确位置、家庭成员名称和通知凭据。部署时应把这些内容当作敏感数据。

## 永远不要提交到 Git

- `.env` 与 Server 酱 SendKey
- `vivo/config.json` 中的设备 ID、联系人姓名、真实围栏坐标
- `data/` 下的浏览器配置、Cookie、SQLite 数据库和最后定位
- 登录账号、密码、短信验证码、二维码截图
- 服务器公网 IP、SSH 私钥和运维日志

仓库的 `.gitignore` 已覆盖常见敏感文件，但不能替代人工检查。每次推送前建议运行：

```bash
git status --short
git diff --cached
git grep -nE 'SCT[0-9A-Za-z]{10,}|password|session-cookies|monitor\.sqlite'
```

## 部署建议

1. noVNC 只监听 `127.0.0.1`，通过 SSH 隧道临时访问，不向公网开放端口。
2. `data/` 权限设置为仅服务账号可读写，例如 `chmod -R 700 data`。
3. 使用专门的低权限服务器账号运行容器。
4. 定期轮换 Server 酱 SendKey、服务器密码和 SSH 密钥。
5. 仅监控本人设备，或已经得到设备所有者明确授权的设备。

## 公开仓库检查清单

- [ ] `git status` 中没有 `.env`、`data/`、`config.json`
- [ ] README 截图没有地址、姓名、手机号或设备编号
- [ ] Git 历史中没有曾经提交过的秘密
- [ ] 示例坐标与示例姓名不对应真实家庭成员
