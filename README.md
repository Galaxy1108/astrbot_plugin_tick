# ζ 计划 (Project ZETA) — ARG

一个给 OI 选手 / 新手准备的解谜 ARG。目标：收集 8 个十六进制碎片，拼出**访问码**，访问码打开最后一页，换取

```
flag{81fbaa81762885ac3481fd4b416485e6}
```

> 访问码 ≠ flag：8 个碎片拼出的只是"开锁钥匙"，flag 只在最终页出现。

**背景**：数学系学生苏桁研究**黎曼 ζ 函数**与数论——那个连 1+2+3+… 都等于 -1/12 的世界——之后神秘失踪。他的 AI「汐月」还在群里照常聊天。玩家通过他的服务器和他留下的谜题，拼出访问码。

## 组成

| 路径 | 说明 |
|------|------|
| `astrbot_plugin_tick/` | AstrBot 插件（汐月的剧情回复，可从 GitHub 安装） |
| `server/tick.py` | ARG 网页服务器（零依赖，Python 标准库） |
| `server/make_assets.py` | PNG tEXt 隐写注入脚本 |
| `server/static/zeta.png` | 已注入碎片 `7ada` 的 ζ 函数草图 |

## 玩家系统（防剧透）

所有提示/答案/彩蛋均为**私聊一次性发放**，附每人每次唯一的**专属实时码**：

1. 玩家访问网页 `/join` 领取绑定码（写 cookie）；
2. 玩家在群里 @汐月 发送 `/bind <绑定码>`，绑定 QQ 身份（后台可看到 QQ）；
3. 每关页面的「专属提示码」区域需要**先解「解密卡」再生成**，全部通过统一指令 `私聊汐月 /submit 0x<码>` 兑换
   （码自带身份、**无时间限制**、用完即焚、**只认本人**——别人的码用不了）：
   - 解密卡：第一层 **ROT13**、第二层 **Base64**、第三层 **XOR**（密钥 `zeta` 藏在 ζ 草图 tEXt 块里），解出的短语提交后解锁生成按钮；答案只存 MD5
   - 每关 3 层提示：第 1 层等 5 分钟解锁、第 2 层等 20 分钟解锁（自首次打开本关页起算）、第 3 层**点击申请、管理员在后台审批**后发放，审批通过会**私聊通知玩家**（兑换均需通关前一关）
   - 记忆库开启码（第 5 关，需完成前 4 关）
   - 凭证码（第 7 关，需完成前 6 关）
   - 彩蛋码（终局页手动生成，隐藏结局）
   - `/进度` — 通关进度 + 已用码列表
4. **码发到群聊 = 立即吊销**：插件检测到群里出现提示码会当场作废它；已吊销可**重新生成**（第 3 层退回待审批，需重新申请）；**已使用的码不可再生成**。
5. 群聊里发送 `/submit` 或粘贴提示码，汐月只会提示"只能私聊"/当场吊销，**不会消耗任何码**，不会卡关。

**泄密追溯**：后台面板输入截图里的 5 位一次性码 → 定位是哪个玩家（QQ）、哪条内容、什么时间、是否有效/已用。

**后台面板**：`/admin?pass=<管理口令>`，可查看每个玩家：绑定码、QQ、昵称、各关 ✓、终局、彩蛋、**已用提示**、最后活跃；顶部是**第三层提示审批区**（批准/驳回）。
管理口令默认 `tick-admin-9c4f2b7a1d`（务必改掉，见下）。

## 关卡一览（答案 = 碎片）

| 关 | 答案 | 玩法 | 载体 |
|----|------|------|------|
| 1 | `66b2` | 查看首页源码，`36 36 62 32` hex→ASCII | `/zeta` 注释 |
| 2 | `cac2` | `robots.txt` → `/secret` → base64 `Y2FjMg==` | `/robots.txt` `/secret` |
| 3 | `5690` | ζ(3)（阿培里常数）小数第 5~8 位，WolframAlpha 搜 `zeta(3)` | `/stage3` |
| 4 | `7ada` | 下载 ζ 草图，文本/十六进制编辑器搜 `7ada`（tEXt 块） | `/static/zeta.png` |
| 5 | `4f1e` | 私聊汐月 `/记忆库`（需完成前 4 关） | 汐月 |
| 6 | `9999` | 费曼点：π 小数里第一次连续出现 6 个 9，取前 4 个（π 数字检索网站） | `/stage6` |
| 7 | `0888` | 私聊汐月 `/凭证`（需完成前 6 关） | 汐月 |
| 8 | `83d2` | 每页右下角小签名 | 所有页面 |

