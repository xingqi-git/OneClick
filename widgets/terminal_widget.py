"""
终端控件：基于 pyte HistoryScreen + QPlainTextEdit 渲染（高性能增量版）
- 历史行只追加，不重绘（history.top 只增不减）
- 当前屏（几十行）每次重绘
- 16ms 节流，合并高频输出
"""
from PyQt5 import QtWidgets, QtCore, QtGui
import pyte
from pyte.screens import HistoryScreen
from wcwidth import wcwidth


# 颜色映射
_COLOR_MAP = {
    0:  '#000000', 1:  '#CD0000', 2:  '#00CD00', 3:  '#CDCD00',
    4:  '#0000EE', 5:  '#CD00CD', 6:  '#00CDCD', 7:  '#E5E5E5',
    8:  '#7F7F7F', 9:  '#FF0000', 10: '#00FF00', 11: '#FFFF00',
    12: '#5C5CFF', 13: '#FF00FF', 14: '#00FFFF', 15: '#FFFFFF',
}

_DEFAULT_FG = '#E5E5E5'
_DEFAULT_BG = '#1E1E1E'
_HISTORY_LINES = 2000
_RENDER_INTERVAL_MS = 16  # 渲染节流间隔（约 60fps）


def _fg_color(char):
    if char.fg in _COLOR_MAP:
        return _COLOR_MAP[char.fg]
    return _DEFAULT_FG


def _bg_color(char):
    if char.bg in _COLOR_MAP:
        return _COLOR_MAP[char.bg]
    return _DEFAULT_BG


def _default_char_format():
    fmt = QtGui.QTextCharFormat()
    fmt.setFontFamily("Consolas")
    fmt.setFontPointSize(12)
    fmt.setForeground(QtGui.QColor(_DEFAULT_FG))
    fmt.setBackground(QtGui.QColor(_DEFAULT_BG))
    return fmt


