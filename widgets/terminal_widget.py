"""
终端控件：基于 pyte 终端模拟器 + QPlainTextEdit 渲染
- pyte 负责所有 ANSI 解析、光标控制、退格/回车覆盖、清屏等
- Qt 控件只负责渲染虚拟屏幕和转发按键
"""
from PyQt5 import QtWidgets, QtCore, QtGui
import pyte
from wcwidth import wcwidth


# 颜色映射（pyte 调色板索引 -> Qt 颜色）
# 使用经典的 xterm 256 色的前 16 色 + 默认前景/背景
_COLOR_MAP = {
    # 0-7: 标准色（暗）
    0:  '#000000',   # 黑
    1:  '#CD0000',   # 红
    2:  '#00CD00',   # 绿
    3:  '#CDCD00',   # 黄
    4:  '#0000EE',   # 蓝
    5:  '#CD00CD',   # 品红
    6:  '#00CDCD',   # 青
    7:  '#E5E5E5',   # 白（灰）
    # 8-15: 亮色
    8:  '#7F7F7F',   # 深灰
    9:  '#FF0000',   # 亮红
    10: '#00FF00',   # 亮绿
    11: '#FFFF00',   # 亮黄
    12: '#5C5CFF',   # 亮蓝
    13: '#FF00FF',   # 亮品红
    14: '#00FFFF',   # 亮青
    15: '#FFFFFF',   # 白
}

# 默认前景色和背景色
_DEFAULT_FG = '#E5E5E5'
_DEFAULT_BG = '#1E1E1E'


def _fg_color(char):
    """获取字符的前景色"""
    if char.fg in _COLOR_MAP:
        return _COLOR_MAP[char.fg]
    return _DEFAULT_FG


def _bg_color(char):
    """获取字符的背景色"""
    if char.bg in _COLOR_MAP:
        return _COLOR_MAP[char.bg]
    return _DEFAULT_BG


