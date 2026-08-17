"""
Clean, professional minimal dark-gray theme for ConnectToPhone Desktop.
Matte solid colors with simple blue, green, amber, and red accents (no neon).
"""

MAIN_STYLESHEET = """
/* Base application styling */
QWidget {
    background-color: #18181B;
    color: #F4F4F5;
    font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Ubuntu', sans-serif;
    font-size: 13px;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
}

/* Main Window */
QMainWindow {
    background-color: #18181B;
}

/* Card panels */
QFrame.CardFrame {
    background-color: #27272A;
    border: 1px solid #3F3F46;
    border-radius: 8px;
}

/* Buttons */
QPushButton {
    background-color: #3F3F46;
    color: #F4F4F5;
    border: 1px solid #52525B;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #52525B;
    border-color: #71717A;
}

QPushButton:pressed {
    background-color: #27272A;
}

QPushButton:disabled {
    background-color: #27272A;
    color: #71717A;
    border-color: #3F3F46;
}

/* Solid Blue Action Button */
QPushButton.PrimaryButton, QPushButton.CopyButton {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #3B82F6;
    border-radius: 6px;
    padding: 5px 14px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton.PrimaryButton:hover, QPushButton.CopyButton:hover {
    background-color: #1D4ED8;
    border-color: #60A5FA;
}

QPushButton.PrimaryButton:pressed, QPushButton.CopyButton:pressed {
    background-color: #1E40AF;
}

/* Connect / Pair Header Button */
QPushButton.ConnectHeaderButton {
    background-color: #27272A;
    border: 1px solid #3F3F46;
    border-radius: 8px;
    padding: 8px 12px;
    font-weight: 600;
    font-size: 12px;
    color: #F4F4F5;
    text-align: center;
}

QPushButton.ConnectHeaderButton:hover {
    background-color: #3F3F46;
    border-color: #2563EB;
}

/* Clickable Phone Mirror Trigger Button */
QPushButton.PhoneMirrorButton {
    background-color: #27272A;
    border: 2px solid #3F3F46;
    border-radius: 12px;
    padding: 8px;
}

QPushButton.PhoneMirrorButton:hover {
    background-color: #3F3F46;
    border-color: #2563EB;
}

QPushButton.PhoneMirrorButton:pressed {
    background-color: #18181B;
}

/* Badges & Status */
QLabel.BadgeSuccess {
    color: #22C55E;
    font-weight: 600;
    font-size: 12px;
}

QLabel.BadgeWarning {
    color: #F59E0B;
    font-weight: 600;
    font-size: 12px;
}

QLabel.BadgeNeutral {
    color: #A1A1AA;
    font-weight: 500;
    font-size: 12px;
}

/* Titles and Text */
QLabel.DeviceTitle {
    color: #F4F4F5;
    font-size: 16px;
    font-weight: 700;
}

QLabel.SectionTitle {
    color: #F4F4F5;
    font-size: 14px;
    font-weight: 700;
}

QLabel.SubText {
    color: #A1A1AA;
    font-size: 12px;
}

/* Checkbox */
QCheckBox {
    color: #E4E4E7;
    spacing: 8px;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #52525B;
    background-color: #18181B;
}

QCheckBox::indicator:checked {
    background-color: #2563EB;
    border-color: #3B82F6;
}

/* Scroll Area & Bars */
QScrollArea {
    background: transparent;
    border: none;
}

QScrollBar:vertical {
    border: none;
    background: #18181B;
    width: 6px;
    margin: 0px;
    border-radius: 3px;
}

QScrollBar::handle:vertical {
    background: #3F3F46;
    min-height: 20px;
    border-radius: 3px;
}

QScrollBar::handle:vertical:hover {
    background: #52525B;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Dialogs */
QDialog {
    background-color: #18181B;
    border: 1px solid #3F3F46;
    border-radius: 10px;
}
"""