class TerminalEdit(QtWidgets.QPlainTextEdit):
    """终端控件（高性能增量渲染）"""
    key_sent = QtCore.pyqtSignal(str)
    paste_sent = QtCore.pyqtSignal(str)

    def __init__(self, parent=None, cols=120, rows=40):
        super().__init__(parent)

        self._screen = HistoryScreen(cols, rows, history=_HISTORY_LINES)
        self._stream = pyte.ByteStream(self._screen)

        self._cols = cols
        self._rows = rows

        # 样式
        self.setReadOnly(True)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        font = QtGui.QFont("Consolas", 12)
        font.setStyleHint(QtGui.QFont.Monospace)
        self.setFont(font)
        self.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {_DEFAULT_BG}; color: {_DEFAULT_FG}; }}"
        )
        self.setCursorWidth(0)

        self._terminal_mode = False

        # 光标闪烁
        self._cursor_visible = True
        self._cursor_timer = QtCore.QTimer(self)
        self._cursor_timer.setInterval(500)
        self._cursor_timer.timeout.connect(self._on_cursor_blink)
        self._cursor_timer.start()

        # 增量渲染状态
        self._rendered_history_count = 0  # 已渲染的历史行数
        self._default_fmt = _default_char_format()
        self._need_full_redraw = True  # 首次需要全量绘制

        # 渲染节流定时器
        self._render_pending = False
        self._render_timer = QtCore.QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(_RENDER_INTERVAL_MS)
        self._render_timer.timeout.connect(self._do_render)

        # 自动滚动
        self._auto_scroll = True
        self.verticalScrollBar().valueChanged.connect(self._on_scrollbar_changed)

    def set_terminal_mode(self, enabled):
        self._terminal_mode = enabled
        self.setReadOnly(not enabled)
        if enabled:
            self.setFocus()

    # ---- 滚动 ----

    def _on_scrollbar_changed(self, value):
        sb = self.verticalScrollBar()
        self._auto_scroll = (value >= sb.maximum() - 2)

    def _scroll_to_bottom(self):
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ---- 按键 ----

    def keyPressEvent(self, event):
        if not self._terminal_mode:
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()

        # Shift+PageUp / Shift+PageDown：滚动历史
        if key == QtCore.Qt.Key_PageUp and modifiers & QtCore.Qt.ShiftModifier:
            sb = self.verticalScrollBar()
            sb.setValue(sb.value() - sb.pageStep())
            event.accept()
            return
        if key == QtCore.Qt.Key_PageDown and modifiers & QtCore.Qt.ShiftModifier:
            sb = self.verticalScrollBar()
            sb.setValue(sb.value() + sb.pageStep())
            event.accept()
            return

        self._auto_scroll = True

        # Ctrl+C
        if key == QtCore.Qt.Key_C and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x03')
            event.accept()
            return
        # Ctrl+V
        if key == QtCore.Qt.Key_V and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            text = QtWidgets.QApplication.clipboard().text()
            if text:
                text = text.replace('\r\n', '\r').replace('\n', '\r')
                self.paste_sent.emit(text)
            event.accept()
            return
        # 回车
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.key_sent.emit('\r')
            event.accept()
            return
        # 退格
        if key == QtCore.Qt.Key_Backspace:
            self.key_sent.emit('\x08')
            event.accept()
            return
        # Delete
        if key == QtCore.Qt.Key_Delete:
            self.key_sent.emit('\x1b[3~')
            event.accept()
            return
        # Home / End
        if key == QtCore.Qt.Key_Home:
            self.key_sent.emit('\x1b[H')
            event.accept()
            return
        if key == QtCore.Qt.Key_End:
            self.key_sent.emit('\x1b[F')
            event.accept()
            return
        # 方向键
        if key == QtCore.Qt.Key_Up:
            self.key_sent.emit('\x1b[A')
            event.accept()
            return
        if key == QtCore.Qt.Key_Down:
            self.key_sent.emit('\x1b[B')
            event.accept()
            return
        if key == QtCore.Qt.Key_Left:
            self.key_sent.emit('\x1b[D')
            event.accept()
            return
        if key == QtCore.Qt.Key_Right:
            self.key_sent.emit('\x1b[C')
            event.accept()
            return
        # Tab
        if key == QtCore.Qt.Key_Tab:
            self.key_sent.emit('\t')
            event.accept()
            return
        # Esc
        if key == QtCore.Qt.Key_Escape:
            self.key_sent.emit('\x1b')
            event.accept()
            return
        # Ctrl+L 清屏
        if key == QtCore.Qt.Key_L and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x0c')
            event.accept()
            return
        # Ctrl+D
        if key == QtCore.Qt.Key_D and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x04')
            event.accept()
            return
        # Ctrl+A
        if key == QtCore.Qt.Key_A and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x01')
            event.accept()
            return
        # Ctrl+E
        if key == QtCore.Qt.Key_E and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x05')
            event.accept()
            return
        # Ctrl+U
        if key == QtCore.Qt.Key_U and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.key_sent.emit('\x15')
            event.accept()
            return

        text = event.text()
        if text and text.isprintable():
            self.key_sent.emit(text)
            event.accept()
            return

        super().keyPressEvent(event)

    def wheelEvent(self, event):
        super().wheelEvent(event)

    # ---- 输出 ----

    def append_output(self, text):
        """接收服务器输出（节流渲染）"""
        if isinstance(text, str):
            data = text.encode('utf-8', errors='replace')
        else:
            data = text

        if not data:
            return

        try:
            self._stream.feed(data)
        except Exception:
            pass

        # 触发节流渲染
        if not self._render_pending:
            self._render_pending = True
            self._render_timer.start()

    def _render_line_into(self, cursor, line, cols):
        """把一行字符渲染到 cursor 位置（返回 cursor 便于链式调用）"""
        x = 0
        while x < cols:
            char = line[x]
            fg = _fg_color(char)
            bg = _bg_color(char)
            bold = char.bold
            chars = []

            while x < cols:
                c = line[x]
                if _fg_color(c) != fg or _bg_color(c) != bg or c.bold != bold:
                    break
                if not c.data:
                    x += 1
                    continue
                w = wcwidth(c.data) if c.data else 1
                if w <= 0:
                    w = 1
                chars.append(c.data)
                x += w

            if chars:
                fmt = QtGui.QTextCharFormat()
                fmt.setFontFamily("Consolas")
                fmt.setFontPointSize(12)
                fmt.setForeground(QtGui.QColor(fg))
                fmt.setBackground(QtGui.QColor(bg))
                if bold:
                    fmt.setFontWeight(QtGui.QFont.Bold)
                cursor.setCharFormat(fmt)
                cursor.insertText(''.join(chars))

    def _do_render(self):
        """执行渲染（增量方式）"""
        self._render_pending = False
        screen = self._screen

        # 历史行数
        history_count = len(screen.history.top) if hasattr(screen, 'history') else 0

        # 如果需要全量重绘（首次、清屏等）
        if self._need_full_redraw:
            self._full_redraw(screen, history_count)
            self._need_full_redraw = False
            self._rendered_history_count = history_count
            return

        doc = self.document()
        cursor = QtGui.QTextCursor(doc)

        # ---- 追加新增的历史行 ----
        if history_count > self._rendered_history_count:
            # 移到文档末尾
            cursor.movePosition(cursor.MoveOperation.End)
            # 补个换行（如果当前屏之前没换行的话，先换行再追加历史）
            # 实际上历史行都是从当前屏滚出去的，所以我们用另一种方式：
            # 把当前屏内容删掉，追加历史行，再重新画当前屏
            # 这个策略更简单，因为 history 增长意味着屏幕滚了一行
            pass  # 见下方统一处理

        # ---- 重新绘制当前屏区域 ----
        # 当前屏在文档中的起始行号 = 已渲染历史行数
        # 每次输出可能改变当前屏的任何行，所以当前屏要全重绘
        # 但历史行（history.top）只增不减，历史部分不用重绘

        # 策略：删除从 history 起始行到末尾的所有内容，重新追加当前屏
        # 历史行不动

        # 找到第 rendered_history_count 行的起始位置
        if history_count >= self._rendered_history_count:
            # 历史行增长了，有新行滚入 history
            # 新增的历史行数量
            new_hist_lines = history_count - self._rendered_history_count
            if new_hist_lines > 0:
                # 从 history.top 中取新增的行
                new_lines = list(screen.history.top)[-new_hist_lines:]
                # 移到文档末尾，追加新增历史行
                cursor.movePosition(cursor.MoveOperation.End)
                for hist_line in new_lines:
                    self._render_line_into(cursor, hist_line, screen.columns)
                    cursor.setCharFormat(self._default_fmt)
                    cursor.insertText('\n')
                self._rendered_history_count = history_count

        # 现在重绘当前屏：
        # 当前屏在文档中的位置 = rendered_history_count 行 到 rendered_history_count + rows - 1 行
        # 删除这些行，重新画

        # 找到第 rendered_history_count 行的开头
        block = doc.findBlockByNumber(self._rendered_history_count)
        if block.isValid():
            cursor = QtGui.QTextCursor(doc)
            cursor.setPosition(block.position())
            # 选到文档末尾
            cursor.movePosition(cursor.MoveOperation.End, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        else:
            # 找不到就直接移到末尾
            cursor = QtGui.QTextCursor(doc)
            cursor.movePosition(cursor.MoveOperation.End)

        # 重绘当前屏
        for y in range(screen.lines):
            line = screen.buffer[y]
            self._render_line_into(cursor, line, screen.columns)
            if y < screen.lines - 1:
                cursor.setCharFormat(self._default_fmt)
                cursor.insertText('\n')

        # 光标渲染
        if self._cursor_visible and self._terminal_mode and self._auto_scroll:
            abs_line = self._rendered_history_count + min(screen.cursor.y, screen.lines - 1)
            block = doc.findBlockByNumber(abs_line)
            if block.isValid():
                cursor_pos = block.position() + min(screen.cursor.x, screen.columns - 1)
                cursor = QtGui.QTextCursor(doc)
                cursor.setPosition(cursor_pos)
                if cursor.position() < doc.characterCount() - 1:
                    cursor.movePosition(cursor.MoveOperation.Right, cursor.MoveMode.KeepAnchor, 1)
                    fmt = cursor.charFormat()
                    old_fg = fmt.foreground().color()
                    old_bg = fmt.background().color()
                    fmt.setForeground(old_bg)
                    fmt.setBackground(old_fg)
                    cursor.setCharFormat(fmt)

        if self._auto_scroll:
            self._scroll_to_bottom()

    def _full_redraw(self, screen, history_count):
        """全量重绘（首次或清屏后）"""
        doc = self.document()
        cursor = QtGui.QTextCursor(doc)
        cursor.select(cursor.SelectionType.Document)
        cursor.removeSelectedText()

        # 历史行
        if history_count > 0:
            for hist_line in screen.history.top:
                self._render_line_into(cursor, hist_line, screen.columns)
                cursor.setCharFormat(self._default_fmt)
                cursor.insertText('\n')

        # 当前屏
        for y in range(screen.lines):
            line = screen.buffer[y]
            self._render_line_into(cursor, line, screen.columns)
            if y < screen.lines - 1:
                cursor.setCharFormat(self._default_fmt)
                cursor.insertText('\n')

        if self._auto_scroll:
            self._scroll_to_bottom()

    def _on_cursor_blink(self):
        if not self._terminal_mode:
            return
        self._cursor_visible = not self._cursor_visible
        if not self._render_pending:
            self._render_pending = True
            self._render_timer.start()

    # ---- 外部接口 ----

    def clear_terminal(self):
        """清空终端"""
        self._screen.reset()
        self._rendered_history_count = 0
        self._need_full_redraw = True
        self._render_pending = True
        self._render_timer.start()

    def append_info_line(self, text, color='#888888'):
        """追加本地信息行"""
        self.append_output(f'\r\n\x1b[90m{text}\x1b[0m\r\n')
