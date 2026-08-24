"""
ui/api_settings_dialog.py - LLM API 设置对话框
"""
import json
import os
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                               QSpinBox, QDoubleSpinBox, QDialogButtonBox,
                               QVBoxLayout, QLabel, QMessageBox)

class ApiSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM API 设置")
        self.resize(450, 300)

        self.config_path = "config/llm_config.json"
        self.current_config = self.load_config()

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.api_key_edit = QLineEdit(self.current_config.get("api_key", ""))
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow("API Key:", self.api_key_edit)

        self.base_url_edit = QLineEdit(self.current_config.get("base_url", "https://api.deepseek.com/v1"))
        form.addRow("Base URL:", self.base_url_edit)

        self.model_edit = QLineEdit(self.current_config.get("model", "deepseek-v4-flash"))
        form.addRow("Model:", self.model_edit)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(100, 16000)
        self.max_tokens_spin.setValue(self.current_config.get("max_tokens", 4000))
        form.addRow("Max Tokens:", self.max_tokens_spin)

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(self.current_config.get("temperature", 0.7))
        form.addRow("Temperature:", self.temperature_spin)

        layout.addLayout(form)

        hint = QLabel("默认 Base URL 为 DeepSeek 官方地址，使用其他兼容服务时修改。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_config)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def load_config(self) -> dict:
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return {
                "api_key": "",
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-v4-flash",
                "max_tokens": 4000,
                "temperature": 0.7
            }

    def save_config(self):
        new_config = {
            "api_key": self.api_key_edit.text().strip(),
            "base_url": self.base_url_edit.text().strip(),
            "model": self.model_edit.text().strip(),
            "max_tokens": self.max_tokens_spin.value(),
            "temperature": self.temperature_spin.value()
        }
        # 确保目录存在
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "保存成功", "API 设置已保存，下次分析时生效。")
        self.accept()