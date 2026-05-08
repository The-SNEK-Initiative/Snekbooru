import os
import re

from PyQt5.QtCore import QStandardPaths, Qt, QSize, QRect, QStringListModel
from PyQt5.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QPainter, QTextCursor, QTextFormat
from PyQt5.QtWidgets import QWidget, QPlainTextEdit, QCompleter, QTextEdit


# --------------------------- Constants --------------------------- #
SCSS_KEYWORDS = [
    'sWidget', 'sLabel', 'sPushButton', 'sLineEdit', 'sPlainTextEdit', 'sComboBox', 
    'sSpinBox', 'sCheckBox', 'sSlider', 'sProgressBar', 'sGroupBox', 'sListWidget', 
    'sTableView', 'sHeaderView', 'sTabWidget', 'sTabBar', 'sScrollArea', 'sScrollBar', 
    'sFrame', 'sMenu', 'sSplitter', 'sToolButton', 'sTextBrowser', 'sDialog',
    'sWidget#custom_title_bar', 'sLabel#title', 'sLabel#app_logo_mini', 
    'sLabel#total_posts_label', 'sLabel#disclaimer_label', 'sGroupBox#danger_zone',
    'sPushButton#reset_button', 'sPushButton[looping="true"]'
]

SCSS_PROPERTIES = [
    'background-color', 'background-image', 'background', 'color', 'border', 
    'border-radius', 'padding', 'margin', 'font-size', 'font-family', 'font-weight', 
    'min-width', 'max-width', 'min-height', 'max-height', 'text-align', 
    'selection-background-color', 'border-color', 'alignment', 'subcontrol-origin', 
    'subcontrol-position', 'qlineargradient', 'border-image', 'width', 'height',
    'border-top', 'border-bottom', 'border-left', 'border-right', 'opacity',
    'border-top-left-radius', 'border-top-right-radius', 'border-bottom-left-radius',
    'border-bottom-right-radius', 'outline', 'spacing'
]

SCSS_PSEUDO = [
    ':hover', ':pressed', ':disabled', ':checked', ':unchecked', ':focus', 
    ':selected', '::chunk', '::tab', '::pane', '::title', '::handle', 
    '::up-arrow', '::down-arrow', '::left-arrow', '::right-arrow', 
    '::add-line', '::sub-line', '::add-page', '::sub-page', '::item',
    ':vertical', ':horizontal'
]


# --------------------------- Theme Management --------------------------- #
def get_themes_path():
    """Returns the path to the custom themes directory.
    Uses stable, version-independent path to ensure cross-version compatibility."""
    from snekbooru.core.config import get_app_data_dir
    path = os.path.join(get_app_data_dir(), "themes")
    os.makedirs(path, exist_ok=True)
    return path

def load_custom_themes():
    """Loads all .snek.css themes from the user's custom theme directory."""
    themes_dir = get_themes_path()
    themes = {}
    try:
        for filename in os.listdir(themes_dir):
            if filename.lower().endswith('.snek.css'):
                theme_path = os.path.join(themes_dir, filename)
                with open(theme_path, 'r', encoding='utf-8') as f:
                    # Key is filename, value is content
                    themes[filename] = f.read()
    except Exception as e:
        print(f"Could not load custom themes: {e}")
    return themes

def get_fonts_path():
    """Returns the path to the custom fonts directory.
    Uses stable, version-independent path to ensure cross-version compatibility."""
    from snekbooru.core.config import get_app_data_dir
    path = os.path.join(get_app_data_dir(), "fonts")
    os.makedirs(path, exist_ok=True)
    return path

def load_custom_fonts():
    """Loads all .ttf and .otf fonts from the user's custom font directory."""
    from PyQt5.QtGui import QFontDatabase
    fonts_dir = get_fonts_path()
    font_db = QFontDatabase()
    loaded_fonts = []
    try:
        for filename in os.listdir(fonts_dir):
            if filename.lower().endswith(('.ttf', '.otf')):
                font_path = os.path.join(fonts_dir, filename)
                font_id = font_db.addApplicationFont(font_path)
                if font_id != -1:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        loaded_fonts.append(f"'{families[0]}' from {filename}")
        if loaded_fonts:
            print("Loaded custom fonts:", ", ".join(loaded_fonts))
    except Exception as e:
        print(f"Could not load custom fonts: {e}")
    return fonts_dir

