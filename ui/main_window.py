"""
主窗口：支持奇门遁甲和梅花易数，流式AI分析，对话式追问，并排显示
"""
import sys
import time
from PySide6.QtWidgets import (QMainWindow, QLabel, QMenuBar, QStatusBar,
                               QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
                               QApplication, QSplitter, QTextEdit, QMessageBox,
                               QScrollArea, QLineEdit, QFrame, QTextBrowser,
                               QSizePolicy)
from PySide6.QtGui import (QAction, QTextCursor, QFont, QColor, QTextDocument,
                           QTextCharFormat)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from datetime import datetime

# 奇门遁甲
from core.qimen.paipan import pai_pan
from .qimen_view import QimenView

# 梅花易数
from core.meihua.qigua import qigua_by_number, qigua_by_time, qigua_by_characters
from core.meihua.paipan import build_full_gua
from .meihua_view import MeihuaView

# 塔罗牌
from core.tarot.draw import draw_three_cards
from .tarot_view import TarotView

# LLM
from core.llm.analyzer import (
    analyze_qimen_stream, analyze_meihua_stream, analyze_tarot_stream,
    load_config
)

from .input_dialog import InputDialog
from .api_settings_dialog import ApiSettingsDialog


# ---------- 工作线程 ----------
class QimenWorker(QThread):
    # 注意：不可命名为 finished —— 会覆盖 QThread 内置 finished 信号，
    # 导致 run() 返回时再触发一次回调（重复执行）。
    pan_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, dt, matter, location):
        super().__init__()
        self.dt = dt
        self.matter = matter
        self.location = location

    def run(self):
        try:
            result = pai_pan(self.dt, self.matter, self.location)
            self.pan_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class TarotWorker(QThread):
    """塔罗牌抽卡工作线程"""
    # 注意：不可命名为 finished —— 会覆盖 QThread 内置 finished 信号，
    # 导致 run() 返回时再触发一次回调（重复执行）。
    draw_ready = Signal(list)
    error = Signal(str)
    def run(self):
        try:
            drawn = draw_three_cards()
            self.draw_ready.emit(drawn)
        except Exception as e:
            self.error.emit(str(e))


