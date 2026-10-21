"""
终端控件：pyte HistoryScreen + QPainter 自绘版（QAbstractScrollArea）
- 完全抛弃 QPlainTextEdit，直接用 QPainter 渲染，性能更高、显示更准确
- 自带滚动条，历史记录与终端屏幕无缝衔接
- 支持 256 色、真彩色、粗体、反色
- 文本选中、复制、粘贴
- 输入法（IME）正确处理
- 16ms 渲染节流，约 60fps
"""
from PyQt5 import QtWidgets, QtCore, QtGui


# ---- 256 色 + 默认前景背景 ----

def _color_256(n):
    """xterm 256 色表"""
    if n < 16:
        # 标准 16 色（用更柔和的现代配色）
        palette = [
            '#1E1E1E', '#CD3131', '#0DBC79', '#E5E510',
            '#2472C8', '#BC3FBC', '#11A8CD', '#E5E5E5',
            '#666666', '#F14C4C', '#23D18B', '#F5F543',
            '#3B8EEA', '#D670D6', '#29B8DB', '#FFFFFF',
        ]
        return palette[n]
    if n < 232:
        # 6x6x6 立方体
        n -= 16
        r = n // 36
        g = (n // 6) % 6
        b = n % 6
        def _v(v):
            return 0 if v == 0 else v * 40 + 55
        return '#{:02X}{:02X}{:02X}'.format(_v(r), _v(g), _v(b))
    # 灰度 232-255
    n -= 232
    gray = 8 + n * 10
    return '#{:02X}{:02X}{:02X}'.format(gray, gray, gray)


_DEFAULT_FG = '#E5E5E5'
_DEFAULT_BG = '#1E1E1E'
_HISTORY_LINES = 2000
_RENDER_INTERVAL_MS = 16  # 约 60fps
# 字体优先级：优先选"中文宽度/英文宽度"恰好等于 2 的等宽字体，确保中文对齐不偏移
_FONT_CANDIDATES = [
    'Source Code Pro',      # 开源等宽，完美2:1，美观
    'DejaVu Sans Mono',     # 开源等宽，完美2:1
    'Consolas',             # Windows 默认等宽，中文1.78倍（最不完美但最常见）
]
_FONT_SIZE = 12


class TerminalWidget(QtWidgets.QAbstractScrollArea):
    """自绘终端控件（pyte + QPainter）

    对外接口与旧版 TerminalEdit 保持兼容：
    - key_sent / paste_sent 信号
    - set_terminal_mode(enabled)
    - append_output(text)
    - clear_terminal()
    - append_info_line(text, color)
    """
    key_sent = QtCore.pyqtSignal(str)
    paste_sent = QtCore.pyqtSignal(str)

    def __init__(self, parent=None, cols=120, rows=40):
        super().__init__(parent)

        self._cols = cols
        self._rows = rows
        self._screen = None  # pyte HistoryScreen，延迟创建
        self._stream = None  # pyte ByteStream，延迟创建
        self._wcwidth = None

        self._terminal_mode = False

        # 字体 & 度量（延迟计算，等控件 show 出来后再 init）
        self._font = self._pick_best_font()
        self._font.setStyleHint(QtGui.QFont.Monospace)
        self._char_width = 0
        self._char_height = 0
        self._char_ascent = 0
        self._calc_font_metrics()

        # 视口背景
        self.viewport().setAutoFillBackground(True)
        pal = self.viewport().palette()
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(_DEFAULT_BG))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor(_DEFAULT_FG))
        self.viewport().setPalette(pal)
        self.viewport().setMouseTracking(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        # 光标闪烁
        self._cursor_visible = True
        self._cursor_timer = QtCore.QTimer(self)
        self._cursor_timer.setInterval(500)
        self._cursor_timer.timeout.connect(self._on_cursor_blink)
        self._cursor_timer.start()

        # 渲染节流
        self._render_pending = False
        self._render_timer = QtCore.QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(_RENDER_INTERVAL_MS)
        self._render_timer.timeout.connect(self._do_render)

        # 自动滚动
        self._auto_scroll = True
        self.verticalScrollBar().valueChanged.connect(self._on_scrollbar_changed)

        # 文本选中
        self._selecting = False
        self._drag_start = None  # 鼠标按下起点，拖动后才进入选中状态
        self._sel_start = None  # (row, col)  绝对行号（历史+当前屏）
        self._sel_end = None    # (row, col)

        # 双击后的那次 release 不要清空选区
        self._suppress_release_clear = False

        # 滚动偏移（行号，向上滚为正）
        self._scroll_offset = 0

        # 聚焦策略
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)

        # 初始化大小
        self.setMinimumSize(self._char_width * 40, self._char_height * 10)

    # ===================== 初始化 =====================

    def _ensure_pyte(self):
        if self._screen is not None:
            return
        import pyte
        from pyte.screens import HistoryScreen
        from wcwidth import wcwidth
        self._wcwidth = wcwidth
        self._screen = HistoryScreen(self._cols, self._rows, history=_HISTORY_LINES)
        self._stream = pyte.ByteStream(self._screen)

    @staticmethod
    def _pick_best_font():
        """从候选字体中选一个"中文宽度/英文宽度"最接近 2:1 的等宽字体，保证中文对齐"""
        best_font = None
        best_ratio = 0
        best_diff = 999.0
        for family in _FONT_CANDIDATES:
            font = QtGui.QFont(family, _FONT_SIZE)
            font.setStyleHint(QtGui.QFont.Monospace)
            fm = QtGui.QFontMetrics(font)
            en_w = fm.horizontalAdvance('M')
            cn_w = fm.horizontalAdvance('汉')
            if en_w <= 0:
                continue
            ratio = cn_w / en_w
            diff = abs(ratio - 2.0)
            if diff < best_diff:
                best_diff = diff
                best_ratio = ratio
                best_font = font
        if best_font is None:
            best_font = QtGui.QFont(_FONT_CANDIDATES[-1], _FONT_SIZE)
            best_font.setStyleHint(QtGui.QFont.Monospace)
        return best_font

    def _calc_font_metrics(self):
        fm = QtGui.QFontMetrics(self._font)
        en_w = fm.horizontalAdvance('M')
        cn_w = fm.horizontalAdvance('汉')
        # 终端格子宽度：英文占 1 格，中文占 2 格。
        # 取 max(英文宽, 中文宽/2 向上取整)，保证中文 2 格能完整放下，英文等宽。
        if cn_w > en_w:
            half_cn = (cn_w + 1) // 2
            self._char_width = max(en_w, half_cn)
        else:
            self._char_width = en_w
        self._char_height = fm.height()
        self._char_ascent = fm.ascent()

    # ===================== 对外接口 =====================

    def set_terminal_mode(self, enabled):
        if enabled:
            self._ensure_pyte()
            self._update_scrollbar()
            self._scroll_to_bottom()
        self._terminal_mode = enabled
        if enabled:
            self.setFocus()
        self.viewport().update()

    def append_output(self, text):
        """接收服务器输出（节流渲染）"""
        self._ensure_pyte()
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

    def clear_terminal(self):
        """清空终端"""
        if self._screen is not None:
            self._screen.reset()
        self._sel_start = None
        self._sel_end = None
        self._scroll_offset = 0
        self._auto_scroll = True
        self._update_scrollbar()
        if not self._render_pending:
            self._render_pending = True
            self._render_timer.start()

    def append_info_line(self, text, color='#888888'):
        """追加本地信息行"""
        self.append_output(f'\r\n\x1b[90m{text}\x1b[0m\r\n')

    # ===================== 滚动 =====================

    def _on_scrollbar_changed(self, value):
        sb = self.verticalScrollBar()
        self._scroll_offset = value
        self._auto_scroll = (value >= sb.maximum() - 1)
        self.viewport().update()

    def _update_scrollbar(self):
        """根据屏幕总行数更新滚动条范围"""
        if self._screen is None:
            return
        total_lines = self._total_lines()
        visible = self._visible_rows()
        sb = self.verticalScrollBar()
        sb.setMinimum(0)
        if total_lines <= visible:
            sb.setMaximum(0)
            self._scroll_offset = 0
        else:
            sb.setMaximum(total_lines - visible)
            sb.setPageStep(visible)
        if self._auto_scroll:
            sb.setValue(sb.maximum())
            self._scroll_offset = sb.maximum()

    def _scroll_to_bottom(self):
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _total_lines(self):
        """历史行 + 当前屏行数"""
        if self._screen is None:
            return 0
        hist = len(self._screen.history.top) if hasattr(self._screen, 'history') else 0
        return hist + self._screen.lines

    def _visible_rows(self):
        """视口能显示多少行"""
        h = self.viewport().height()
        if self._char_height <= 0:
            return 24
        return max(1, h // self._char_height)

    # ===================== 渲染 =====================

    def _do_render(self):
        self._render_pending = False
        if self._screen is None:
            return
        self._update_scrollbar()
        # 如果用户在选中文本，且自动跟随模式下，不更新选区
        self.viewport().update()

    def _on_cursor_blink(self):
        if not self._terminal_mode:
            return
        self._cursor_visible = not self._cursor_visible
        # 只更新光标所在行
        if self._screen is not None and self._auto_scroll and not self._selecting:
            self._update_cursor_line()
        else:
            self.viewport().update()

    def _update_cursor_line(self):
        """只刷新光标所在行的矩形区域（性能优化）"""
        if self._screen is None:
            self.viewport().update()
            return
        hist = len(self._screen.history.top) if hasattr(self._screen, 'history') else 0
        abs_row = hist + self._screen.cursor.y
        visible_rows = self._visible_rows()
        total = self._total_lines()
        top_row = max(0, total - visible_rows) if self._auto_scroll else self._scroll_offset
        rel = abs_row - top_row
        if 0 <= rel < visible_rows:
            y = rel * self._char_height
            self.viewport().update(0, y, self.viewport().width(), self._char_height)
        else:
            self.viewport().update()

    def paintEvent(self, event):
        if self._screen is None:
            # 还没初始化，画背景
            painter = QtGui.QPainter(self.viewport())
            painter.fillRect(event.rect(), QtGui.QColor(_DEFAULT_BG))
            return

        painter = QtGui.QPainter(self.viewport())
        painter.setFont(self._font)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)

        rect = event.rect()
        first_row = max(0, rect.top() // self._char_height)
        last_row = min(self._visible_rows() - 1, rect.bottom() // self._char_height)

        top_row = self._scroll_offset
        hist_count = len(self._screen.history.top) if hasattr(self._screen, 'history') else 0

        for rel_row in range(first_row, last_row + 1):
            abs_row = top_row + rel_row
            y = rel_row * self._char_height
            # 背景先铺满
            painter.fillRect(0, y, self.viewport().width(), self._char_height,
                             QtGui.QColor(_DEFAULT_BG))

            line_buf = self._get_line(abs_row, hist_count)
            if line_buf is None:
                continue

            self._draw_line(painter, line_buf, abs_row, y, hist_count)

        # 画光标（只在终端模式 + 自动跟随 + 可见时）
        if (self._terminal_mode and self._cursor_visible and self._auto_scroll
                and self._screen is not None and not self._selecting):
            cursor_row = hist_count + self._screen.cursor.y
            cursor_col = self._screen.cursor.x
            cursor_rel = cursor_row - top_row
            if 0 <= cursor_rel < self._visible_rows():
                cy = cursor_rel * self._char_height
                cx = cursor_col * self._char_width
                # 光标：一个竖条
                painter.fillRect(cx, cy + 1, 2, self._char_height - 2,
                                 QtGui.QColor(_DEFAULT_FG))

    def _get_line(self, abs_row, hist_count):
        """获取绝对行号对应的 pyte line 对象"""
        if self._screen is None:
            return None
        if abs_row < hist_count:
            # 历史行
            hist = list(self._screen.history.top)
            if abs_row < len(hist):
                return hist[abs_row]
            return None
        else:
            # 当前屏
            idx = abs_row - hist_count
            if 0 <= idx < self._screen.lines:
                return self._screen.buffer[idx]
            return None

    def _draw_line(self, painter, line, abs_row, y, hist_count):
        """绘制单行（逐字符绘制，逻辑简单可靠）"""
        cols = self._screen.columns
        baseline = y + self._char_ascent
        fm = painter.fontMetrics()

        i = 0           # 字符索引
        col_pos = 0     # 当前视觉列号
        while i < cols and col_pos < cols:
            ch = line[i]
            data = ch.data

            # pyte 中宽字符（中文等）占两个 buffer 位置：字符 + 空占位符
            # 碰到空占位符直接跳过，不推进列号
            if data == '':
                i += 1
                continue

            w = self._wcwidth(data) if data else 1
            if w <= 0:
                w = 1

            # 计算选中状态
            is_selected = self._range_selected(abs_row, col_pos, col_pos + w)

            fg = self._resolve_fg(ch)
            bg = self._resolve_bg(ch)

            cell_width = w * self._char_width  # 格子总宽度
            draw_x = col_pos * self._char_width

            if ch.reverse or is_selected:
                if is_selected:
                    bg_color = QtGui.QColor('#264F78')  # VS Code 风格选中色
                    fg_color = QtGui.QColor(_DEFAULT_FG)
                else:
                    bg_color = QtGui.QColor(fg)
                    fg_color = QtGui.QColor(bg)
                # 背景铺满整个格子
                painter.fillRect(draw_x, y, cell_width, self._char_height, bg_color)
                # 文字（非英文等宽字符在格子内水平居中）
                if data:
                    painter.setPen(fg_color)
                    f = QtGui.QFont(self._font)
                    if ch.bold:
                        f.setBold(True)
                    painter.setFont(f)
                    text_w = fm.horizontalAdvance(data)
                    offset_x = max(0, (cell_width - text_w) // 2)
                    painter.drawText(draw_x + offset_x, baseline, data)
            else:
                # 正常文字
                if data and data != ' ':
                    painter.setPen(QtGui.QColor(fg))
                    f = QtGui.QFont(self._font)
                    if ch.bold:
                        f.setBold(True)
                    painter.setFont(f)
                    text_w = fm.horizontalAdvance(data)
                    # 等宽字符（宽度=格子宽度）直接画，非等宽（如中文）居中画
                    offset_x = max(0, (cell_width - text_w) // 2)
                    painter.drawText(draw_x + offset_x, baseline, data)

            i += 1
            col_pos += w

    def _resolve_fg(self, char):
        if char.fg == 'default':
            return _DEFAULT_FG
        if isinstance(char.fg, int):
            return _color_256(char.fg)
        # 真彩色 (256, R, G, B) 元组
        if isinstance(char.fg, (tuple, list)) and len(char.fg) >= 4:
            r, g, b = char.fg[1], char.fg[2], char.fg[3]
            return '#{:02X}{:02X}{:02X}'.format(r, g, b)
        return _DEFAULT_FG

    def _resolve_bg(self, char):
        if char.bg == 'default':
            return _DEFAULT_BG
        if isinstance(char.bg, int):
            return _color_256(char.bg)
        if isinstance(char.bg, (tuple, list)) and len(char.bg) >= 4:
            r, g, b = char.bg[1], char.bg[2], char.bg[3]
            return '#{:02X}{:02X}{:02X}'.format(r, g, b)
        return _DEFAULT_BG

    # ===================== 选中文本 =====================

    def _range_selected(self, row, col_start, col_end):
        """判断 [row, col_start:col_end] 是否在选区内"""
        if self._sel_start is None or self._sel_end is None:
            return False
        s_row, s_col = self._sel_start
        e_row, e_col = self._sel_end
        # 规范化
        if (s_row, s_col) > (e_row, e_col):
            s_row, e_row = e_row, s_row
            s_col, e_col = e_col, s_col

        if row < s_row or row > e_row:
            return False
        if s_row == e_row:
            return col_start < e_col and col_end > s_col
        if row == s_row:
            return col_end > s_col
        if row == e_row:
            return col_start < e_col
        return True  # 中间行全选

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        if self._screen is None:
            return
        row, col = self._pos_to_rowcol(event.pos())
        self._cursor_visible = True

        # 记录起点，不立刻进入选中状态（拖动超过阈值才算）
        self._drag_start = (row, col)
        self._selecting = False
        self._suppress_release_clear = False
        self.viewport().update()

    def mouseMoveEvent(self, event):
        if self._screen is None:
            return
        if self._drag_start is None:
            return
        row, col = self._pos_to_rowcol(event.pos())
        # 还没进入选中状态：看是否拖动了超过 2 个字符
        if not self._selecting:
            dr = abs(row - self._drag_start[0])
            dc = abs(col - self._drag_start[1])
            if dr == 0 and dc <= 2:
                return  # 还在微动范围内
            # 开始选中
            self._selecting = True
            self._sel_start = self._drag_start
        self._sel_end = (row, col)
        self.viewport().update()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        self._drag_start = None
        # 双击/三击后的 release：不清空选区
        if self._suppress_release_clear:
            self._suppress_release_clear = False
            self._selecting = False
            return
        # 如果没有真正进入选中状态（纯单击），清空选区
        if not self._selecting:
            if self._sel_start is not None or self._sel_end is not None:
                self._sel_start = None
                self._sel_end = None
                self.viewport().update()
            return
        self._selecting = False

    def mouseDoubleClickEvent(self, event):
        if self._screen is None:
            return
        if event.button() != QtCore.Qt.LeftButton:
            return
        row, col = self._pos_to_rowcol(event.pos())
        self._select_word_at(row, col)
        self._suppress_release_clear = True
        self._drag_start = None
        self._selecting = False
        self.viewport().update()

    def _select_word_at(self, row, col):
        """选中 (row, col) 位置处的单词（字母/数字/下划线）"""
        hist_count = len(self._screen.history.top) if hasattr(self._screen, 'history') else 0
        line = self._get_line(row, hist_count)
        if line is None:
            return

        cols = self._screen.columns
        cur_idx, cur_x = self._col_to_char_index(line, col)
        cur = line[cur_idx] if cur_idx < cols else None

        if not cur or not cur.data or not (cur.data.isalnum() or cur.data == '_'):
            self._sel_start = None
            self._sel_end = None
            return

        # 向左找起点
        start_idx = cur_idx
        start_x = cur_x
        while start_idx > 0:
            ch = line[start_idx - 1]
            if ch and ch.data and (ch.data.isalnum() or ch.data == '_'):
                w = self._wcwidth(ch.data)
                if w <= 0:
                    w = 1
                start_idx -= 1
                start_x -= w
            else:
                break

        # 向右找终点
        end_idx = cur_idx
        end_x = cur_x
        while end_idx < cols:
            ch = line[end_idx]
            if ch and ch.data and (ch.data.isalnum() or ch.data == '_'):
                w = self._wcwidth(ch.data)
                if w <= 0:
                    w = 1
                end_idx += 1
                end_x += w
            else:
                break

        if start_x >= end_x:
            self._sel_start = None
            self._sel_end = None
            return

        self._sel_start = (row, start_x)
        self._sel_end = (row, end_x)



    def _pos_to_rowcol(self, pos):
        """将视口坐标转为 (abs_row, col)"""
        row = self._scroll_offset + pos.y() // self._char_height
        col = pos.x() // self._char_width
        total = self._total_lines()
        row = max(0, min(row, max(0, total - 1)))
        if self._screen is not None:
            col = max(0, min(col, self._screen.columns - 1))
        return row, col

    def _col_to_char_index(self, line, col):
        """将视觉列号转为 line 数组的字符索引"""
        cols = self._screen.columns
        x = 0
        i = 0
        while i < cols and x < col:
            ch = line[i]
            # pyte 宽字符占位符（空字符串）不占视觉宽度，直接跳过
            if ch.data == '':
                i += 1
                continue
            w = self._wcwidth(ch.data)
            if w <= 0:
                w = 1
            if x + w > col:
                # 落在宽字符中间，取这个字符
                break
            x += w
            i += 1
        return i, x

    def _selected_text(self):
        """获取选中文本"""
        if self._sel_start is None or self._sel_end is None:
            return ''
        s_row, s_col = self._sel_start
        e_row, e_col = self._sel_end
        if (s_row, s_col) > (e_row, e_col):
            s_row, e_row = e_row, s_row
            s_col, e_col = e_col, s_col

        hist_count = len(self._screen.history.top) if hasattr(self._screen, 'history') else 0
        lines = []
        for r in range(s_row, e_row + 1):
            line = self._get_line(r, hist_count)
            if line is None:
                continue
            start_col = s_col if r == s_row else 0
            end_col = e_col if r == e_row else self._screen.columns
            chars = []
            x = 0
            i = 0
            cols = self._screen.columns
            while i < cols and x < end_col:
                ch = line[i]
                # pyte 宽字符占位符（空字符串）不占视觉宽度，直接跳过
                if ch.data == '':
                    i += 1
                    continue
                w = self._wcwidth(ch.data)
                if w <= 0:
                    w = 1
                if x >= start_col:
                    if ch.data:
                        chars.append(ch.data)
                x += w
                i += 1
            lines.append(''.join(chars))
        return '\n'.join(lines)

    # ===================== 右键菜单 =====================

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        has_sel = self._sel_start is not None and self._sel_end is not None and self._sel_start != self._sel_end

        act_copy = menu.addAction("复制")
        act_copy.setEnabled(has_sel)
        act_paste = menu.addAction("粘贴")
        act_select_all = menu.addAction("全选")

        action = menu.exec_(event.globalPos())
        if action is None:
            return
        if action == act_copy and has_sel:
            text = self._selected_text()
            if text:
                QtWidgets.QApplication.clipboard().setText(text)
        elif action == act_paste:
            text = QtWidgets.QApplication.clipboard().text()
            if text:
                text = text.replace('\r\n', '\r').replace('\n', '\r')
                self.paste_sent.emit(text)
        elif action == act_select_all:
            total = self._total_lines()
            if total > 0 and self._screen is not None:
                self._sel_start = (0, 0)
                self._sel_end = (total - 1, self._screen.columns)
                self.viewport().update()

    # ===================== 键盘输入 =====================

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
        # Shift+Insert 粘贴
        if key == QtCore.Qt.Key_Insert and modifiers & QtCore.Qt.ShiftModifier:
            text = QtWidgets.QApplication.clipboard().text()
            if text:
                text = text.replace('\r\n', '\r').replace('\n', '\r')
                self.paste_sent.emit(text)
            event.accept()
            return
        # Ctrl+Shift+C 复制
        if key == QtCore.Qt.Key_C and modifiers & QtCore.Qt.ShiftModifier \
                and modifiers & QtCore.Qt.ControlModifier:
            text = self._selected_text()
            if text:
                QtWidgets.QApplication.clipboard().setText(text)
            event.accept()
            return
        # Ctrl+Shift+V 粘贴
        if key == QtCore.Qt.Key_V and modifiers & QtCore.Qt.ShiftModifier \
                and modifiers & QtCore.Qt.ControlModifier:
            text = QtWidgets.QApplication.clipboard().text()
            if text:
                text = text.replace('\r\n', '\r').replace('\n', '\r')
                self.paste_sent.emit(text)
            event.accept()
            return

        self._auto_scroll = True
        self._scroll_to_bottom()
        self._cursor_visible = True

        # 控制键
        if key == QtCore.Qt.Key_C and modifiers & QtCore.Qt.ControlModifier:
            self.key_sent.emit('\x03')
            event.accept()
            return
        if key == QtCore.Qt.Key_V and modifiers & QtCore.Qt.ControlModifier:
            # Ctrl+V 在终端里是字面量 \x16，不是粘贴
            # 这里按传统终端行为发送 ^V
            self.key_sent.emit('\x16')
            event.accept()
            return
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.key_sent.emit('\r')
            event.accept()
            return
        if key == QtCore.Qt.Key_Backspace:
            self.key_sent.emit('\x7f')  # DEL，现代终端常用
            event.accept()
            return
        if key == QtCore.Qt.Key_Delete:
            self.key_sent.emit('\x1b[3~')
            event.accept()
            return
        if key == QtCore.Qt.Key_Home:
            self.key_sent.emit('\x1b[H')
            event.accept()
            return
        if key == QtCore.Qt.Key_End:
            self.key_sent.emit('\x1b[F')
            event.accept()
            return
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
        if key == QtCore.Qt.Key_Tab:
            self.key_sent.emit('\t')
            event.accept()
            return
        if key == QtCore.Qt.Key_Escape:
            self.key_sent.emit('\x1b')
            event.accept()
            return
        if key == QtCore.Qt.Key_L and modifiers & QtCore.Qt.ControlModifier:
            self.key_sent.emit('\x0c')
            event.accept()
            return
        if key == QtCore.Qt.Key_D and modifiers & QtCore.Qt.ControlModifier:
            self.key_sent.emit('\x04')
            event.accept()
            return
        if key == QtCore.Qt.Key_A and modifiers & QtCore.Qt.ControlModifier:
            self.key_sent.emit('\x01')
            event.accept()
            return
        if key == QtCore.Qt.Key_E and modifiers & QtCore.Qt.ControlModifier:
            self.key_sent.emit('\x05')
            event.accept()
            return
        if key == QtCore.Qt.Key_U and modifiers & QtCore.Qt.ControlModifier:
            self.key_sent.emit('\x15')
            event.accept()
            return
        if key == QtCore.Qt.Key_W and modifiers & QtCore.Qt.ControlModifier:
            self.key_sent.emit('\x17')
            event.accept()
            return
        if key == QtCore.Qt.Key_Z and modifiers & QtCore.Qt.ControlModifier:
            self.key_sent.emit('\x1a')
            event.accept()
            return
        # F1-F12 简单支持
        fkeys = {
            QtCore.Qt.Key_F1: '\x1bOP', QtCore.Qt.Key_F2: '\x1bOQ',
            QtCore.Qt.Key_F3: '\x1bOR', QtCore.Qt.Key_F4: '\x1bOS',
            QtCore.Qt.Key_F5: '\x1b[15~', QtCore.Qt.Key_F6: '\x1b[17~',
            QtCore.Qt.Key_F7: '\x1b[18~', QtCore.Qt.Key_F8: '\x1b[19~',
            QtCore.Qt.Key_F9: '\x1b[20~', QtCore.Qt.Key_F10: '\x1b[21~',
            QtCore.Qt.Key_F11: '\x1b[23~', QtCore.Qt.Key_F12: '\x1b[24~',
        }
        if key in fkeys:
            self.key_sent.emit(fkeys[key])
            event.accept()
            return

        # 可打印字符
        text = event.text()
        if text and not modifiers & QtCore.Qt.ControlModifier and not modifiers & QtCore.Qt.AltModifier:
            if text.isprintable():
                self.key_sent.emit(text)
                event.accept()
                return

        super().keyPressEvent(event)

    # ===================== 输入法 =====================

    def inputMethodEvent(self, event):
        if not self._terminal_mode:
            super().inputMethodEvent(event)
            return
        # 提交文本（已确认的中文/日文等）
        commit = event.commitString()
        if commit:
            self.key_sent.emit(commit)
            event.accept()
            return
        # 预编辑文本不显示，直接接受（终端模式下不显示候选字在终端内，由系统 IME 窗口显示）
        super().inputMethodEvent(event)

    def inputMethodQuery(self, query):
        # 告诉输入法控件的字体、位置等信息，确保候选窗口和光标对齐
        if query == QtCore.Qt.ImFont:
            return self._font
        if query == QtCore.Qt.ImCursorPosition:
            return 0
        if query == QtCore.Qt.ImSurroundingText:
            return ''
        if query == QtCore.Qt.ImCursorRectangle:
            # 返回当前光标在控件坐标中的矩形，输入法候选窗会对齐这里
            if self._screen is not None and self._terminal_mode:
                cursor_col = self._screen.cursor.x
                cursor_row = self._screen.cursor.y
                hist_count = len(self._screen.history.top) if hasattr(self._screen, 'history') else 0
                abs_row = hist_count + cursor_row
                rel_row = abs_row - self._scroll_offset
                if 0 <= rel_row < self._visible_rows():
                    x = cursor_col * self._char_width
                    y = rel_row * self._char_height
                    return QtCore.QRect(x, y, 2, self._char_height)
            return QtCore.QRect(0, 0, 2, self._char_height)
        return super().inputMethodQuery(query)

    # ===================== Tab 键拦截 =====================

    def focusNextPrevChild(self, next_):
        # 终端模式下拦截 Tab，不让它触发焦点切换
        if self._terminal_mode:
            return False
        return super().focusNextPrevChild(next_)

    # ===================== 滚轮 =====================

    def wheelEvent(self, event):
        if self._screen is None:
            return
        # 终端模式下，向上滚动发送鼠标滚轮序列给应用（如 vim）
        # 简化处理：直接用滚动条滚动
        sb = self.verticalScrollBar()
        old_val = sb.value()
        super().wheelEvent(event)
        if sb.value() < old_val:
            self._auto_scroll = False

    # ===================== 大小变化 =====================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scrollbar()
        # TODO: 可以通知远端 resize pty（需要改 SSH 层）
        self.viewport().update()


# 兼容旧类名
TerminalEdit = TerminalWidget