# --------------------------- sCSS Pre-processor --------------------------- #
def preprocess_stylesheet(scss_string):
    """
    Translates the custom 'sCSS' syntax (e.g., sPushButton) into standard Qt CSS.
    This allows the user to work with a fully branded styling system.
    """
    # 1. Process class selectors: .my-class -> [class~="my-class"]
    processed_style = re.sub(r'(?<![a-zA-Z0-9/])\.([a-zA-Z_][a-zA-Z0-9_-]*)', r'[class~="\1"]', scss_string)

    # 2. Process s-widget type selectors: sPushButton -> QPushButton
    replacements = {
        'sCheckBox': 'QCheckBox', 'sComboBox': 'QComboBox', 'sDialog': 'QDialog',
        'sFrame': 'QFrame', 'sGroupBox': 'QGroupBox', 'sHeaderView': 'QHeaderView',
        'sLabel': 'QLabel', 'sLineEdit': 'QLineEdit', 'sListWidget': 'QListWidget',
        'sMenu': 'QMenu', 'sPlainTextEdit': 'QPlainTextEdit', 'sProgressBar': 'QProgressBar',
        'sPushButton': 'QPushButton', 'sScrollBar': 'QScrollBar', 'sScrollArea': 'QScrollArea',
        'sSlider': 'QSlider', 'sSpinBox': 'QSpinBox', 'sSplitter': 'QSplitter',
        'sTabBar': 'QTabBar', 'sTabWidget': 'QTabWidget', 'sTableView': 'QTableView',
        'sTextBrowser': 'QTextBrowser', 'sWidget': 'QWidget',
    }
    
    for s_name, q_name in replacements.items():
        pattern = r'\b' + re.escape(s_name) + r'\b'
        processed_style = re.sub(pattern, q_name, processed_style)
        
    return processed_style

# --------------------------- Code Editor --------------------------- #
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.codeEditor.lineNumberAreaPaintEvent(event)

class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()
        
        # Font
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)
        
        # Completer
        self.completer = None

    def lineNumberAreaWidth(self):
        digits = 1
        max_val = max(1, self.blockCount())
        while max_val >= 10:
            max_val //= 10
            digits += 1
        space = 10 + self.fontMetrics().width('9') * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def highlightCurrentLine(self):
        extraSelections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            bg_color = self.palette().color(self.backgroundRole())
            if bg_color.lightness() < 128:
                 lineColor = QColor("#2a2a2a")
            else:
                 lineColor = QColor("#e8e8ff")
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        bg_color = self.palette().color(self.backgroundRole())
        area_bg = QColor("#2b2b2b") if bg_color.lightness() < 128 else QColor("#f0f0f0")
        text_color = QColor("#888888")
        
        painter.fillRect(event.rect(), area_bg)
        
        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(text_color)
                painter.drawText(0, top, self.lineNumberArea.width() - 5, self.fontMetrics().height(), Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1

    def setCompleter(self, completer):
        if self.completer:
            self.completer.activated.disconnect()
        self.completer = completer
        if not self.completer:
            return
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self.insertCompletion)

    def insertCompletion(self, completion):
        if self.completer.widget() != self:
            return
        tc = self.textCursor()
        extra = len(completion) - len(self.completer.completionPrefix())
        tc.movePosition(QTextCursor.Left)
        tc.movePosition(QTextCursor.EndOfWord)
        tc.insertText(completion[-extra:])
        self.setTextCursor(tc)

    def textUnderCursor(self):
        tc = self.textCursor()
        tc.select(QTextCursor.WordUnderCursor)
        return tc.selectedText()

    def focusInEvent(self, e):
        if self.completer:
            self.completer.setWidget(self)
        super().focusInEvent(e)

    def keyPressEvent(self, e):
        if self.completer and self.completer.popup().isVisible():
            if e.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape, Qt.Key_Tab, Qt.Key_Backtab):
                e.ignore()
                return

        # Auto-indentation
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()
            indentation = ""
            for char in text:
                if char.isspace():
                    indentation += char
                else:
                    break
            if text.rstrip().endswith('{'):
                indentation += "    "
            
            super().keyPressEvent(e)
            self.insertPlainText(indentation)
            return
            
        # Auto-close brackets
        if e.key() == Qt.Key_BraceLeft:
            super().keyPressEvent(e)
            self.insertPlainText("}")
            self.moveCursor(QTextCursor.Left)
            return

        isShortcut = ((e.modifiers() & Qt.ControlModifier) and e.key() == Qt.Key_Space)
        if not self.completer or not isShortcut:
            super().keyPressEvent(e)

        ctrlOrShift = e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)
        if not self.completer or (ctrlOrShift and len(e.text()) == 0):
            return

        eow = "~!@#$%^&*()_+{}|:\"<>?,./;'[]\\-="
        hasModifier = (e.modifiers() != Qt.NoModifier) and not ctrlOrShift
        completionPrefix = self.textUnderCursor()

        if not isShortcut and (hasModifier or len(e.text()) == 0 or len(completionPrefix) < 1 or e.text()[-1] in eow):
            self.completer.popup().hide()
            return

        if completionPrefix != self.completer.completionPrefix():
            self.completer.setCompletionPrefix(completionPrefix)
            self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))

        cr = self.cursorRect()
        cr.setWidth(self.completer.popup().sizeHintForColumn(0) + self.completer.popup().verticalScrollBar().sizeHint().width())
        self.completer.complete(cr)