class AnalysisWorker(QThread):
    """支持对话历史的流式分析线程"""
    text_chunk = Signal(str)
    # 同上：避开 QThread 内置 finished，否则完成回调会被触发两次
    stream_done = Signal()
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
            elif self.method == 'tarot':
                generator = analyze_tarot_stream(
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
            self.stream_done.emit()
        except Exception as e:
            self.error.emit(str(e))


# ---------- Markdown 渲染控件 ----------
# 深色主题下的聊天字体与配色
CHAT_FONT_FAMILY = "Microsoft YaHei"
CHAT_TEXT_COLOR = "#e8e8e8"      # 正文
CHAT_HEAD_COLOR = "#7fd1ff"      # 小标题
CHAT_BOLD_COLOR = "#ffd479"      # 加粗重点
CHAT_TABLE_BORDER = "#666"

# 表格/引用等元素样式（须在 setHtml 之前设置才生效）
MD_CSS = f"""
td, th {{ border: 1px solid {CHAT_TABLE_BORDER}; padding: 3px 8px; }}
th {{ background-color: #2f3a44; }}
blockquote {{ color: #a9b4c0; margin-left: 8px; }}
code {{ background-color: #2a2a2a; color: #ffb86c; }}
a {{ color: #64b5f6; }}
"""


def _style_markdown_document(doc: QTextDocument):
    """
    按 Markdown 结构给文档着色，形成”有重点“的排版：
      - 标题块（##）：蓝色 + 加粗 + 更大字号，段前后留白
      - 行内加粗（**重点**）：金色
      - 正文：统一浅灰，行高 150% 提升可读性
    仅修改字符颜色/字号，不影响文本本身，选择与复制不受影响。
    """
    blk = doc.begin()
    while blk.isValid():
        bf = blk.blockFormat()
        heading_level = bf.headingLevel() if hasattr(bf, "headingLevel") else 0

        # 段落间距与行高（提升“通顺、不拥挤”的观感）
        new_bf = bf.__class__(bf)
        if heading_level > 0:
            new_bf.setTopMargin(8 if blk.position() else 2)
            new_bf.setBottomMargin(4)
        else:
            new_bf.setTopMargin(1)
            new_bf.setBottomMargin(1)
        try:
            new_bf.setLineHeight(140, new_bf.LineHeightTypes.ProportionalHeight)
        except Exception:
            pass

        cursor = QTextCursor(doc)
        cursor.setPosition(blk.position())
        cursor.setBlockFormat(new_bf)

        it = blk.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.length() > 0:
                cf = frag.charFormat()
                new_cf = QTextCharFormat(cf)
                if heading_level > 0:
                    new_cf.setForeground(QColor(CHAT_HEAD_COLOR))
                    new_cf.setFontWeight(QFont.Bold)
                    new_cf.setFontPointSize(12.5)
                    new_cf.setFontFamily(CHAT_FONT_FAMILY)
                elif cf.fontWeight() >= 600:
                    # 行内加粗 → 金色重点
                    new_cf.setForeground(QColor(CHAT_BOLD_COLOR))
                    new_cf.setFontFamily(CHAT_FONT_FAMILY)
                else:
                    new_cf.setForeground(QColor(CHAT_TEXT_COLOR))
                    new_cf.setFontFamily(CHAT_FONT_FAMILY)

                frag_cursor = QTextCursor(doc)
                frag_cursor.setPosition(frag.position())
                frag_cursor.setPosition(frag.position() + frag.length(),
                                        QTextCursor.KeepAnchor)
                frag_cursor.setCharFormat(new_cf)
            it += 1
        blk = blk.next()


class MarkdownView(QTextBrowser):
    """
    单条聊天消息控件：支持 Markdown（标题/列表/表格/代码）+ 鼠标选择复制。
    高度随内容自适应，滚动交给外层聊天区（避免内层滚动条抢滚轮）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setOpenExternalLinks(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"QTextBrowser {{ background: transparent; color: {CHAT_TEXT_COLOR};"
            f" font-family: '{CHAT_FONT_FAMILY}'; font-size: 11px; }}")
        self.document().setDocumentMargin(2)
        self.document().setDefaultStyleSheet(MD_CSS)

    # --- 内容 ---
    def set_markdown(self, text: str):
        """
        渲染 Markdown 文本（标题/加粗/表格等）。

        性能要点：着色在**离屏文档**上完成，最后一次性交给控件。
        若直接对活控件逐片段 setCharFormat，每次都会触发重排版，
        长文本下单帧可达 400ms；此写法仅需约 40ms。
        """
        src = QTextDocument()
        src.setMarkdown(text or "", QTextDocument.MarkdownDialectGitHub)
        _style_markdown_document(src)
        self.document().setHtml(src.toHtml())
        self._sync_height()

    def set_error_text(self, text: str):
        """错误信息按纯文本显示，避免误解析 Markdown"""
        self.document().setDefaultStyleSheet(MD_CSS)
        self.setPlainText(text)
        self._sync_height()

    # --- 高度自适应 ---
    def _sync_height(self):
        doc = self.document()
        doc.setTextWidth(max(self.viewport().width(), 40))
        h = int(doc.size().height()) + 2 * int(doc.documentMargin()) + 2
        if abs(self.height() - h) > 1:
            self.setFixedHeight(max(h, 22))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_height()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_height()

    def wheelEvent(self, event):
        # 滚轮交给外层聊天区滚动，避免内层吞掉滚轮
        event.ignore()


# ---------- 聊天面板 ----------
class ChatPanel(QWidget):
    """右侧聊天面板：历史记录 + 追问输入"""

    # 信号必须在类级别声明
    send_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 注意：不要用 self.layout 作属性名，会遮蔽 QWidget.layout() 方法
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(6, 6, 6, 6)
        self.vbox.setSpacing(6)
        self._locked = False

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
        # setWidget 只接受 QWidget（不能传 QLayout）
        scroll.setWidget(self.chat_history_widget)
        self.scroll = scroll
        self.vbox.addWidget(scroll, stretch=1)

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

        self.vbox.addWidget(input_frame)

        # 绑定信号（send_requested 已在类级别声明）
        self.question_input.textChanged.connect(self._on_text_changed)

    def _on_send(self):
        # AI 回复期间锁定：仅禁用按钮不够，回车同样要拦截，
        # 否则会并发启动多个分析线程，输出互相混入
        if self._locked:
            return
        text = self.question_input.text().strip()
        if not text:
            return
        self.question_input.clear()
        self.send_requested.emit(text)

    def _on_text_changed(self, text):
        """有文字时启用发送按钮（AI 回复期间保持锁定）"""
        if self._locked:
            return
        self.send_btn.setEnabled(bool(text.strip()))

    def append_message(self, role: str, content: str):
        """添加一条消息到聊天记录（AI 消息按 Markdown 渲染）"""
        if role == "user":
            label = QLabel(f"<b style='color:#90caf9;'>你：</b>"
                           f"<span style='color:#e8e8e8;'>{content}</span>")
            label.setWordWrap(True)
            label.setTextFormat(Qt.RichText)
            # 允许鼠标选择并复制
            label.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            label.setStyleSheet("font-size: 11px; padding: 4px;")
            self.chat_layout.addWidget(label)
        else:
            view = MarkdownView(self)
            view.set_markdown(content)
            self.chat_layout.addWidget(view)
        self.scroll_to_bottom()

    # --- 流式消息 ---
    def begin_stream_message(self) -> MarkdownView:
        """为即将流式输出的 AI 回复创建消息控件"""
        view = MarkdownView(self)
        self.chat_layout.addWidget(view)
        self.scroll_to_bottom()
        return view

    def update_stream_message(self, view: MarkdownView, text: str):
        """用累积文本刷新流式消息（Markdown 实时渲染）"""
        if view is None:
            return
        view.set_markdown(text)
        self.scroll_to_bottom()

    def scroll_to_bottom(self):
        """滚动聊天记录到底部"""
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_history(self):
        """清空聊天记录"""
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def set_send_enabled(self, enabled: bool):
        """锁定/解锁发送（AI 回复期间锁定输入）"""
        self._locked = not enabled
        if enabled:
            self.send_btn.setEnabled(bool(self.question_input.text().strip()))
        else:
            self.send_btn.setEnabled(False)


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

        tarot_menu = menubar.addMenu("塔罗牌")
        self.tarot_action = QAction("开始抽牌...", self)
        tarot_menu.addAction(self.tarot_action)
        self.tarot_action.triggered.connect(self.on_tarot_start)

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

        subtitle = QLabel("奇门遁甲 · 梅花易数 · 塔罗牌 · AI 智能解盘")
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

        btn_tarot = QPushButton("🔮 塔罗牌")
        btn_tarot.setFixedSize(200, 60)
        btn_tarot.setFont(QFont("SimHei", 14))
        btn_tarot.clicked.connect(self.on_tarot_start)
        welcome_layout.addWidget(btn_tarot, alignment=Qt.AlignCenter)

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

        # 流式输出的匀速刷新定时器
        self._ai_buffer = ""
        self._ai_view = None
        self._stream_dirty = False
        self._last_render = 0.0
        self._stream_timer = QTimer(self)
        self._stream_timer.setInterval(120)
        self._stream_timer.timeout.connect(self._on_stream_tick)

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
        self.worker.pan_ready.connect(self.on_pan_finished)
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

    # ---------- 塔罗牌 ----------
    def on_tarot_start(self):
        self.welcome_widget.setVisible(False)
        fields = [
            {'name': 'question', 'label': '所问事项', 'type': 'text', 'default': ''},
            {'name': 'background', 'label': '背景信息（可选）', 'type': 'text', 'default': ''},
        ]
        dialog = InputDialog("塔罗牌抽牌", fields, self, method='tarot')
        if dialog.exec() != InputDialog.DialogCode.Accepted:
            self.welcome_widget.setVisible(True)
            return
        values = dialog.get_values()
        self.current_matter = values.get('question', '')
        self.current_location = values.get('background', '')
        self.current_method = 'tarot'
        # 重置对话历史
        self.chat_history = []

        self.qimen_action.setEnabled(False)
        self.meihua_action.setEnabled(False)
        self.tarot_action.setEnabled(False)
        self.status_bar.showMessage("正在洗牌抽卡，请稍候...")

        self.worker = TarotWorker()
        self.worker.draw_ready.connect(self.on_tarot_finished)
        self.worker.error.connect(self.on_pan_error)
        # 用 singleShot 确保 welcome_widget 的 setVisible(False) 先完成再启动 worker，
        # 避免布局在过渡状态下计算错误
        QTimer.singleShot(0, self.worker.start)

    def on_tarot_finished(self, result):
        """塔罗牌抽卡完成（result 为 draw_three_cards 返回列表）"""
        self.worker = None
        self.qimen_action.setEnabled(True)
        self.meihua_action.setEnabled(True)
        self.tarot_action.setEnabled(True)
        self.current_result = result
        self.status_bar.showMessage("抽牌完成，显示牌阵...")
        self.on_pan_finished(result)

    # ---------- 显示结果 ----------
    def on_pan_finished(self, result):
        self.worker = None
        self.qimen_action.setEnabled(True)
        self.meihua_action.setEnabled(True)
        self.tarot_action.setEnabled(True)
        self.current_result = result
        self.status_bar.showMessage("排盘/起卦完成")

        try:
            self._build_result_view(result)
        except Exception:
            # 兜底：任何渲染异常都要显式提示，避免出现"状态栏完成但页面空白"
            import traceback
            detail = traceback.format_exc()
            self.status_bar.showMessage("结果渲染失败")
            QMessageBox.critical(
                self, "结果渲染失败",
                "排盘/起卦已完成，但界面渲染时出错：\n\n"
                + detail.strip().splitlines()[-1]
                + "\n\n（详细信息已输出到控制台）"
            )
            print(detail)
            self._show_welcome()

    def _build_result_view(self, result):
        """构建结果区：左侧盘面/卦象 + 右侧聊天面板"""
        self._clear_central_layout()

        self.splitter = QSplitter(Qt.Horizontal)

        if self.current_method == 'qimen':
            self.result_view = QimenView(result, self)
        elif self.current_method == 'meihua':
            self.result_view = MeihuaView(result, self)
        else:  # tarot
            self.result_view = TarotView(result, self)
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
        self.tarot_action.setEnabled(True)
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
        self._begin_stream_state()

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
        self.analysis_worker.stream_done.connect(self._on_analysis_finished)
        self.analysis_worker.error.connect(self._on_analysis_error)
        self._start_thinking()
        self.analysis_worker.start()

    # ---------- 追问 ----------
    def on_followup(self, question: str):
        if self.current_result is None:
            return
        # 防并发：上一轮分析未结束时不接受新追问（避免 worker 被覆盖、输出混入）
        if self.analysis_worker is not None:
            self.status_bar.showMessage("上一轮分析尚未结束，请稍候…")
            return
        config = load_config()
        if not config.get("api_key"):
            self.status_bar.showMessage("请先设置 API Key")
            return

        # 将用户追问追加到聊天历史
        self.chat_history.append({"role": "user", "content": question})
        self.chat_panel.append_message("user", question)
        self.chat_panel.set_send_enabled(False)
        self._begin_stream_state()

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
        self.analysis_worker.stream_done.connect(self._on_analysis_finished)
        self.analysis_worker.error.connect(self._on_analysis_error)
        self._start_thinking()
        self.analysis_worker.start()

    # ---------- AI 回答流式追加 ----------
    def _reset_stream_state(self):
        """清空流式状态并停止刷新定时器"""
        self._ai_buffer = ""
        self._ai_view = None
        self._stream_dirty = False
        self._last_render = 0.0
        self._stream_timer.stop()

    def _begin_stream_state(self):
        """开始新的 AI 请求：清空状态并启动匀速刷新"""
        self._reset_stream_state()
        self._stream_timer.start()

    def _ensure_stream_view(self):
        """首个 chunk 到达：结束思考提示并创建流式消息控件"""
        if self._thinking_active:
            self._stop_thinking()
        if self._ai_view is None and self.chat_panel is not None:
            self._ai_view = self.chat_panel.begin_stream_message()
        return self._ai_view

    def _append_ai_chunk(self, text: str):
        """流式回调：累积文本，由 _stream_timer 匀速刷新界面"""
        if not text or self.chat_panel is None:
            return
        self._ensure_stream_view()
        self._ai_buffer += text
        self._stream_dirty = True

    def _on_stream_tick(self):
        """定时刷新流式消息（内容越长间隔越大，避免长回答拖慢界面）"""
        if not self._stream_dirty:
            return
        n = len(self._ai_buffer)
        if n < 1200:
            interval = 0.12
        elif n < 3000:
            interval = 0.20
        else:
            interval = 0.30
        if time.monotonic() - self._last_render < interval:
            return
        self._render_ai_stream()

    def _render_ai_stream(self):
        """把当前缓冲区渲染到流式消息控件"""
        if self._ai_view is None or self.chat_panel is None:
            self._stream_dirty = False
            return
        self.chat_panel.update_stream_message(self._ai_view, self._ai_buffer)
        self._stream_dirty = False
        self._last_render = time.monotonic()

    def _on_analysis_finished(self):
        # 防重入：同一请求的完成回调只处理一次
        if self.analysis_worker is None:
            return
        self._stream_timer.stop()
        self._render_ai_stream()          # 收尾渲染，确保内容完整
        self._stop_thinking()

        answer = self._ai_buffer
        if answer:
            self.chat_history.append({"role": "assistant", "content": answer})
        elif self._ai_view is None:
            # 全程没有任何正文：给出明确提示，而不是静默空白
            if self.chat_panel is not None:
                self.chat_panel.append_message(
                    "assistant",
                    "（未收到模型正文输出。请检查「设置 → LLM API 设置」中的 "
                    "max_tokens 是否过小，或更换模型后重试。）")
        self._reset_stream_state()
        self.status_bar.showMessage("分析完成")
        self.analyze_button.setEnabled(True)
        if self.chat_panel:
            self.chat_panel.set_send_enabled(True)
        self.analysis_worker = None

    def _on_analysis_error(self, err):
        if self.analysis_worker is None:
            return
        self._stream_timer.stop()
        self._stop_thinking()
        self.status_bar.showMessage(f"分析错误: {err}")
        # 若已有部分流式内容，保留它并提示错误；否则新建一条错误消息
        if self._ai_view is not None and self._ai_buffer:
            if self.chat_panel is not None:
                self.chat_panel.update_stream_message(
                    self._ai_view, self._ai_buffer + f"\n\n> ⚠️ 输出中断：{err}")
        elif self.chat_panel is not None:
            view = self.chat_panel.begin_stream_message()
            view.set_error_text(f"[错误] {err}")
        self._reset_stream_state()
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
        # 立即移出布局再销毁，避免延迟删除期间残留导致消息计数错乱
        label = getattr(self, '_thinking_label', None)
        if label is not None:
            if self.chat_panel is not None:
                self.chat_panel.chat_layout.removeWidget(label)
            label.setParent(None)
            label.deleteLater()
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
        self._stream_timer.stop()
        self.chat_history = []
        self._ai_buffer = ""
        self._ai_view = None
        self._stream_dirty = False
        self.current_result = None
        self.current_matter = ""
        self.current_location = ""
        # 清除主区域（保留 welcome_widget 和 bottom_btn_layout）
        self._clear_central_layout()
        self.welcome_widget.setVisible(True)
        self.analyze_button.setVisible(False)
        self.return_btn.setVisible(False)
        self.status_bar.showMessage("就绪")

    # ---------- 辅助 ----------
    def open_llm_settings(self):
        dlg = ApiSettingsDialog(self)
        dlg.exec()

    def _clear_central_layout(self):
        """清除主布局中的内容区域（保留 welcome_widget 和 bottom_btn_layout）"""
        # 从后向前遍历，移除所有 widget 和 layout（除了底栏）
        for i in range(self.main_layout.count() - 1, -1, -1):
            item = self.main_layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            # 保留欢迎页和底部按钮布局
            if w == self.welcome_widget or w == self.bottom_btn_layout:
                continue
            # 保留底部按钮布局（即使作为嵌套 layout 出现）
            if item.layout() is self.bottom_btn_layout:
                continue
            # 移除并删除 widget
            if w is not None:
                self.main_layout.takeAt(i)
                w.deleteLater()
            else:
                # layout 项（如 splitter 的嵌套 layout）
                self.main_layout.takeAt(i)
        self.splitter = None
        self.result_view = None
        self.chat_panel = None
        self._ai_buffer = ""
        self._ai_view = None
        self._stream_dirty = False
        self._thinking_label = None