class TerminalEdit(QtWidgets.QPlainTextEdit):
    """终端控件（pyte + QPlainTextEdit）
    """
    # 按键发送信号
    key_sent = QtCore.pyqtSignal(str)
    # 粘贴发送信号
    paste_sent = QtCore.pyqtSignal(str)

    def __init__(self, parent=None, cols=120, rows=40):
        super().__init__(parent)

        # pyte 虚拟屏幕和流解析器
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.ByteStream(self._screen)

        # 终端尺寸
        self._cols = cols
        self._rows = rows

        # 样式
        self.setReadOnly(True)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        font = QtGui.QFont("Consolas", 12)
        font.setStyleHint(QtGui.QFont.Monospace)
        self.setFont(font)
        self.setStyleSheet(f"QPlainTextEdit {{ background-color: {_DEFAULT_BG}; color: {_DEFAULT_FG}; }}")

        # 隐藏光标（我们自己画闪烁光标）
        self.setCursorWidth(0)

        # 终端模式标志
        self._terminal_mode = False

        # 光标闪烁定时器
        self._cursor_visible = True
        self._cursor_timer = QtCore.QTimer(self)
        self._cursor_timer.setInterval(500)
        self._cursor_timer.timeout.connect(self._on_cursor_blink)
        self._cursor_timer.start()

        # 内容变化标记，避免重复渲染
        self._dirty = True
        self._pending_data = b''

        # 等宽字符宽度缓存
        self._char_width = None

    def set_terminal_mode(self, enabled):
        """切换终端模式"""
        self._terminal_mode = enabled
        self.setReadOnly(not enabled)
        if enabled:
            self.setFocus()

    # ---- 按键处理 ----

    def keyPressEvent(self, event):
        if not self._terminal_mode:
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()

        # Ctrl+C
        if key == QtCore.Qt.Key.Key_C and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x03')
            event.accept()
            return

        # Ctrl+V 粘贴
        if key == QtCore.Qt.Key.Key_V and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            clipboard = QtWidgets.QApplication.clipboard()
            text = clipboard.text()
            if text:
                text = text.replace('\r\n', '\r').replace('\n', '\r')
                self.paste_sent.emit(text)
            event.accept()
            return

        # 回车
        if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            self.key_sent.emit('\r')
            event.accept()
            return

        # 退格
        if key == QtCore.Qt.Key.Key_Backspace:
            self.key_sent.emit('\x08')
            event.accept()
            return

        # Delete
        if key == QtCore.Qt.Key.Key_Delete:
            self.key_sent.emit('\x1b[3~')
            event.accept()
            return

        # Home / End
        if key == QtCore.Qt.Key.Key_Home:
            self.key_sent.emit('\x1b[H')
            event.accept()
            return
        if key == QtCore.Qt.Key.Key_End:
            self.key_sent.emit('\x1b[F')
            event.accept()
            return

        # 方向键
        if key == QtCore.Qt.Key.Key_Up:
            self.key_sent.emit('\x1b[A')
            event.accept()
            return
        if key == QtCore.Qt.Key.Key_Down:
            self.key_sent.emit('\x1b[B')
            event.accept()
            return
        if key == QtCore.Qt.Key.Key_Left:
            self.key_sent.emit('\x1b[D')
            event.accept()
            return
        if key == QtCore.Qt.Key.Key_Right:
            self.key_sent.emit('\x1b[C')
            event.accept()
            return

        # Tab
        if key == QtCore.Qt.Key.Key_Tab:
            self.key_sent.emit('\t')
            event.accept()
            return

        # Esc
        if key == QtCore.Qt.Key.Key_Escape:
            self.key_sent.emit('\x1b')
            event.accept()
            return

        # Ctrl+L 清屏
        if key == QtCore.Qt.Key.Key_L and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x0c')
            event.accept()
            return

        # Ctrl+D EOF
        if key == QtCore.Qt.Key.Key_D and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x04')
            event.accept()
            return

        # Ctrl+A 行首
        if key == QtCore.Qt.Key.Key_A and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x01')
            event.accept()
            return

        # Ctrl+E 行尾
        if key == QtCore.Qt.Key.Key_E and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x05')
            event.accept()
            return

        # Ctrl+U 删除整行
        if key == QtCore.Qt.Key.Key_U and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x15')
            event.accept()
            return

        # 普通可打印字符
        text = event.text()
        if text and text.isprintable():
            self.key_sent.emit(text)
            event.accept()
            return

        super().keyPressEvent(event)

    # ---- 输出处理 ----

    def append_output(self, text):
        """接收服务器输出（字符串或字节），喂给 pyte 然后重绘"""
        if isinstance(text, str):
            data = text.encode('utf-8', errors='replace')
        else:
            data = text

        if not data:
            return

        # 喂给 pyte
        try:
            self._stream.feed(data)
        except Exception:
            pass

        self._dirty = True
        # 用定时器延迟一帧渲染，避免高频输出时重复渲染
        QtCore.QTimer.singleShot(0, self._render_screen)

    def _render_screen(self):
        """把 pyte 的虚拟屏幕渲染到 QPlainTextEdit"""
        if not self._dirty:
            return
        self._dirty = False

        screen = self._screen
        cursor_y = screen.cursor.y
        cursor_x = screen.cursor.x

        # 获取文档的 text cursor
        doc = self.document()
        cursor = QtGui.QTextCursor(doc)
        cursor.select(cursor.SelectionType.Document)
        cursor.removeSelectedText()

        # 默认格式
        default_format = QtGui.QTextCharFormat()
        default_format.setFontFamily("Consolas")
        default_format.setFontPointSize(12)
        default_format.setForeground(QtGui.QColor(_DEFAULT_FG))
        default_format.setBackground(QtGui.QColor(_DEFAULT_BG))

        # 逐行渲染
        for y in range(screen.lines):
            line = screen.buffer[y]
            x = 0
            while x < screen.columns:
                char = line[x]
                # 收集连续相同格式的字符（批量渲染，提升性能）
                fg = _fg_color(char)
                bg = _bg_color(char)
                bold = char.bold
                chars = []

                while x < screen.columns:
                    c = line[x]
                    if _fg_color(c) != fg or _bg_color(c) != bg or c.bold != bold:
                        break
                    # 跳过空字符（data 为空）
                    if not c.data:
                        x += 1
                        continue
                    # 宽字符判断（用 wcwidth）
                    w = wcwidth(c.data) if c.data else 1
                    if w <= 0:
                        w = 1
                    chars.append(c.data)
                    x += w

                if chars:
                    text = ''.join(chars)
                    fmt = QtGui.QTextCharFormat()
                    fmt.setFontFamily("Consolas")
                    fmt.setFontPointSize(12)
                    fmt.setForeground(QtGui.QColor(fg))
                    fmt.setBackground(QtGui.QColor(bg))
                    if bold:
                        fmt.setFontWeight(QtGui.QFont.Bold)
                    cursor.setCharFormat(fmt)
                    cursor.insertText(text)

            # 行末加换行
            if y < screen.lines - 1:
                cursor.setCharFormat(default_format)
                cursor.insertText('\n')

        # 光标渲染：在光标位置画一个反向色块（闪烁）
        if self._cursor_visible and self._terminal_mode:
            # 找到光标所在行位置
            block = doc.findBlockByNumber(min(cursor_y, screen.lines - 1))
            if block.isValid():
                cursor_pos = block.position() + min(cursor_x, screen.columns - 1)
                cursor = QtGui.QTextCursor(doc)
                cursor.setPosition(cursor_pos)
                if cursor.position() < doc.characterCount() - 1:
                    cursor.movePosition(cursor.MoveOperation.Right, cursor.MoveMode.KeepAnchor, 1)
                    fmt = cursor.charFormat()
                    # 反色
                    old_fg = fmt.foreground().color()
                    old_bg = fmt.background().color()
                    fmt.setForeground(old_bg)
                    fmt.setBackground(old_fg)
                    cursor.setCharFormat(fmt)

        # 滚到底部
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _on_cursor_blink(self):
        """光标闪烁"""
        if not self._terminal_mode:
            return
        self._cursor_visible = not self._cursor_visible
        self._dirty = True
        QtCore.QTimer.singleShot(0, self._render_screen)

    # ---- 兼容旧接口 ----

    def clear_terminal(self):
        """清空终端"""
        self._screen.reset()
        self._dirty = True
        self._render_screen()

    def append_info_line(self, text, color='#888888'):
        """追加本地信息行（灰色提示）"""
        # 模拟终端输出：换行 + 文本 + 换行
        self.append_output(f'\r\n\x1b[90m{text}\x1b[0m\r\n')
