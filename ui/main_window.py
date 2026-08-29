"""
主窗口：支持奇门遁甲和梅花易数，流式AI分析，并排显示
增加美观欢迎界面，隐藏菜单栏
"""
import sys
from PySide6.QtWidgets import (QMainWindow, QLabel, QMenuBar, QStatusBar,
                               QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
                               QApplication, QSplitter, QTextEdit, QMessageBox)
from PySide6.QtGui import QAction, QTextCursor, QFont
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
    text_chunk = Signal(str)
    finished = Signal()
    error = Signal(str)
    def __init__(self, method, data, matter, location, api_key, base_url, model):
        super().__init__()
        self.method = method          # 'qimen' or 'meihua'
        self.data = data
        self.matter = matter
        self.location = location
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    def run(self):
        try:
            # 流式接口逐块输出（关闭深思考后可正常返回正文）
            if self.method == 'qimen':
                generator = analyze_qimen_stream(
                    self.data, self.matter, self.location,
                    self.api_key, self.base_url, self.model
                )
            else:  # meihua
                generator = analyze_meihua_stream(
                    self.data, self.matter, self.location,
                    self.api_key, self.base_url, self.model
                )
            for chunk in generator:
                self.text_chunk.emit(chunk)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("玄学工具箱")
        self.resize(1100, 750)

        self.current_method = None          # 'qimen' or 'meihua'
        self.current_result = None
        self.current_matter = ""
        self.current_location = ""

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

        # 隐藏菜单栏
        menubar.setVisible(False)

        # 状态栏
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪")

        # 中央部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(5, 5, 5, 5)

        # ---- 欢迎界面 ----
        self.welcome_widget = QWidget()
        welcome_layout = QVBoxLayout(self.welcome_widget)
        welcome_layout.setAlignment(Qt.AlignCenter)
        welcome_layout.setSpacing(20)

        # 标题
        title_label = QLabel("欢迎使用 Evander 的神秘学工具箱")
        title_font = QFont("SimHei", 20, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        welcome_layout.addWidget(title_label)

        # 副标题/说明
        subtitle = QLabel("奇门遁甲 · 梅花易数 · AI 智能解盘")
        sub_font = QFont("SimHei", 12)
        subtitle.setFont(sub_font)
        subtitle.setAlignment(Qt.AlignCenter)
        welcome_layout.addWidget(subtitle)

        welcome_layout.addSpacing(20)

        # 三个大按钮
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

        # 分析按钮（初始隐藏）
        self.analyze_button = QPushButton("🧠 智能分析")
        self.analyze_button.setVisible(False)
        self.analyze_button.clicked.connect(self.on_analyze)
        self.main_layout.addWidget(self.analyze_button)

        # 工作线程引用
        self.worker = None
        self.analysis_worker = None
        self.splitter = None
        self.result_view = None
        self.analysis_text_edit = None

        # AI 思考状态指示（动态省略号）
        self._thinking_active = False
        self._thinking_ticks = 0
        self.thinking_timer = QTimer(self)
        self.thinking_timer.setInterval(400)
        self.thinking_timer.timeout.connect(self._on_thinking_tick)

    # ---------- 奇门遁甲 ----------
    def on_qimen_start(self):
        # 隐藏欢迎界面
        self.welcome_widget.setVisible(False)

        fields = [
            {'name': 'matter', 'label': '预测事项', 'type': 'text', 'default': ''},
            {'name': 'location', 'label': '当前位置', 'type': 'text', 'default': ''},
        ]
        dialog = InputDialog("奇门遁甲排盘", fields, self)
        if dialog.exec() != InputDialog.DialogCode.Accepted:
            self.welcome_widget.setVisible(True)
            return
        values = dialog.get_values()
        self.current_matter = values.get('matter', '')
        self.current_location = values.get('location', '')
        self.current_method = 'qimen'

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
            {'name': 'method', 'label': '起卦方式', 'type': 'select', 'default': '数字起卦', 'options': ['数字起卦', '时间起卦', '汉字起卦']},
            {'name': 'num1', 'label': '第一个数字', 'type': 'text', 'default': '', 'visible_if': {'field': 'method', 'value': '数字起卦'}},
            {'name': 'num2', 'label': '第二个数字', 'type': 'text', 'default': '', 'visible_if': {'field': 'method', 'value': '数字起卦'}},
            {'name': 'num3', 'label': '第三个数字', 'type': 'text', 'default': '', 'visible_if': {'field': 'method', 'value': '数字起卦'}},
            {'name': 'char_text', 'label': '输入汉字', 'type': 'text', 'default': '', 'visible_if': {'field': 'method', 'value': '汉字起卦'}},
            {'name': 'char_mode', 'label': '起卦方式', 'type': 'select', 'default': '笔画数法', 'options': ['笔画数法', '字数法'], 'visible_if': {'field': 'method', 'value': '汉字起卦'}},
            {'name': 'question', 'label': '所问事项', 'type': 'text', 'default': ''},
            {'name': 'background', 'label': '背景信息（可选）', 'type': 'text', 'default': ''},
        ]
        dialog = InputDialog("梅花易数起卦", fields, self)
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

        self.current_result = build_full_gua(upper, lower, moving, dt=datetime.now())
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

        self.splitter = QSplitter(Qt.Horizontal)

        if self.current_method == 'qimen':
            self.result_view = QimenView(result, self)
        else:
            self.result_view = MeihuaView(result, self)
        self.splitter.addWidget(self.result_view)

        self.analysis_text_edit = QTextEdit()
        self.analysis_text_edit.setReadOnly(True)
        self.analysis_text_edit.setPlaceholderText("点击「智能分析」按钮，AI 解读将实时显示于此...")
        self.analysis_text_edit.setFontPointSize(11)
        self.splitter.addWidget(self.analysis_text_edit)

        self.splitter.setSizes([550, 450])
        self.main_layout.addWidget(self.splitter)
        self.analyze_button.setVisible(True)

    def on_pan_error(self, error_msg):
        self.worker = None
        self.qimen_action.setEnabled(True)
        self.meihua_action.setEnabled(True)
        self.status_bar.showMessage(f"排盘失败: {error_msg}")
        self.welcome_widget.setVisible(True)

    # ---------- AI 分析 ----------
    def on_analyze(self):
        if self.current_result is None or self.analysis_text_edit is None:
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

        self.analysis_text_edit.clear()
        self.analysis_text_edit.setPlaceholderText("")
        self.status_bar.showMessage("正在请求 AI 分析（流式输出）...")
        self.analyze_button.setEnabled(False)

        self.analysis_worker = AnalysisWorker(
            self.current_method,
            self.current_result,
            self.current_matter,
            self.current_location,
            config.get("api_key"),
            config.get("base_url"),
            config.get("model")
        )
        self.analysis_worker.text_chunk.connect(self.append_analysis_text)
        self.analysis_worker.finished.connect(self.on_analysis_finished)
        self.analysis_worker.error.connect(self.on_analysis_error)
        self._start_thinking()
        self.analysis_worker.start()

    # ---------- 思考状态指示 ----------
    def _start_thinking(self):
        self._thinking_active = True
        self._thinking_ticks = 0
        if self.analysis_text_edit:
            self.analysis_text_edit.setPlainText("正在思考分析中")
        self.thinking_timer.start()

    def _stop_thinking(self):
        self._thinking_active = False
        self._thinking_ticks = 0
        self.thinking_timer.stop()

    def _on_thinking_tick(self):
        if not self._thinking_active or not self.analysis_text_edit:
            return
        self._thinking_ticks += 1
        dots = "." * ((self._thinking_ticks - 1) % 3 + 1)
        self.analysis_text_edit.setPlainText(f"正在思考分析中{dots}")

    def append_analysis_text(self, text):
        # 思考结束、开始输出正文时，清掉“正在思考”占位
        if self._thinking_active:
            self._stop_thinking()
            self.analysis_text_edit.clear()
        if self.analysis_text_edit:
            self.analysis_text_edit.moveCursor(QTextCursor.MoveOperation.End)
            self.analysis_text_edit.insertPlainText(text)
            self.analysis_text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def on_analysis_finished(self):
        self._stop_thinking()
        self.status_bar.showMessage("分析完成")
        self.analyze_button.setEnabled(True)
        self.analysis_worker = None

    def on_analysis_error(self, err):
        self._stop_thinking()
        self.status_bar.showMessage(f"分析错误: {err}")
        self.analysis_text_edit.append(f"\n[错误] {err}")
        self.analyze_button.setEnabled(True)
        self.analysis_worker = None

    # ---------- 辅助 ----------
    def open_llm_settings(self):
        dlg = ApiSettingsDialog(self)
        dlg.exec()

    def _clear_central_layout(self):
        for i in reversed(range(self.main_layout.count())):
            item = self.main_layout.itemAt(i)
            widget = item.widget()
            if widget and widget is not self.analyze_button:
                widget.deleteLater()
        self.splitter = None
        self.result_view = None
        self.analysis_text_edit = None