# --------------------------- Syntax Highlighter --------------------------- #
class sCSSHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)
        self.highlighting_rules = []

        # Keywords (s-widgets)
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6")); keyword_format.setFontWeight(QFont.Bold)
        for word in SCSS_KEYWORDS: 
            pattern = r'\b' + re.escape(word) + r'\b'
            if '#' in word or '[' in word:
                pattern = re.escape(word)
            self.highlighting_rules.append((re.compile(pattern), keyword_format))

        # Properties
        property_format = QTextCharFormat(); property_format.setForeground(QColor("#9CDCFE"))
        for word in SCSS_PROPERTIES: self.highlighting_rules.append((re.compile(r'\b' + re.escape(word) + r'(?=\s*:)'), property_format))

        # Pseudo-states
        pseudo_format = QTextCharFormat(); pseudo_format.setForeground(QColor("#C586C0"))
        for word in SCSS_PSEUDO: self.highlighting_rules.append((re.compile(re.escape(word)), pseudo_format))

        # Values (numbers, hex colors)
        value_format = QTextCharFormat(); value_format.setForeground(QColor("#D7BA7D"))
        self.highlighting_rules.append((re.compile(r'#[0-9a-fA-F]{3,8}\b'), value_format))
        self.highlighting_rules.append((re.compile(r'\b\d+(px|pt|em)?\b'), value_format))

        # Strings (in quotes)
        string_format = QTextCharFormat(); string_format.setForeground(QColor("#CE9178"))
        self.highlighting_rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), string_format))
        self.highlighting_rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), string_format))

        # Object Names (#id) and Pseudo-states (:hover)
        selector_format = QTextCharFormat(); selector_format.setForeground(QColor("#C586C0"))
        self.highlighting_rules.append((re.compile(r'#[A-Za-z0-9_-]+'), selector_format))
        self.highlighting_rules.append((re.compile(r'::?[a-zA-Z-]+'), selector_format))

        # Comments
        self.comment_format = QTextCharFormat(); self.comment_format.setForeground(QColor("#6A9955"))
        self.comment_start_expression = re.compile(r'/\*'); self.comment_end_expression = re.compile(r'\*/')

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in re.finditer(pattern, text): self.setFormat(match.start(), match.end() - match.start(), format)
        self.setCurrentBlockState(0)
        start_index = 0
        if self.previousBlockState() != 1:
            match = self.comment_start_expression.search(text, 0)
            start_index = match.start() if match else -1
        while start_index >= 0:
            match = self.comment_end_expression.search(text, start_index)
            if not match:
                self.setCurrentBlockState(1); comment_length = len(text) - start_index
            else:
                comment_length = match.end() - start_index
            self.setFormat(start_index, comment_length, self.comment_format)
            match = self.comment_start_expression.search(text, start_index + comment_length)
            start_index = match.start() if match else -1

