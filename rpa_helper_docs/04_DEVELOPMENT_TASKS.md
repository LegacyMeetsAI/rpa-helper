
# 开发任务拆分

## Phase 1 - MVP

### Task 1：项目初始化

- 创建目录结构
- 安装依赖
- requirements.txt

### Task 2：图像识别模块

功能：

- 根据截图找按钮
- 返回坐标

输出：

- image_matcher.py

### Task 3：鼠标控制模块

功能：

- 点击
- 输入
- 移动

### Task 4：Workflow Engine

功能：

- 读取 YAML
- 执行步骤

### Task 5：日志模块

功能：

- runtime.log

### Task 6：热键模块

支持：

- F8
- ESC

### Task 7：GUI

功能：

- 开始
- 停止
- 选择流程

## Phase 2 - OCR

### Task 8：OCR 模块

使用：

- PaddleOCR

### Task 9：状态识别

功能：

- 提交成功
- 无数据

## Phase 3 - 配置器

### Task 10：截图管理器

功能：

- 框选截图
- 自动保存 PNG

### Task 11：流程编辑器

功能：

- 增删步骤
- 保存 YAML

## Phase 4 - 打包

### Task 12：EXE 打包

使用：

- PyInstaller

命令：

pyinstaller -F -w main.py
