# 参赛提交指引（SUBMISSION.md）

本文档不参与运行，仅作为提交参赛时的操作清单和文案底稿。
**提交前请通读一遍，尤其是「格式红线」部分。**

---

## 一、发布仓库（先做这个）

```bash
cd maimen-wrapped
git init
git add .
git commit -m "feat: 麦麦年报 Maimen Wrapped v1.0"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB>/maimen-wrapped.git
git push -u origin main
```

推送后到 GitHub 仓库 Settings 确认：**仓库可见性为 Public**。

### 提交前必须改掉的两个占位符

| 文件 | 要改的内容 |
|---|---|
| `README.md` | 克隆命令里的 `<YOUR_NAME>` |
| `LICENSE` | 版权行的 `<YOUR_NAME>` |

### 发布前最后检查

- [ ] README / LICENSE 里的 `<YOUR_NAME>` 已替换为真实 GitHub 用户名
- [x] `workbuddy.md` 已由真实会话导出，且为**精简脱敏版**（`tools/export_workbuddy_md.py --brief --redact` 生成）
  - 完整版另存为 `workbuddy.full.md`（同样已脱敏）
  - 若之后还有新的开发会话，重跑导出命令即可刷新，脚本会自动裁到最新一次提问
- [x] 已跑 `python tools/check_redaction.py`：无本地路径、用户名、会话 ID、账号数据、真实凭证残留
  - 该脚本会扫描全仓库，**推仓库前建议再跑一次**；`.idea/` 等 IDE 状态文件已在 `.gitignore` 中排除
- [ ] `.mcd-wrapped-raw/`、`raw/`、个人订单 JSON **不在**暂存区（`.gitignore` 已配置，但 `git add` 后建议 `git status` 再看一眼）
- [ ] `examples/demo-report.html`、`examples/demo-card.png` 已包含（README 引用了它们）

---

## 二、报名 Issue 文案

### Issue 标题

```text
麦麦年报（Maimen Wrapped）：把你的麦当劳订单变成一张能截图发出去的年度报告
```

### Issue 正文（原样复制，替换 URL）

```text
【参赛申请】
项目名称：麦麦年报
项目地址：https://github.com/<YOUR_GITHUB>/maimen-wrapped
项目简介：这一年在麦当劳花了多少钱、几点吃最凶、最爱点什么——读取你的真实订单历史，在本地生成一份零外部依赖的单文件 HTML 年报与一张 1080×1440 竖版分享卡，可直接截图发社交媒体。
```

---

## 三、格式红线（这一步错一个字就报名失败）

活动方明确提示报名 Issue 校验逻辑严格，以下按重要度排序：

1. **`项目地址` 必须是裸 URL**。不要写成
   `[xxx](https://...)` 或加任何 Markdown 语法、反引号、尖括号。
2. **每个 `字段：` 和它的值必须在同一行**。特别是 `项目简介：` 后面
   不要换行再写内容。
3. **标签行之间不要插空行**。整个正文就是连续四行，中间不要有空行。
4. **正文第一行必须是 `【参赛申请】`**，不要在它前面加问候语或别的字。
5. Issue **标题**里不要出现换行符。
6. 提交后盯紧 Issue 下的系统回复：
   - 回复成功通知 → 报名完成，去 `RANKING.md` 看自己有没有上榜
   - 回复失败原因 → 按原因修改后**重新提交一个新 Issue**

### 如果反复失败的 Plan B

系统可能对换行更敏感。把整个正文压成更紧凑的形态再试一次：

```text
【参赛申请】项目名称：麦麦年报 项目地址：https://github.com/<YOUR_GITHUB>/maimen-wrapped 项目简介：（同上）
```

即所有内容在同一行、仅用空格分隔。两种都试过仍失败，
联系麦当劳顾客中心 400-920-0205（每天 9:00–18:00）。

---

## 四、关键时间（北京时间）

| 事项 | 时间 |
|---|---|
| 报名及排名截止 | **2026-10-25 23:59** |
| 定榜数据采集 | 2026-10-26 00:00 |
| 兑奖信息提交截止 | 2026-11-14 |

**Star 需要发酵时间，仓库越早公开越好。** 活动开始前已获得的 Star 也计入排名。

---

## 五、拉星提醒（合规）

活动规则明确把「刷榜、操纵 Star 数据、多账号、串通」列为不正当手段，
一经发现**直接取消资格**。所以：

- ❌ 不要买 Star、不要大规模互刷、不要多账号
- ✅ README 顶部放一句能脱离上下文被截图转发的金句（已写好）
- ✅ 写一篇掘金 / 知乎 / 小红书帖子介绍项目，结尾放仓库链接
- ✅ 直接把 `examples/demo-card.png` 发到社交平台——它本身就是成品素材