# --------------------------- Themes --------------------------- #

PYGMENTS_CSS = """
.codehilite .hll { background-color: #49483e }
.codehilite  { background: #272822; color: #f8f8f2; border-radius: 4px; padding: 10px; }
.codehilite .c { color: #75715e } /* Comment */
.codehilite .err { color: #960050; background-color: #1e0010 } /* Error */
.codehilite .k { color: #66d9ef } /* Keyword */
.codehilite .l { color: #ae81ff } /* Literal */
.codehilite .n { color: #f8f8f2 } /* Name */
.codehilite .o { color: #f92672 } /* Operator */
.codehilite .p { color: #f8f8f2 } /* Punctuation */
.codehilite .ch { color: #75715e } /* Comment.Hashbang */
.codehilite .cm { color: #75715e } /* Comment.Multiline */
.codehilite .cp { color: #75715e } /* Comment.Preproc */
.codehilite .cpf { color: #75715e } /* Comment.PreprocFile */
.codehilite .c1 { color: #75715e } /* Comment.Single */
.codehilite .cs { color: #75715e } /* Comment.Special */
.codehilite .kc { color: #66d9ef } /* Keyword.Constant */
.codehilite .kd { color: #66d9ef } /* Keyword.Declaration */
.code.hilite .kn { color: #f92672 } /* Keyword.Namespace */
.codehilite .kp { color: #66d9ef } /* Keyword.Pseudo */
.codehilite .kr { color: #66d9ef } /* Keyword.Reserved */
.codehilite .kt { color: #66d9ef } /* Keyword.Type */
.codehilite .ld { color: #e6db74 } /* Literal.Date */
.codehilite .m { color: #ae81ff } /* Literal.Number */
.codehilite .s { color: #e6db74 } /* Literal.String */
.codehilite .na { color: #a6e22e } /* Name.Attribute */
.codehilite .nb { color: #f8f8f2 } /* Name.Builtin */
.codehilite .nc { color: #a6e22e } /* Name.Class */
.codehilite .no { color: #66d9ef } /* Name.Constant */
.codehilite .nd { color: #a6e22e } /* Name.Decorator */
.codehilite .ni { color: #f8f8f2 } /* Name.Entity */
.codehilite .ne { color: #a6e22e } /* Name.Exception */
.codehilite .nf { color: #a6e22e } /* Name.Function */
.codehilite .nl { color: #f8f8f2 } /* Name.Label */
.codehilite .nn { color: #f8f8f2 } /* Name.Namespace */
.codehilite .nt { color: #f92672 } /* Name.Tag */
.codehilite .nv { color: #f8f8f2 } /* Name.Variable */
.codehilite .ow { color: #f92672 } /* Operator.Word */
.codehilite .w { color: #f8f8f2 } /* Text.Whitespace */
.codehilite .mb { color: #ae81ff } /* Literal.Number.Bin */
.codehilite .mf { color: #ae81ff } /* Literal.Number.Float */
.codehilite .mh { color: #ae81ff } /* Literal.Number.Hex */
.codehilite .mi { color: #ae81ff } /* Literal.Number.Integer */
.codehilite .mo { color: #ae81ff } /* Literal.Number.Oct */
.codehilite .sa { color: #e6db74 } /* Literal.String.Affix */
.codehilite .sb { color: #e6db74 } /* Literal.String.Backtick */
.codehilite .sc { color: #e6db74 } /* Literal.String.Char */
.codehilite .dl { color: #e6db74 } /* Literal.String.Delimiter */
.codehilite .sd { color: #e6db74 } /* Literal.String.Doc */
.codehilite .s2 { color: #e6db74 } /* Literal.String.Double */
.codehilite .se { color: #ae81ff } /* Literal.String.Escape */
.codehilite .sh { color: #e6db74 } /* Literal.String.Heredoc */
.codehilite .si { color: #e6db74 } /* Literal.String.Interpol */
.codehilite .sx { color: #e6db74 } /* Literal.String.Other */
.codehilite .sr { color: #e6db74 } /* Literal.String.Regex */
.codehilite .s1 { color: #e6db74 } /* Literal.String.Single */
.codehilite .ss { color: #e6db74 } /* Literal.String.Symbol */
.codehilite .bp { color: #f8f8f2 } /* Name.Builtin.Pseudo */
.codehilite .vc { color: #f8f8f2 } /* Name.Variable.Class */
.codehilite .vg { color: #f8f8f2 } /* Name.Variable.Global */
.codehilite .vi { color: #f8f8f2 } /* Name.Variable.Instance */
.codehilite .il { color: #ae81ff } /* Literal.Number.Integer.Long */
"""

