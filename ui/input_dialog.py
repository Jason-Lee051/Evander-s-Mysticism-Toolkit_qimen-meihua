"""
ui/input_dialog.py - 通用输入对话框，支持根据选择动态显示/隐藏字段 + 智能填写
"""
import json
from typing import Dict, Any, List, Optional
from PySide6.QtWidgets import (QDialog, QLineEdit, QComboBox, QDateTimeEdit,
                               QDialogButtonBox, QVBoxLayout, QHBoxLayout,
                               QLabel, QWidget, QTextEdit, QPushButton,
                               QScrollArea, QGroupBox)
from PySide6.QtCore import QDateTime, Qt, QTimer, QThread, Signal
from PySide6.QtGui import QFont

from core.llm.analyzer import load_config


class SmartFillWorker(QThread):
    """后台工作线程：调用 LLM 提取字段，不阻塞 UI"""
    # 注意：不可命名为 finished —— 会覆盖 QThread 内置 finished 信号，
    # 导致 run() 返回时再触发一次回调（重复填充 / 重复调用 AI）。
    extracted = Signal(dict)
    error = Signal(str)

    def __init__(self, text: str, fields: list, method: str = ""):
        super().__init__()
        self.text = text
        self.fields = fields
        self.method = method

    def run(self):
        try:
            # 临时构造一个 Dialog 对象只用于调用 _extract_fields
            dialog = InputDialog.__new__(InputDialog)
            dialog.fields = self.fields
            dialog.method = self.method
            result = dialog._extract_fields(self.text)
            self.extracted.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class InputDialog(QDialog):
    """支持字段级 + 智能填写的通用输入对话框"""

    def __init__(self, title: str, fields: List[Dict[str, Any]],
                 parent=None, method: str = ""):
        super().__init__(parent)
        self.method = method          # 'qimen' | 'meihua' | ''
        self.setWindowTitle(title)
        self.resize(560, 480)
        self.fields = fields
        self.inputs = {}              # name -> widget
        self.rows = {}                # name -> (label_widget, input_widget, container_widget)
        self.conditional_fields = []

        # ---- 主布局（可滚动） ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.scroll_contents = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_contents)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)

        scroll.setWidget(self.scroll_contents)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.addWidget(scroll)

        # ---- 1) 普通字段 ----
        for field in fields:
            name = field.get('name')
            label = field.get('label', name)
            ftype = field.get('type', 'text')
            default = field.get('default', '')
            options = field.get('options', None)
            visible_if = field.get('visible_if', None)

            row_container = QWidget()
            row_layout = QHBoxLayout(row_container)
            row_layout.setContentsMargins(0, 0, 0, 0)

            label_widget = QLabel(label)
            label_widget.setFixedWidth(130)
            row_layout.addWidget(label_widget)

            if ftype == 'select' and options:
                widget = QComboBox()
                widget.addItems(options)
                if default in options:
                    widget.setCurrentText(default)
                else:
                    widget.setCurrentIndex(0)
                if name == 'method':
                    widget.currentTextChanged.connect(self.on_condition_changed)
            elif ftype == 'datetime':
                widget = QDateTimeEdit()
                widget.setCalendarPopup(True)
                widget.setDateTime(QDateTime.currentDateTime())
            else:
                widget = QLineEdit()
                widget.setText(str(default))
                widget.setPlaceholderText(label)

            row_layout.addWidget(widget)
            self.inputs[name] = widget
            self.rows[name] = (label_widget, widget, row_container)
            self.main_layout.addWidget(row_container)

            if visible_if:
                self.conditional_fields.append((name, visible_if))

        self.main_layout.addStretch()

        # ---- 2) 智能填写分组 ----
        smart = QGroupBox("🤖 智能填写（可选）")
        smart_layout = QVBoxLayout(smart)
        smart_layout.setSpacing(4)

        smart_hint = QLabel(
            "粘贴一段包含术数所需信息的自然语言描述，点击「智能填充」后 AI 会自动提取并填入上方字段。"
            "如果某些字段已经手动填写，智能填写结果会覆盖它们。"
        )
        smart_hint.setWordWrap(True)
        smart_hint.setStyleSheet("color: gray; font-size: 11px;")
        smart_layout.addWidget(smart_hint)

        self.smart_text = QTextEdit()
        self.smart_text.setPlaceholderText(
            "例：我想测一下今天去面试能不能成功，地点在北京朝阳区，问的是工作运势。"
        )
        self.smart_text.setMinimumHeight(90)
        self.smart_text.setMaximumHeight(160)
        smart_layout.addWidget(self.smart_text)

        btn_layout = QHBoxLayout()
        self.smart_btn = QPushButton("✨ 智能填充")
        self.smart_btn.clicked.connect(self._on_smart_fill)
        self.smart_status = QLabel("")
        self.smart_status.setStyleSheet("color: #888; font-size: 11px; min-height: 16px;")
        btn_layout.addWidget(self.smart_btn)
        btn_layout.addWidget(self.smart_status)
        btn_layout.addStretch()
        smart_layout.addLayout(btn_layout)

        self.main_layout.addWidget(smart)

        # ---- 3) 按钮行 ----
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Ok).setText("确定")
        self.button_box.button(QDialogButtonBox.Cancel).setText("取消")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.main_layout.addWidget(self.button_box)

        # 初始化可见性
        self.update_visibility()

    # ---- 事件处理 ----
    def on_condition_changed(self, value):
        self.update_visibility()

    def update_visibility(self):
        method_widget = self.inputs.get('method')
        if not method_widget:
            return
        current_method = method_widget.currentText()
        for name, visible_if in self.conditional_fields:
            if visible_if.get('field') == 'method':
                should_show = (visible_if.get('value') == current_method)
                if name in self.rows:
                    _, _, container = self.rows[name]
                    container.setVisible(should_show)

    def get_values(self) -> Dict[str, Any]:
        values = {}
        for name, widget in self.inputs.items():
            if isinstance(widget, QLineEdit):
                values[name] = widget.text()
            elif isinstance(widget, QComboBox):
                values[name] = widget.currentText()
            elif isinstance(widget, QDateTimeEdit):
                values[name] = widget.dateTime().toPython()
        return values

    # ---- 智能填写 ----
    def _on_smart_fill(self):
        text = self.smart_text.toPlainText().strip()
        if not text:
            self.smart_status.setText("请先输入一段描述文字")
            return
        self.smart_btn.setEnabled(False)
        self.smart_status.setText("AI 正在解析…")
        # 用 QThread 子线程调用 AI，避免阻塞主线程导致界面卡死
        self._smart_worker = SmartFillWorker(text, self.fields, self.method)
        self._smart_worker.extracted.connect(self._on_smart_filled)
        self._smart_worker.error.connect(self._on_smart_error)
        self._smart_worker.start()

    def _on_smart_filled(self, extracted: dict):
        """在主线程中安全地更新 UI"""
        # 验证 method 字段合法性（梅花易数特需）
        if 'method' in extracted:
            valid_methods = ['数字起卦', '时间起卦', '汉字起卦']
            if extracted['method'] not in valid_methods:
                extracted['method'] = '时间起卦'
        self._apply_extracted(extracted)
        self.smart_status.setText(f"已填充 {len(extracted)} 个字段 ✓")
        self.smart_btn.setEnabled(True)

    def _on_smart_error(self, err: str):
        self.smart_status.setText(f"解析失败：{err}")
        self.smart_btn.setEnabled(True)

    def _apply_extracted(self, extracted: dict):
        """将提取结果写入字段（在主线程调用）"""
        for key, val in extracted.items():
            if key not in self.inputs:
                continue
            w = self.inputs[key]
            if isinstance(w, QLineEdit):
                w.setText(val or "")
            elif isinstance(w, QComboBox):
                if val and w.count() > 0 and val in [w.itemText(i) for i in range(w.count())]:
                    idx = w.findText(val)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
        # 切换 method 时刷新条件字段可见性
        if 'method' in extracted and 'method' in self.inputs:
            self.on_condition_changed(extracted['method'])
        self.smart_status.setText(f"已填充 {len(extracted)} 个字段 ✓")

    def _extract_fields(self, text: str) -> Dict[str, str]:
        """调用 LLM 从 text 中提取 fields 所需字段，返回 {name: value}"""
        from core.llm.analyzer import _extra_body_for, DEFAULT_BASE_URL, DEFAULT_MODEL
        config = load_config()
        api_key = config.get("api_key", "")
        base_url = config.get("base_url", DEFAULT_BASE_URL)
        model = config.get("model", DEFAULT_MODEL)

        field_names = [f.get('name') for f in self.fields]
        field_labels = {f['name']: f.get('label', f['name']) for f in self.fields}

        if self.method == 'qimen':
            instruction = (
                "你是一位助手。请从用户的自然语言描述中提取以下字段，以 JSON 格式返回：\n"
                "- matter：预测/所问事项（简短概括）\n"
                "- location：所在地点/方位（如城市、方位等）\n"
                "只返回 JSON，不要解释。若无对应信息则该字段为空串。"
            )
        elif self.method == 'meihua':
            instruction = (
                "你是一位助手。请从用户的自然语言描述中提取梅花易数所需字段，以 JSON 格式返回：\n"
                "- method：起卦方式，从以下三项选一个：'数字起卦'、'时间起卦'、'汉字起卦'\n"
                "- num1：第一个数字（整数）\n"
                "- num2：第二个数字（整数）\n"
                "- num3：第三个数字（整数，动爻）\n"
                "- char_text：用于起卦的汉字（汉字起卦时填写）\n"
                "- char_mode：汉字起卦方式，选 '笔画数法' 或 '字数法'\n"
                "- question：所问事项\n"
                "- background：背景信息（可选）\n"
                "只返回 JSON，不要解释。若无对应信息则该字段为空串。"
            )
        else:
            instruction = (
                "请从用户的自然语言描述中提取以下字段，以 JSON 格式返回：\n"
                + "\n".join(f"- {name}：{field_labels.get(name, name)}" for name in field_names)
                + "\n只返回 JSON，不要解释。"
            )

        prompt = f"{instruction}\n\n用户描述：\n{text}"

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=30.0  # 30秒超时，防止卡死
            )
            kwargs = dict(
                model=model,
                messages=[
                    {"role": "system", "content": "你是字段提取助手。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=min(config.get("max_tokens", 2000), 2000),
                temperature=config.get("temperature", 0.7),
                stream=False,
            )
            # 仅对思考型 DeepSeek 模型关闭思考（字段提取不需要思考）；
            # 其他模型不发送该参数，避免不兼容报错
            extra_body = _extra_body_for(model)
            if extra_body:
                kwargs["extra_body"] = extra_body
            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception:
                if extra_body:
                    # 服务端不支持该参数 → 去掉后重试
                    kwargs.pop("extra_body", None)
                    resp = client.chat.completions.create(**kwargs)
                else:
                    raise
            raw = resp.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"AI 调用失败：{e}")

        # 容错：LLM 可能返回 markdown 代码块
        raw = raw.strip()
        # 去掉 ```json ... ``` 包裹
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        # 提取 JSON 对象（从第一个 { 到最后一个 }）
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("未能在 AI 返回中提取到 JSON")
        raw = raw[start:end]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"AI 返回的 JSON 解析失败：{e}。原始返回：{raw[:300]}")

        result = {}
        for key, val in data.items():
            if key in field_names and val is not None:
                result[key] = str(val).strip()
        return result
