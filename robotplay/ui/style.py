"""
Application-wide Qt style sheet — a modern dark "engineering software" theme.

Colours are pulled from the shared `Palette` so the whole look changes from one
place. Kept as a single function returning a QSS string.
"""

from __future__ import annotations

from ..config import CONFIG


def build_stylesheet() -> str:
    p = CONFIG.palette
    return f"""
    * {{ font-family:'Segoe UI','Inter',Arial,sans-serif; font-size:13px; }}
    QMainWindow, QWidget {{ background:{p.bg}; color:{p.text}; }}
    QToolTip {{ background:{p.panel}; color:{p.text};
               border:1px solid {p.border}; padding:4px; }}

    QGroupBox {{
        border:1px solid {p.border}; border-radius:8px;
        margin-top:12px; padding-top:10px;
        font-weight:600; color:{p.text_dim}; font-size:12px;
    }}
    QGroupBox::title {{ subcontrol-origin:margin; left:12px; padding:0 5px;
                        text-transform:uppercase; letter-spacing:1px; }}

    QPushButton {{
        background:#21262d; border:1px solid {p.border};
        border-radius:6px; padding:7px 14px; color:{p.text};
    }}
    QPushButton:hover  {{ background:#30363d; border-color:{p.accent}; }}
    QPushButton:pressed {{ background:#388bfd22; }}
    QPushButton:disabled {{ color:#484f58; border-color:#21262d; background:#161b22; }}
    QPushButton:checked {{ background:#1f6feb33; border-color:{p.accent};
                           color:{p.accent}; }}

    QPushButton#btn_record {{
        background:#1a472a; border:1px solid {p.ok_dim};
        color:#56d364; font-size:14px; font-weight:bold; padding:12px;
    }}
    QPushButton#btn_record:hover  {{ background:#2ea04335; }}
    QPushButton#btn_play {{
        background:#1f3a5f; border:1px solid #388bfd;
        color:{p.accent}; font-size:14px; font-weight:bold; padding:12px;
    }}
    QPushButton#btn_play:hover {{ background:#388bfd35; }}
    QPushButton#btn_danger {{ background:#3d1f1f; border-color:{p.err}; color:#ff7b72; }}
    QPushButton#btn_danger:hover {{ background:#f8514922; }}

    QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
        background:{p.panel}; border:1px solid {p.border};
        border-radius:5px; padding:5px 8px; color:{p.text};
        selection-background-color:{p.accent};
    }}
    QComboBox::drop-down {{ border:none; width:18px; }}
    QComboBox QAbstractItemView {{ background:{p.panel}; color:{p.text};
        border:1px solid {p.border}; selection-background-color:#1f6feb55; }}

    QListWidget, QTableWidget, QTextEdit {{
        background:{p.panel}; border:1px solid {p.border};
        border-radius:6px; padding:2px;
    }}
    QTableWidget {{ gridline-color:{p.border}; }}
    QTableWidget::item {{ padding:3px 6px; }}
    QTableWidget::item:selected {{ background:#1f6feb44; color:#fff; }}
    QHeaderView::section {{
        background:#1c2128; color:{p.text_dim}; padding:5px 6px;
        border:none; border-right:1px solid {p.border};
        border-bottom:1px solid {p.border}; font-weight:600;
    }}
    QTableCornerButton::section {{ background:#1c2128; border:none; }}

    QTextEdit {{
        color:{p.mono_green};
        font-family:'Cascadia Code','Consolas','Courier New',monospace;
        font-size:12px;
    }}

    QTabWidget::pane {{ border:1px solid {p.border}; border-radius:6px; top:-1px; }}
    QTabBar::tab {{
        background:{p.panel}; border:1px solid {p.border}; border-bottom:none;
        padding:7px 18px; margin-right:2px; color:{p.text_dim};
        border-top-left-radius:6px; border-top-right-radius:6px;
    }}
    QTabBar::tab:selected {{ background:#21262d; color:{p.accent}; }}

    QStatusBar {{ background:{p.panel}; color:{p.text_dim}; font-size:12px; }}
    QSplitter::handle {{ background:{p.border}; }}
    QSplitter::handle:horizontal {{ width:2px; }}
    QScrollBar:vertical {{ background:{p.bg}; width:11px; margin:0; }}
    QScrollBar::handle:vertical {{ background:#30363d; border-radius:5px; min-height:24px; }}
    QScrollBar::handle:vertical:hover {{ background:#3f4855; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}

    QSlider::groove:horizontal {{ height:4px; background:{p.border}; border-radius:2px; }}
    QSlider::handle:horizontal {{ background:{p.accent}; width:14px; height:14px;
        margin:-6px 0; border-radius:7px; }}
    QSlider::sub-page:horizontal {{ background:{p.accent}; border-radius:2px; }}

    QLabel#mono {{
        font-family:'Cascadia Code','Consolas','Courier New',monospace;
        font-size:12px; color:{p.mono_green}; background:{p.panel};
        border:1px solid {p.border}; border-radius:6px; padding:8px;
    }}
    QLabel#hint {{ color:#6e7681; font-size:11px; }}
    QLabel#h1 {{ color:{p.text}; font-size:15px; font-weight:600; }}
    """