DARK_STYLESHEET = """
* { 
    font-size: 14px; 
    font-family: 'Segoe UI', Arial, sans-serif;
}
sWidget { 
    background-color: #121212; 
    color: #eaeaea; 
    border: none;
}
sLineEdit, sPlainTextEdit, sListWidget, sComboBox, sSpinBox { 
    background: #1e1e1e; 
    color: #eaeaea; 
    border: 1px solid #333; 
    border-radius: 4px; 
    padding: 6px; 
    selection-background-color: #3a3a3a;
}
sPushButton { 
    background: #2a2a2a; 
    color: #eaeaea; 
    border: 1px solid #3a3a3a; 
    border-radius: 4px; 
    padding: 8px 12px; 
    min-height: 30px;
}
sPushButton:hover { 
    background: #333333; 
    border: 1px solid #444;
}
sPushButton:pressed { 
    background: #3a3a3a; 
}
sPushButton:disabled {
    background: #1a1a1a;
    color: #666;
}
sScrollArea { 
    border: none; 
    background: transparent;
}
sScrollArea > sWidget > sWidget {
    background: transparent;
}
sLabel#title { 
    font-size: 18px; 
    font-weight: 600; 
}
sLabel#app_logo_mini {
    padding-right: 10px;
}
sGroupBox {
    font-weight: bold;
    border: 1px solid #333;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 15px;
}
sGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 5px;
}
sTabWidget::pane {
    border: 1px solid #333;
    border-radius: 4px;
}
sTabWidget::tab-bar {
    alignment: center;
}
sTabBar::tab {
    background: #1e1e1e;
    color: #aaa;
    padding: 8px 16px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
sTabBar::tab:selected {
    background: #2a2a2a;
    color: #fff;
    border-bottom: 2px solid #5b5bff;
}
sProgressBar {
    border: 1px solid #333;
    border-radius: 4px;
    text-align: center;
    background: #1e1e1e;
}
sProgressBar::chunk {
    background: #5b5bff;
    width: 10px;
}
.video-thumb {
    border: 2px solid #5b5bff;
}
sLabel#total_posts_label {
    font-size: 72px;
    font-weight: 900;
    color: #5b5bff;
}
sLabel#disclaimer_label {
    font-size: 12px;
    color: #888;
}
sGroupBox#danger_zone {
    border-color: #c33;
}
sGroupBox#danger_zone::title {
    color: #f66;
}
sPushButton#reset_button {
    background-color: #400; color: #fcc; border-color: #a00;
}
sSplitter::handle {
    background: #2a2a2a;
}

sSplitter::handle:hover {
    background: #2a2a2a;
}
sSplitter::handle:hover {
    background: #5b5bff;
}
sMenu {
    background-color: #1e1e1e;
    border: 1px solid #333;
}
sMenu::item:selected {
    background-color: #3a3a3a;
}
sPushButton[looping="true"] {
    background-color: #3a5f3a;
    border-color: #4a7f4a;
}
sPushButton[looping="true"]:hover {
    background-color: #4a7f4a;
}
"""

