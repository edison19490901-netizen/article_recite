# 背诵宝 📖

从**中文/英文文章、博客、演讲稿、字幕**生成**可背诵的材料包**：AI 把原文切成意群块，配上艾宾浩斯复习计划，一次生成：

| 板块 | 内容 |
|------|------|
| **原文意群分块** | AI 按语义切分意群块（每块独立成义），逐字保留原文 |
| **提示卡** | 每块的背诵提示：AI 关键词 + 首字/首字母提示（英文材料） |
| **遮罩自测** | 一键遮住原文，看提示卡试着背出来 |
| **逐块复习表** | 每块背完后第 1/2/4/7/15 天复习（间隔可配） |
| **每日打卡清单** | 每天「新背几块 + 复习哪几块」，点击打卡，进度保存在本机浏览器 |
| **打印 / 导出 PDF** | 一键打印，生成纸质背诵单 |

## 与「智读」的分工

| 工具 | 解决什么问题 |
|------|-------------|
| **智读**（article_understand） | 读懂材料：口播总结、结构解构、实际应用、金句单词 |
| **背诵宝**（本仓库） | 背下材料：意群分块、复习计划、遮罩自测、打卡 |

先「智读」读懂，再用「背诵宝」背下来，形成完整的学习闭环。

## 快速开始

### 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置 DeepSeek API Key
#    复制 .env 文件或设置环境变量
export DEEPSEEK_API_KEY="sk-xxxx"   # 获取: https://platform.deepseek.com/api_keys

# 3. 启动 Web 界面
python app.py
# 浏览器打开 http://localhost:5000

# 4. 或命令行直接生成
#    从网页文章 URL
python -m article_recite "https://example.com/blog/post"
#    从本地文件
python -m article_recite --file speech.srt --title "演讲稿标题"
#    从 stdin 粘贴
cat article.txt | python -m article_recite --title "文章标题"
```

运行后在 `output/<材料>/recite.html` 生成背诵看板，手机/浏览器直接打开。

### 输入方式

| 方式 | 说明 |
|------|------|
| 粘贴文本 | 直接把文章/演讲稿/字幕正文粘贴到网页或 stdin |
| 链接 | 网页文章链接自动抓取正文（博客等） |
| 文件 | `.srt` 按字幕处理；`.txt` / `.md` / `.docx` / `.pdf` 按文章处理 |

语言自动检测（中文/英文），英文材料额外生成首字母提示卡。

## 生成流程

```
输入（文本 / URL / 文件）
  → 清洗解析（去噪声、保段落）
  → 语言检测（zh / en）
  → DeepSeek 意群分块（一次调用，输出 JSON：chunks + hint + advice）
  → 艾宾浩斯计划（确定性计算，间隔 1/2/4/7/15 天）
  → 交互式背诵看板 recite.html
```

意群分块由 AI 完成（语义精准，每篇约 ¥0.001-0.01）；复习计划是纯本地计算，不额外花钱。

## 艾宾浩斯计划说明

- 默认间隔：**第 1 / 2 / 4 / 7 / 15 天**（对应背完当天之后的第 1、2、4、7、15 天）
- 每天新背块数：按材料块数自动确定（块多则每天多背），看板里可手动调整
- 每日清单按「开始背诵日」排日历日期，点块号打卡，进度存于浏览器 localStorage，刷新不丢失

## 项目结构

```
article_recite/
├── app.py                 # Flask Web（首页 / 处理 / 结果 / 文库）
├── manifest.json          # PWA 清单
├── static/                # 图标（recite.png 多尺寸）+ service worker
├── output/                # 生成的背诵看板（每篇一个目录）
├── article_recite/        # 核心包
│   ├── parser.py          # 清洗、语言检测、字数统计、文件解析
│   ├── downloader.py      # 网页文章抓取
│   ├── prompts.py         # 意群分块 prompt 模板
│   ├── analyzer.py        # DeepSeek 调用 + 健壮 JSON 解析
│   ├── planner.py         # 艾宾浩斯计划（确定性计算）
│   ├── cli.py             # 命令行入口
│   └── outputs/
│       └── recite_book.py # 背诵看板 HTML 生成
│   └── templates/
│       └── recite.html.j2 # 背诵看板模板（含交互 JS）
```

## Render 部署 + 安装到手机

仓库已包含 `render.yaml`（Blueprint），Render 部署接近一键完成：

1. 打开 https://dashboard.render.com ，用邮箱或 GitHub 注册登录（免费）
2. 点右上角 **New +** → **Blueprint**
3. 首次需授权 GitHub：Connect account → 选择仓库 `edison19490901-netizen/article_recite` → 授权
4. Render 识别到 `render.yaml`，列出 `article-recite` 服务 → 点 **Apply** 开始部署（约 2-5 分钟）
5. 部署完成后：
   - 服务页 → **Environment** → 添加变量 `DEEPSEEK_API_KEY` = 你的 API Key → **Save** → 顶部 **Manual Deploy → Deploy latest commit** 重启生效
   - 服务顶部拿到 HTTPS 地址，形如 `https://article-recite.onrender.com`
6. **手机安装为 App（图标 = recite.png）**：
   - **Android（Chrome）**：手机打开该网址 → 菜单 ⋮ → 「添加到主屏幕 / 安装应用」
   - **iPhone（Safari）**：打开网址 → 分享 → 「添加到主屏幕」
   - PWA 已配置好：多尺寸 recite.png 图标（含 Android 自适应 maskable）、Service Worker 离线可用

> 免费版 Render 服务空闲 15 分钟后休眠，重新打开约需 30 秒唤醒，属正常现象。
> 国内访问 render.com 一般可用；若太慢可换 Zeabur 等平台，接同一个 GitHub 仓库即可。

### 传统配置项（手动部署时用）

| 配置项 | 值 |
|--------|-----|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT` |
| Environment Variable | `DEEPSEEK_API_KEY` = 你的 API Key |

## 依赖

- **Flask** — Web 界面
- **openai** — DeepSeek API（OpenAI 兼容）
- **trafilatura** — 网页文章正文提取
- **python-docx / pypdf** — Word / PDF 解析
- **Jinja2** — 模板渲染
- **Click** — CLI 框架
