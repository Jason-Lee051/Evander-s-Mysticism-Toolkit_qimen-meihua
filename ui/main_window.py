"""
主窗口：支持奇门遁甲和梅花易数，流式AI分析，对话式追问，并排显示
"""
import sys
from PySide6.QtWidgets import (QMainWindow, QLabel, QMenuBar, QStatusBar,
                               QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
                               QApplication, QSplitter, QTextEdit, QMessageBox,
                               QScrollArea, QLineEdit, QFrame)
from PySide6.QtGui import QAction, QTextCursor, QFont, QColor
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from datetime import datetime

# 奇门遁甲
from core.qimen.paipan import pai_pan
from .qimen_view import QimenView

# 梅花易数
from core.meihua.qigua import qigua_by_number, qigua_by_time, qigua_by_characters
from core.meihua.paipan import build_full_gua
from .meihua_view import MeihuaView

# LLM
from core.llm.analyzer import (
    analyze_qimen_stream, analyze_meihua_stream,
    load_config
)

from .input_dialog import InputDialog
from .api_settings_dialog import ApiSettingsDialog


# ---------- 工作线程 ----------
class QimenWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)
    def __init__(self, dt, matter, location):
        super().__init__()
        self.dt = dt
        self.matter = matter
        self.location = location
    def run(self):
        try:
            result = pai_pan(self.dt, self.matter, self.location)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class AnalysisWorker(QThread):
    """支持对话历史的流式分析线程"""
    text_chunk = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, method, data, matter, location, api_key, base_url, model,
                 chat_history=None, is_followup=False):
        super().__init__()
        self.method = method
        self.data = data
        self.matter = matter
        self.location = location
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        # chat_history: list of {"role":"user"/"assistant", "content":str}
        self.chat_history = chat_history or []
        self.is_followup = is_followup   # True = 追问，False = 首次分析

    def run(self):
        try:
            if self.method == 'qimen':
                generator = analyze_qimen_stream(
                    self.data, self.matter, self.location,
                    self.api_key, self.base_url, self.model,
                    chat_history=self.chat_history,
                    is_followup=self.is_followup
                )
            else:
                generator = analyze_meihua_stream(
                    self.data, self.matter, self.location,
                    self.api_key, self.base_url, self.model,
                    chat_history=self.chat_history,
                    is_followup=self.is_followup
                )
            for chunk in generator:
                self.text_chunk.emit(chunk)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ---------- 聊天面板 ----------