LIGHT_STYLESHEET = """
* { 
    font-size: 14px; 
    font-family: 'Segoe UI', Arial, sans-serif;
}
sWidget { 
    background-color: #f5f5f5; 
    color: #1a1a1a; 
    border: none;
}
sWidget#custom_title_bar {
    background-color: #e0e0e0;
}
/* --- Custom ScrollBar --- */
sScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 0px;
}
sScrollBar::handle:vertical {
    background: #454545;
    min-height: 25px;
    border-radius: 4px;
}
sScrollBar::handle:vertical:hover { background: #555555; }
sScrollBar::add-line:vertical, sScrollBar::sub-line:vertical { border: none; background: none; height: 0px; }
sScrollBar::add-page:vertical, sScrollBar::sub-page:vertical { background: none; }
sScrollBar:horizontal {
    border: none;
    background: transparent;
    height: 8px;
    margin: 0px;
}
sScrollBar::handle:horizontal { background: #454545; min-width: 25px; border-radius: 4px; }
sScrollBar::handle:horizontal:hover { background: #555555; }
sScrollBar::add-line:horizontal, sScrollBar::sub-line:horizontal { border: none; background: none; width: 0px; }
sScrollBar::add-page:horizontal, sScrollBar::sub-page:horizontal { background: none; }
sLabel#custom_title_bar_label {
    font-weight: bold;
    padding-left: 5px;
}
sToolButton#title_bar_button {
    background: transparent;
    border: none;
}
sToolButton#title_bar_button:hover {
    background: #dcdcdc;
}
sToolButton#close_button:hover {
    border: none;
}
sLineEdit, sPlainTextEdit, sListWidget, sComboBox, sSpinBox { 
    background: #ffffff; 
    color: #1a1a1a; 
    border: 1px solid #cfcfcf; 
    border-radius: 4px; 
    padding: 6px; 
    selection-background-color: #cce0ff;
}
sPushButton { 
    background: #f0f0f0; 
    color: #1a1a1a; 
    border: 1px solid #dcdcdc; 
    border-radius: 4px; 
    padding: 8px 12px; 
    min-height: 30px;
}
sPushButton:hover { 
    background: #e5e5e5; 
    border: 1px solid #ccc;
}
sPushButton:pressed { 
    background: #dcdcdc; 
}
sPushButton:disabled {
    background: #f8f8f8;
    color: #aaa;
}
sScrollArea { 
    border: none; 
    background: transparent;
}
sScrollArea > sWidget > sWidget {
    background: transparent;
}
sLabel#title { 
    font-size: 18px; 
    font-weight: 600; 
}
sLabel#app_logo_mini {
    padding-right: 10px;
}
sGroupBox {
    font-weight: bold;
    border: 1px solid #dcdcdc;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 15px;
}
sGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 5px;
}
sTabWidget::pane {
    border: 1px solid #dcdcdc;
    border-radius: 4px;
}
sTabWidget::tab-bar {
    alignment: center;
}
sTabBar::tab {
    background: #f0f0f0;
    color: #555;
    padding: 8px 16px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
sTabBar::tab:selected {
    background: #ffffff;
    color: #000;
    border-bottom: 2px solid #5b5bff;
}
sProgressBar {
    border: 1px solid #dcdcdc;
    border-radius: 4px;
    text-align: center;
    background: #ffffff;
}
sProgressBar::chunk {
    background: #5b5bff;
    width: 10px;
}
.video-thumb {
    border: 2px solid #5b5bff;
}
sLabel#total_posts_label {
    font-size: 72px;
    font-weight: 900;
    color: #5b5bff;
}
sLabel#disclaimer_label {
    font-size: 12px;
    color: #666;
}
sGroupBox#danger_zone {
    border-color: #c33;
}
sGroupBox#danger_zone::title {
    color: #c33;
}
sPushButton#reset_button {
    background-color: #fdd; color: #a00; border-color: #c33;
}
sSplitter::handle {
    background: #e5e5e5;
}
sSplitter::handle:hover {
    background: #cce0ff;
}
sMenu {
    background-color: #ffffff;
    border: 1px solid #cfcfcf;
}
sMenu::item:selected {
    background-color: #cce0ff;
}
sPushButton[looping="true"] {
    background-color: #d9f0d9;
    border-color: #b9e0b9;
}
sPushButton[looping="true"]:hover {
    background-color: #c9e0c9;
}
"""

