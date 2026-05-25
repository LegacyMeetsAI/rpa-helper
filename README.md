# RPA Helper

面向办公场景的本地化 Web 自动化工具。专注「打开网页 → 操作 → 批量下载附件」这一类高频但繁琐的工作，所有操作都通过浏览器录制 + 流程编辑完成，不依赖任何云端服务。

## 功能特性

- 🌐 **纯浏览器自动化**：内置 Playwright + Chromium，无需用户额外安装浏览器；
- 🎬 **可视化录制**：在真实页面里点点点，自动生成可回放的步骤；
- 🧩 **占位符与变量**：`{{today}}` / `{{prompt:科室}}` / `{{order_id}}` 等占位符，支持「提取页面文本 → 后续步骤复用」；
- 🔁 **循环步骤**：对表格行或字符串列表批量执行同一组子步骤；
- ⏸️ **人工确认**：遇到验证码 / 滑块时弹窗等待，手工处理完再继续；
- 📦 **一键打包**：PyInstaller 打包为单目录 exe，免 Python 环境部署。

## 运行方式（开发模式）

```powershell
pip install -r requirements.txt
# 首次需要安装 Playwright 自带的 Chromium
python -m playwright install chromium
python -m rpa_helper.main
```

主窗口分四个页面：

| 页面 | 用途 |
| --- | --- |
| 执行面板 | 选择流程、点「开始」运行；实时显示当前步骤与日志 |
| 流程编辑 | 新建 / 编辑 / 删除流程文件；按步骤增删改 |
| 浏览器录制 | 打开 URL，在网页里操作，结束后自动把步骤追加到当前流程 |
| 运行日志 | 查看 `logs/runtime.log` 内容 |

## 步骤类型

| 类型 | 用途 |
| --- | --- |
| `wait` | 等待 N 秒（可被「停止」打断） |
| `confirm` | 弹窗让人工确认是否继续 |
| `browser_open` | 启动浏览器并跳转到 URL；可指定持久化目录复用 Cookie |
| `browser_close` | 关闭浏览器（流程结束会自动关，通常无需显式调用） |
| `browser_click` | 点击元素 |
| `browser_input` | 表单输入文本（支持占位符） |
| `browser_wait_for` | 等待元素出现，规避「点击太早」问题 |
| `browser_extract` | 抓取元素的文本或属性，存入变量供后续步骤使用 |
| `browser_download` | 触发下载并保存文件到 `save_dir`（支持 `{{order_id}}` 自动分桶） |
| `browser_go_back` | 浏览器返回上一页 |
| `for_each` | 循环：遍历选择器命中的元素或字符串列表，对每项执行子步骤 |

## 快捷键

- **F8**：开始执行当前流程
- **ESC**：停止正在执行的流程

## 占位符

字段值里出现 `{{...}}` 会在执行时被替换：

| 占位符 | 含义 |
| --- | --- |
| `{{today}}` | 当天日期 `YYYY-MM-DD` |
| `{{now}}` | 当前时间 `YYYY-MM-DD HH:MM:SS` |
| `{{date:%Y%m%d}}` | 自定义 strftime 格式 |
| `{{env:FOO}}` | 读取环境变量 |
| `{{prompt:科室}}` | 弹窗让用户输入；同一次执行内只问一次 |
| `{{prompt:科室\|default=门诊}}` | 同上，带默认值 |
| `{{order_id}}` | 取 `browser_extract` 保存的变量；或 `for_each` 的循环项 |

## 流程文件

流程以 YAML 形式保存在 `config/` 目录下，每个 `.yaml` 文件一份流程。新建流程默认 `steps: []`，进入「流程编辑」页再逐步添加。

示例（按订单号批量下载附件）：

```yaml
name: 月度账单下载
steps:
  - type: browser_open
    name: 打开 OA
    url: https://oa.example.com/orders
    user_data_dir: browser_profile

  - type: confirm
    name: 登录确认
    message: 已完成扫码登录？

  - type: for_each
    name: 遍历订单
    selector: table.orders tr.row
    as: row_idx
    steps:
      - type: browser_extract
        selector: 'table.orders tr.row:nth-child({{row_idx_one_based}}) .id'
        save_as: order_id
      - type: browser_download
        trigger_selector: 'table.orders tr.row:nth-child({{row_idx_one_based}}) a.dl'
        save_dir: downloads/{{today}}/{{order_id}}
```

## 打包成可分发的 exe

```powershell
scripts\package.ps1
```

或：

```bat
scripts\package.bat
```

构建脚本会：

1. 调用 PyInstaller 生成 `dist/RPAHelper/`；
2. 把 Playwright Chromium 一并打包到 `_internal/playwright/...` 目录；
3. 删除占用空间的多余文件，控制最终体积在 ~750 MB。

分发给最终用户时把整个 `dist/RPAHelper/` 拷过去即可，运行 `RPAHelper.exe` 会在 exe 同级目录创建：

```
RPAHelper/
  RPAHelper.exe
  _internal/...
  config/        # 用户编辑的流程文件
  logs/          # 运行日志
  downloads/     # 下载附件落到这里（按 save_dir 配置）
```

## 目录结构

```
rpa_helper/
  main.py                程序入口（PyQt6 QApplication）
  core/
    workflow_engine.py   流程串行执行引擎
    browser_controller.py  Playwright 浏览器控制器
    browser_recorder.py    浏览器录制后端
    placeholder.py       {{...}} 占位符渲染器
    variable_store.py    带作用域栈的变量存储
    safety.py            跨线程「停止」旗标
    workflow_loader.py   读取并校验 YAML
    workflow_writer.py   把内存中的 Workflow 序列化回 YAML
    step_handlers/       每种步骤一个 handler，自动注册到 registry
  ui/
    main_window.py       PyQt6 主窗口（4 个页面）
    step_dialog.py       步骤编辑对话框
    step_schemas.py      步骤 → 表单字段的映射表
    form_fields.py       数据驱动的表单字段描述符
    error_translator.py  把异常翻译成对用户友好的中文提示
    controllers/
      workflow_store.py  流程文件的增删改查
      workflow_editor.py 单流程内的步骤增删改查
tests/                   pytest 单元测试
scripts/                 PyInstaller 打包脚本
```

## 开发与测试

```powershell
# 跑全部单元测试
python -m pytest

# 仅跑某一个文件
python -m pytest tests/test_workflow_engine.py -v
```

代码规范：

- 所有源文件统一使用中文注释，类与方法都带文档字符串；
- 关键代码行附简短行内注释解释「为什么这么写」；
- 类注释末尾以 `Author: huaiqing.wang` 标注作者。
