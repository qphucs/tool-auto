STYLESHEET = """
QWidget {
    font-family: "Segoe UI";
    font-size: 10pt;
    color: #1f2937;
}
QMainWindow, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {
    background: #f4f5f7;
}
QDialog, QMessageBox { background: #ffffff; }

QListWidget#sidebar {
    background: #1e2330;
    border: none;
    padding: 12px 8px;
    outline: 0;
}
QListWidget#sidebar::item {
    color: #c9cfdb;
    padding: 10px 14px;
    border-radius: 6px;
    margin: 2px 0;
}
QListWidget#sidebar::item:hover { background: #2a3142; }
QListWidget#sidebar::item:selected { background: #3b82f6; color: white; }
QLabel#brand {
    background: #1e2330;
    color: white;
    font-size: 14pt;
    font-weight: 600;
    padding: 18px 20px 6px 20px;
}

QLabel#pageTitle { font-size: 18pt; font-weight: 600; }
QLabel#pageSubtitle { color: #6b7280; }

QFrame#card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
}
QLabel#statValue { font-size: 22pt; font-weight: 600; }
QLabel#statLabel { color: #6b7280; }
QLabel#phaseBadge {
    background: #eef2ff;
    color: #4338ca;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
}
QLabel#muted { color: #6b7280; }

QGroupBox {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    margin-top: 14px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 5px 8px;
    font-weight: normal;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { background: #f3f4f6; color: #9ca3af; }
QPlainTextEdit#logView { font-family: Consolas; font-size: 9pt; }

QCheckBox { font-weight: normal; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #9ca3af;
    border-radius: 4px;
    background: white;
}
QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; }
QCheckBox::indicator:disabled { background: #f3f4f6; border-color: #d1d5db; }
QCheckBox::indicator:checked:disabled { background: #93c5fd; border-color: #93c5fd; }

QTableWidget, QListWidget {
    background: white;
    alternate-background-color: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    gridline-color: #f0f1f3;
    selection-background-color: #dbeafe;
    selection-color: #1f2937;
    font-weight: normal;
}
QHeaderView::section {
    background: #f9fafb;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    padding: 6px 8px;
    font-weight: 600;
    color: #4b5563;
}
QSplitter::handle { background: transparent; }
QPushButton:disabled { color: #9ca3af; background: #f9fafb; }

QWidget#taskbar { background: #eef2ff; border-top: 1px solid #c7d2fe; }
QProgressBar { border: 1px solid #c7d2fe; border-radius: 4px; background: white; max-height: 10px; }
QProgressBar::chunk { background: #3b82f6; border-radius: 3px; }

QPushButton {
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover { background: #f3f4f6; }
QPushButton#primary { background: #3b82f6; border-color: #3b82f6; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #2563eb; }
"""