INCOGNITO_STYLESHEET = """
* { 
    font-size: 14px; 
    font-family: 'Segoe UI', Arial, sans-serif;
}
sWidget { 
    background-color: #1a1a2e; /* base_bg */
    color: #e0e0ff; /* text_color */
    border: none;
}

/* --- Inputs & Lists --- */
sLineEdit, sPlainTextEdit, sListWidget, sComboBox, sSpinBox {
    background: #24243e; /* ui_bg */
    color: #e0e0ff; 
    border: 1px solid #4a4a6a; /* border_color */
    border-radius: 4px; 
    padding: 6px; 
    selection-background-color: #4a4a6a;
}

/* --- Buttons --- */
sPushButton { 
    background: #2e2e4f; /* hover_bg */
    color: #e0e0ff; 
    border: 1px solid #4a4a6a; 
    border-radius: 4px; 
    padding: 8px 12px; 
    min-height: 30px;
}
sPushButton:hover { 
    background: #3a3a5f; /* pressed_bg */
    border-color: #5a5a7a;
}
sPushButton:pressed { 
    background: #4a4a6a; 
}
sPushButton:disabled {
    background: #24243e;
    color: #80809f;
}

/* --- Containers & Layout --- */
sGroupBox {
    font-weight: bold;
    border: 1px solid #4a4a6a;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 15px;
}
sGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 5px;
    color: #c0c0ff;
}
sSplitter::handle {
    background: #2e2e4f;
}
sSplitter::handle:hover {
    background: #9a70ff; /* accent */
}

/* --- Tabs --- */
sTabWidget::pane {
    border: 1px solid #4a4a6a;
    border-radius: 4px;
}
sTabWidget::tab-bar {
    alignment: center;
}
sTabBar::tab {
    background: #24243e;
    color: #a0a0cf; /* subtle_text */
    padding: 8px 16px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
sTabBar::tab:hover {
    background: #2e2e4f;
    color: #e0e0ff;
}
sTabBar::tab:selected {
    background: #2e2e4f;
    color: #fff;
    border-bottom: 2px solid #9a70ff; /* accent */
}

/* --- Other Widgets --- */
sProgressBar {
    border: 1px solid #4a4a6a;
    border-radius: 4px;
    text-align: center;
    background: #24243e;
    color: #e0e0ff;
}
sProgressBar::chunk {
    background: #9a70ff; /* accent */
    border-radius: 3px;
}
sMenu {
    background-color: #24243e;
    border: 1px solid #4a4a6a;
}
sMenu::item:selected {
    background-color: #3a3a5f;
}

/* --- Title Bar --- */
sWidget#main_window_title_bar, sWidget#dialog_title_bar {
    background-color: #2e2e4f;
}
sToolButton#title_bar_button:hover {
    background: #3a3a5f;
}
sToolButton#close_button:hover {
    background-color: #c33;
}
"""

EXAMPLE_STYLESHEET = """
/* Snekbooru Example Theme: "Vaporwave Sunset" */

* { 
    font-family: 'Comic Sans MS', 'Impact', sans-serif; /* Example font */
    font-size: 15px; 
}
sWidget { 
    background-color: #0d0221; 
    color: #ffccff; 
}
sLineEdit, sPlainTextEdit, sListWidget, sComboBox, sSpinBox, sTableView { 
    background-color: #261447;
    /* background-image: url("path/to/your/image.png");  Example background image */
    color: #f0f0f0; 
    border: 1px solid #ff79c6; 
    border-radius: 0px; 
    padding: 6px; 
}
sPushButton { 
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2DE2E6, stop:1 #F706CF);
    color: #0d0221;
    border: 2px solid #0d0221;
    border-radius: 8px; 
    padding: 8px 12px; 
    font-weight: bold;
}
sPushButton:hover { 
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #F706CF, stop:1 #2DE2E6);
}
sGroupBox {
    border: 1px solid #ff79c6;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 15px;
}
sGroupBox::title {
    color: #2DE2E6;
    font-weight: bold;
}


/* Tab Styling */
sTabWidget::pane {
    border: 1px solid #ff79c6;
    border-top: 0px;
}
sTabBar::tab {
    background: #261447;
    color: #ffccff;
    border: 1px solid #ff79c6;
    border-bottom: none;
    padding: 8px 20px;
    margin-right: 2px;
}
sTabBar::tab:hover {
    background: #4d288a;
}
sTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2DE2E6, stop:1 #F706CF);
    color: #0d0221;
    font-weight: bold;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
"""