class ChatPanel(QWidget):
    """右侧聊天面板：历史记录 + 追问输入"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(6)

        # ---- 聊天记录区 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #333; background: #1a1a1a; border-radius: 4px; }")

        self.chat_history_widget = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_history_widget)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setContentsMargins(6, 6, 6, 6)
        self.chat_layout.setSpacing(8)
        scroll.setWidget(self.chat_layout)
        self.layout.addWidget(scroll, stretch=1)

        # ---- 输入区 ----
        input_frame = QFrame()
        input_frame.setStyleSheet("QFrame { background: #2a2a2a; border-radius: 4px; }")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(6, 6, 6, 6)
        input_layout.setSpacing(4)

        hint = QLabel("输入追问，按 Enter 发送，Shift+Enter 换行")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        input_layout.addWidget(hint)

        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("在这里输入你的追问...")
        self.question_input.setMinimumHeight(36)
        self.question_input.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.question_input)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setStyleSheet(
            "QPushButton { background: #2e7d32; color: white; "
            "border: none; border-radius: 3px; padding: 4px 16px; font-weight: bold; }"
            "QPushButton:pressed { background: #1b5e20; }"
            "QPushButton:disabled { background: #555; }"
        )
        btn_row.addWidget(self.send_btn)
        btn_row.addStretch()
        input_layout.addLayout(btn_row)

        self.layout.addWidget(input_frame)

        # 绑定信号
        self.send_requested = Signal(str)
        self.send_btn.clicked.connect(lambda: self._on_send())
        self.question_input.textChanged.connect(self._on_text_changed)

    def _on_send(self):
        text = self.question_input.text().strip()
        if not text:
            return
        self.question_input.clear()
        self.send_requested.emit(text)

    def _on_text_changed(self, text):
        """有文字时启用发送按钮"""
        self.send_btn.setEnabled(bool(text.strip()))

    def append_message(self, role: str, content: str):
        """添加一条消息到聊天记录"""
        label = QLabel()
        if role == "user":
            label.setText(f"<b style='color:#90caf9;'>你：</b>{content}")
        else:
            label.setText(f"<b style='color:#81c784;'>AI：</b>{content}")
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setStyleSheet("color: #eee; font-size: 11px; padding: 4px;")
        label.setMinimumHeight(20)
        self.chat_layout.addWidget(label)
        # 自动滚动到底部
        scroll = self.parent().findChild(QScrollArea)
        if scroll:
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())

    def clear_history(self):
        """清空聊天记录（保留占位）"""
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def set_send_enabled(self, enabled: bool):
        self.send_btn.setEnabled(enabled and bool(self.question_input.text().strip()))


# ---------- 主窗口 ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("玄学工具箱")
        self.resize(1100, 750)

        self.current_method = None          # 'qimen' or 'meihua'
        self.current_result = None
        self.current_matter = ""
        self.current_location = ""
        self.chat_history = []              # [{"role":..., "content":...}]

        # 菜单栏（隐藏，因为欢迎界面已有按钮）
        menubar = self.menuBar()
        qimen_menu = menubar.addMenu("奇门遁甲")
        self.qimen_action = QAction("开始排盘...", self)
        qimen_menu.addAction(self.qimen_action)
        self.qimen_action.triggered.connect(self.on_qimen_start)

        meihua_menu = menubar.addMenu("梅花易数")
        self.meihua_action = QAction("开始起卦...", self)
        meihua_menu.addAction(self.meihua_action)
        self.meihua_action.triggered.connect(self.on_meihua_start)

        settings_menu = menubar.addMenu("设置")
        self.llm_settings_action = QAction("LLM API 设置...", self)
        settings_menu.addAction(self.llm_settings_action)
        self.llm_settings_action.triggered.connect(self.open_llm_settings)

        menubar.setVisible(False)

        # 状态栏
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪")

        # 中央部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(4)

        # ---- 欢迎界面 ----
        self.welcome_widget = QWidget()
        welcome_layout = QVBoxLayout(self.welcome_widget)
        welcome_layout.setAlignment(Qt.AlignCenter)
        welcome_layout.setSpacing(20)

        title_label = QLabel("欢迎使用 Evander 的神秘学工具箱")
        title_font = QFont("SimHei", 20, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        welcome_layout.addWidget(title_label)

        subtitle = QLabel("奇门遁甲 · 梅花易数 · AI 智能解盘")
        sub_font = QFont("SimHei", 12)
        subtitle.setFont(sub_font)
        subtitle.setAlignment(Qt.AlignCenter)
        welcome_layout.addWidget(subtitle)
        welcome_layout.addSpacing(20)

        btn_qimen = QPushButton("🔮 奇门遁甲")
        btn_qimen.setFixedSize(200, 60)
        btn_qimen.setFont(QFont("SimHei", 14))
        btn_qimen.clicked.connect(self.on_qimen_start)
        welcome_layout.addWidget(btn_qimen, alignment=Qt.AlignCenter)

        btn_meihua = QPushButton("☯ 梅花易数")
        btn_meihua.setFixedSize(200, 60)
        btn_meihua.setFont(QFont("SimHei", 14))
        btn_meihua.clicked.connect(self.on_meihua_start)
        welcome_layout.addWidget(btn_meihua, alignment=Qt.AlignCenter)

        btn_settings = QPushButton("⚙️ LLM 设置")
        btn_settings.setFixedSize(200, 60)
        btn_settings.setFont(QFont("SimHei", 14))
        btn_settings.clicked.connect(self.open_llm_settings)
        welcome_layout.addWidget(btn_settings, alignment=Qt.AlignCenter)

        self.main_layout.addWidget(self.welcome_widget)

        # ---- 底部按钮区（排盘后显示） ----
        self.bottom_btn_layout = QHBoxLayout()
        self.bottom_btn_layout.setContentsMargins(0, 4, 0, 4)

        self.analyze_button = QPushButton("🧠 智能分析")
        self.analyze_button.setVisible(False)
        self.analyze_button.clicked.connect(self.on_analyze)
        self.analyze_button.setStyleSheet(
            "QPushButton { background: #1565c0; color: white; "
            "border: none; border-radius: 4px; padding: 6px 20px; font-size: 13px; font-weight: bold; }"
            "QPushButton:pressed { background: #0d47a1; }"
            "QPushButton:disabled { background: #555; }"
        )
        self.bottom_btn_layout.addWidget(self.analyze_button)

        self.return_btn = QPushButton("🏠 返回主菜单")
        self.return_btn.setVisible(False)
        self.return_btn.clicked.connect(self._show_welcome)
        self.return_btn.setStyleSheet(
            "QPushButton { background: #424242; color: #ccc; "
            "border: 1px solid #666; border-radius: 4px; padding: 6px 20px; font-size: 13px; }"
            "QPushButton:pressed { background: #333; }"
        )
        self.bottom_btn_layout.addWidget(self.return_btn)
        self.bottom_btn_layout.addStretch()
        self.main_layout.addLayout(self.bottom_btn_layout)

        # 工作线程引用
        self.worker = None
        self.analysis_worker = None
        self.splitter = None
        self.result_view = None
        self.chat_panel = None

        # AI 思考状态指示
        self._thinking_active = False
        self._thinking_ticks = 0
        self.thinking_timer = QTimer(self)
        self.thinking_timer.setInterval(400)
        self.thinking_timer.timeout.connect(self._on_thinking_tick)

    # ---------- 奇门遁甲 ----------
    def on_qimen_start(self):
        self.welcome_widget.setVisible(False)
        fields = [
            {'name': 'matter', 'label': '预测事项', 'type': 'text', 'default': ''},
            {'name': 'location', 'label': '当前位置', 'type': 'text', 'default': ''},
        ]
        dialog = InputDialog("奇门遁甲排盘", fields, self, method='qimen')
        if dialog.exec() != InputDialog.DialogCode.Accepted:
            self.welcome_widget.setVisible(True)
            return
        values = dialog.get_values()
        self.current_matter = values.get('matter', '')
        self.current_location = values.get('location', '')
        self.current_method = 'qimen'
        # 重置对话历史
        self.chat_history = []

        self.qimen_action.setEnabled(False)
        self.meihua_action.setEnabled(False)
        self.status_bar.showMessage("正在计算排盘，请稍候...")

        self.worker = QimenWorker(datetime.now(), self.current_matter, self.current_location)
        self.worker.finished.connect(self.on_pan_finished)
        self.worker.error.connect(self.on_pan_error)
        self.worker.start()

    # ---------- 梅花易数 ----------
    def on_meihua_start(self):
        self.welcome_widget.setVisible(False)
        fields = [
            {'name': 'method', 'label': '起卦方式', 'type': 'select', 'default': '数字起卦',
             'options': ['数字起卦', '时间起卦', '汉字起卦']},
            {'name': 'num1', 'label': '第一个数字', 'type': 'text', 'default': '',
             'visible_if': {'field': 'method', 'value': '数字起卦'}},
            {'name': 'num2', 'label': '第二个数字', 'type': 'text', 'default': '',
             'visible_if': {'field': 'method', 'value': '数字起卦'}},
            {'name': 'num3', 'label': '第三个数字', 'type': 'text', 'default': '',
             'visible_if': {'field': 'method', 'value': '数字起卦'}},
            {'name': 'char_text', 'label': '输入汉字', 'type': 'text', 'default': '',
             'visible_if': {'field': 'method', 'value': '汉字起卦'}},
            {'name': 'char_mode', 'label': '起卦方式', 'type': 'select',
             'default': '笔画数法', 'options': ['笔画数法', '字数法'],
             'visible_if': {'field': 'method', 'value': '汉字起卦'}},
            {'name': 'question', 'label': '所问事项', 'type': 'text', 'default': ''},
            {'name': 'background', 'label': '背景信息（可选）', 'type': 'text', 'default': ''},
        ]
        dialog = InputDialog("梅花易数起卦", fields, self, method='meihua')
        if dialog.exec() != InputDialog.DialogCode.Accepted:
            self.welcome_widget.setVisible(True)
            return
        values = dialog.get_values()
        method = values.get('method', '数字起卦')
        question = values.get('question', '')
        background = values.get('background', '')
        self.current_matter = question
        self.current_location = background
        self.current_method = 'meihua'
        # 重置对话历史
        self.chat_history = []

        try:
            if method == '数字起卦':
                num1 = int(values.get('num1', 0) or 0)
                num2 = int(values.get('num2', 0) or 0)
                num3 = int(values.get('num3', 0) or 0)
                if num1 == 0 and num2 == 0 and num3 == 0:
                    QMessageBox.warning(self, "提示", "请至少输入一个非零数字")
                    self.welcome_widget.setVisible(True)
                    return
                upper, lower, moving = qigua_by_number(num1, num2, num3)
            elif method == '时间起卦':
                dt = datetime.now()
                upper, lower, moving = qigua_by_time(dt)
            else:  # 汉字起卦
                text = values.get('char_text', '')
                if not text:
                    QMessageBox.warning(self, "提示", "请输入汉字")
                    self.welcome_widget.setVisible(True)
                    return
                char_mode = values.get('char_mode', '笔画数法')
                mode = 'stroke' if char_mode == '笔画数法' else 'word'
                try:
                    upper, lower, moving = qigua_by_characters(text, mode=mode)
                except NotImplementedError as e:
                    QMessageBox.warning(self, "提示", str(e))
                    self.welcome_widget.setVisible(True)
                    return
        except Exception as e:
            QMessageBox.critical(self, "起卦错误", str(e))
            self.welcome_widget.setVisible(True)
            return

        self.current_result = build_full_gua(upper, lower, moving)
        self.current_result['question'] = question
        self.current_result['background'] = background

        self.qimen_action.setEnabled(False)
        self.meihua_action.setEnabled(False)
        self.status_bar.showMessage("起卦完成，显示卦象...")
        self.on_pan_finished(self.current_result)

    # ---------- 显示结果 ----------
    def on_pan_finished(self, result):
        self.worker = None
        self.qimen_action.setEnabled(True)
        self.meihua_action.setEnabled(True)
        self.current_result = result
        self.status_bar.showMessage("排盘/起卦完成")

        self._clear_central_layout()

        # 左侧：盘面/卦象；右侧：聊天面板
        self.splitter = QSplitter(Qt.Horizontal)

        if self.current_method == 'qimen':
            self.result_view = QimenView(result, self)
        else:
            self.result_view = MeihuaView(result, self)
        self.splitter.addWidget(self.result_view)

        self.chat_panel = ChatPanel(self)
        self.chat_panel.send_requested.connect(self.on_followup)
        self.splitter.addWidget(self.chat_panel)

        self.splitter.setSizes([550, 450])
        self.main_layout.addWidget(self.splitter)

        self.analyze_button.setVisible(True)
        self.return_btn.setVisible(True)

    def on_pan_error(self, error_msg):
        self.worker = None
        self.qimen_action.setEnabled(True)
        self.meihua_action.setEnabled(True)
        self.status_bar.showMessage(f"排盘失败: {error_msg}")
        self._show_welcome()

    # ---------- 智能分析（首次） ----------
    def on_analyze(self):
        if self.current_result is None or self.chat_panel is None:
            return

        config = load_config()
        if not config.get("api_key"):
            self.status_bar.showMessage("请先设置 API Key")
            dlg = ApiSettingsDialog(self)
            dlg.exec()
            config = load_config()
            if not config.get("api_key"):
                self.status_bar.showMessage("未配置 API Key，分析取消")
                return

        self.status_bar.showMessage("正在请求 AI 分析（流式输出）...")
        self.analyze_button.setEnabled(False)
        self.chat_panel.set_send_enabled(False)

        self.analysis_worker = AnalysisWorker(
            self.current_method,
            self.current_result,
            self.current_matter,
            self.current_location,
            config.get("api_key"),
            config.get("base_url"),
            config.get("model"),
            chat_history=self.chat_history,
            is_followup=False
        )
        self.analysis_worker.text_chunk.connect(self._append_ai_chunk)
        self.analysis_worker.finished.connect(self._on_analysis_finished)
        self.analysis_worker.error.connect(self._on_analysis_error)
        self._start_thinking()
        self.analysis_worker.start()

    # ---------- 追问 ----------
    def on_followup(self, question: str):
        if self.current_result is None:
            return
        config = load_config()
        if not config.get("api_key"):
            self.status_bar.showMessage("请先设置 API Key")
            return

        # 将用户追问追加到聊天历史
        self.chat_history.append({"role": "user", "content": question})
        self.chat_panel.append_message("user", question)
        self.chat_panel.set_send_enabled(False)

        self.status_bar.showMessage("正在请求 AI 回答追问...")
        self.analysis_worker = AnalysisWorker(
            self.current_method,
            self.current_result,
            self.current_matter,
            self.current_location,
            config.get("api_key"),
            config.get("base_url"),
            config.get("model"),
            chat_history=self.chat_history,
            is_followup=True
        )
        self.analysis_worker.text_chunk.connect(self._append_ai_chunk)
        self.analysis_worker.finished.connect(self._on_analysis_finished)
        self.analysis_worker.error.connect(self._on_analysis_error)
        self.analysis_worker.start()

    # ---------- AI 回答流式追加 ----------
    def _append_ai_chunk(self, text: str):
        if not hasattr(self, '_ai_buffer'):
            self._ai_buffer = ""
        self._ai_buffer += text
        # 实时更新显示
        if self.chat_panel:
            # 找到最后一条 AI 消息并更新
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()

    def _on_analysis_finished(self):
        self._stop_thinking()
        # 将缓冲的完整回答追加到聊天面板和历史记录
        answer = getattr(self, '_ai_buffer', '')
        if answer:
            self.chat_history.append({"role": "assistant", "content": answer})
            self.chat_panel.append_message("assistant", answer)
        self._ai_buffer = ""
        self.status_bar.showMessage("分析完成")
        self.analyze_button.setEnabled(True)
        if self.chat_panel:
            self.chat_panel.set_send_enabled(True)
        self.analysis_worker = None

    def _on_analysis_error(self, err):
        self._stop_thinking()
        self.status_bar.showMessage(f"分析错误: {err}")
        if self.chat_panel:
            self.chat_panel.append_message("assistant", f"[错误] {err}")
        self.analyze_button.setEnabled(True)
        if self.chat_panel:
            self.chat_panel.set_send_enabled(True)
        self.analysis_worker = None

    # ---------- 思考状态指示 ----------
    def _start_thinking(self):
        self._thinking_active = True
        self._thinking_ticks = 0
        if self.chat_panel:
            # 插入一条 thinking 占位消息
            self._thinking_label = QLabel("<i style='color:#aaa;'>AI 正在思考中...</i>")
            self._thinking_label.setWordWrap(True)
            self._thinking_label.setStyleSheet("color: #aaa; font-size: 11px; padding: 4px;")
            self.chat_panel.chat_layout.addWidget(self._thinking_label)
        self.thinking_timer.start()

    def _stop_thinking(self):
        self._thinking_active = False
        self._thinking_ticks = 0
        self.thinking_timer.stop()
        # 移除 thinking 占位标签
        if hasattr(self, '_thinking_label') and self._thinking_label:
            self._thinking_label.deleteLater()
            self._thinking_label = None

    def _on_thinking_tick(self):
        if not self._thinking_active or not hasattr(self, '_thinking_label') or not self._thinking_label:
            return
        self._thinking_ticks += 1
        dots = "." * ((self._thinking_ticks - 1) % 3 + 1)
        self._thinking_label.setText(f"<i style='color:#aaa;'>AI 正在思考中{dots}</i>")

    # ---------- 返回主菜单 ----------
    def _show_welcome(self):
        self._stop_thinking()
        self.chat_history = []
        self.current_result = None
        self.current_matter = ""
        self.current_location = ""
        self.welcome_widget.setVisible(True)
        self.analyze_button.setVisible(False)
        self.return_btn.setVisible(False)
        self.status_bar.showMessage("就绪")
        self._clear_central_layout()

    # ---------- 辅助 ----------
    def open_llm_settings(self):
        dlg = ApiSettingsDialog(self)
        dlg.exec()

    def _clear_central_layout(self):
        for i in reversed(range(self.main_layout.count())):
            item = self.main_layout.itemAt(i)
            widget = item.widget()
            if widget and widget not in (self.welcome_widget,):
                widget.deleteLater()
        self.splitter = None
        self.result_view = None
        self.chat_panel = None
        self._ai_buffer = ""
        self._thinking_label = None