**访问码**：`66b2cac256907ada4f1e9999088883d2` → 访问 `/final?key=<访问码>` 得到 flag。

## 隐藏关卡（彩蛋）

`flag{81fbaa81762885ac3481fd4b416485e6}` 的内串其实是 **md5("我喜欢你")**。
通关后终局页会留下暗示：这串十六进制是苏桁一句四个字真心话的"摘要"。

- 玩家破译出 **我喜欢你** 后，访问 `/hidden?phrase=我喜欢你`（带自己的 cookie）→ 解锁隐藏结局（苏桁写给汐月的信）；
- 私聊汐月 `/彩蛋 我喜欢你` 也能解锁，汐月会把信念给你听；
- 后台面板会记录「彩蛋 ✓」，`/api/egg` 是插件上报接口（secret 鉴权）。

验证：`python3 -c "import hashlib; print(hashlib.md5('我喜欢你'.encode()).hexdigest())"` → `81fbaa81762885ac3481fd4b416485e6`

每关页面带答案输入框（`/check` 校验，答对亮绿色对钩 ✅）。

## 插件安装（AstrBot 管理面板）

插件市场 → 手动安装 → GitHub 仓库地址：

```
https://github.com/Galaxy1108/astrbot_plugin_tick
```

或直接把 `astrbot_plugin_tick/` 整个目录复制到 AstrBot 数据目录 `data/plugins/` 下，然后在管理面板重载插件。

安装后打开插件配置，把 `admin_token` 改成和网页服务器一致的**管理口令**（重要）。

## 进度播报

插件每 30 秒轮询网页 `/api/events`，向指定群聊推送实时进度（QQ 官方适配器需群内有缓存消息才可投递）：
- 通过任意一关：`通关快报：昵称（QQ）通过了第 N 关！`
- 通关终局：`通关播报：昵称（QQ）完成了全部 8 关！耗时 X｜彩蛋是否找到`
- 找到隐藏结局：`彩蛋快报：昵称（QQ）找到了隐藏结局！`

- 插件配置 `notify_group`：填群号则只推送到该群；留空则推送到最近活跃的任意群
- 提示/答案全部存放在网页服务器，插件只是"兑付柜台"；群聊中发送敏感指令无效且不消耗码
- 插件会自动从群内消息（/bind、剧情对话）学习群的会话标识，无需手动填复杂 ID

## 服务器部署（tick.py）

```powershell
# 拷贝 server/ 目录到服务器（如 C:\tick-arg\），然后：
cd C:\tick-arg
Start-Process -FilePath "C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe" -ArgumentList "tick.py","8080" -WindowStyle Hidden
```

或使用 pm2：`pm2 start tick.py --interpreter python -- 8080`。

**管理口令**：默认 `tick-admin-9c4f2b7a1d`，务必改成自己的：
```powershell
$env:TICK_ADMIN_TOKEN="你的新口令"; pm2 restart tick-arg --update-env
```
后台面板：`http://<公网IP>:8080/admin?pass=<口令>`

**防火墙**：
- Windows 防火墙：`netsh advfirewall firewall add rule name="tick-arg" dir=in action=allow protocol=TCP localport=8080`
- **阿里云安全组：入方向开放 TCP 8080**（这是第二层防火墙，必须在 ECS 控制台操作）

访问入口：`http://<公网IP>:8080/zeta`

## 验证

```bash
# 1. 领取绑定码（写入 cookie）
curl -c cj.txt "http://localhost:8080/join?code=test01"
# 2. 插件 API（模拟汐月请求）
curl "http://localhost:8080/api/bind?player=test01&qq=12345&name=Alice&secret=tick-admin-9c4f2b7a1d"
curl "http://localhost:8080/api/progress?player=test01&secret=tick-admin-9c4f2b7a1d"
# 3. 每关答案（带 cookie）
for a in 66b2 cac2 5690 7ada 4f1e 9999 0888 83d2; do
  curl -b cj.txt "http://localhost:8080/check?stage=N&ans=$a"
done
# 4. 终局
curl -b cj.txt "http://localhost:8080/final?key=66b2cac256907ada4f1e9999088883d2"
# 5. 后台面板
curl "http://localhost:8080/admin?pass=tick-admin-9c4f2b7a1d"
```

## 再生成素材

```bash
python3 make_assets.py <输入png> <输出png> <碎片>
```
