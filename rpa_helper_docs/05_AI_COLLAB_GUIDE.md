
# AI 协作开发指南（Vibe Coding）

## 推荐方式

使用：

- ChatGPT
- Cursor
- Claude Code
- Windsurf

## 推荐开发顺序

1. 先做找图点击
2. 再做流程引擎
3. 再做 GUI
4. 最后做 OCR

## 推荐 Prompt

### Prompt 1

请帮我实现 Python 图像识别点击模块：

功能：
- 使用 pyautogui
- 根据 png 找按钮
- 返回中心坐标
- 支持 confidence 参数

### Prompt 2

请帮我实现 workflow.yaml 流程执行器：

支持：
- click_image
- input_text
- wait
- confirm

### Prompt 3

请帮我实现 PyQt6 GUI：

包含：
- 开始按钮
- 停止按钮
- 流程选择器
- 日志输出区域

## 推荐原则

- 先 MVP
- 不要一开始做录制器
- 不要先做 OCR
- 不要先做 Selenium
