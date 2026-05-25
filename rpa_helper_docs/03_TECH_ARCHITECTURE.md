
# 技术架构设计

## 技术栈

- Python
- PyAutoGUI
- OpenCV
- Pillow
- PaddleOCR
- PyQt6
- YAML

## 架构图

用户操作
  ↓
GUI
  ↓
Workflow Engine
  ↓
Image Matcher
  ↓
Mouse Controller
  ↓
OCR Engine
  ↓
Logger

## 项目目录

```
rpa_helper/
├── main.py
├── config/
├── images/
├── core/
├── ui/
├── logs/
└── requirements.txt
```

## 核心模块

### Workflow Engine

职责：

- 读取 workflow.yaml
- 执行步骤
- 控制流程状态

### Image Matcher

使用：

- OpenCV 模板匹配

API：

- locateCenterOnScreen()

### Mouse Controller

功能：

- moveTo()
- click()
- write()

### OCR Engine

使用：

- PaddleOCR

用于：

- 成功识别
- 错误提示识别

### Safety Manager

功能：

- ESC 强制停止
- 超时停止
- 找不到图片停止
