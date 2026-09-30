"""自定义消息框模块

替代 tkinter.messagebox 和 tkinter.simpledialog，
所有弹窗居中在父窗口上，而不是屏幕中央。
"""

import tkinter as tk
from tkinter import ttk


# ---- 颜色常量，与应用主题保持一致 ----
CARD_BG = "#ffffff"
PRIMARY = "#2563eb"
TEXT_PRIMARY = "#1e293b"
TEXT_SECONDARY = "#64748b"
BORDER = "#e2e8f0"


# ======================== 消息对话框 ========================

class _MsgDialog(tk.Toplevel):
    """居中在父窗口上的消息对话框"""

    # 图标符号和颜色配置
    _TYPE_CONFIG = {
        "info":     {"symbol": "✔",  "color": "#16a34a", "buttons": ["确定"]},
        "warning":  {"symbol": "⚠",  "color": "#d97706", "buttons": ["确定"]},
        "error":    {"symbol": "✗",  "color": "#dc2626", "buttons": ["确定"]},
        "question": {"symbol": "?",  "color": "#2563eb", "buttons": ["是", "否"]},
    }

    def __init__(self, parent, title, message, dialog_type="info"):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=CARD_BG)

        config = self._TYPE_CONFIG.get(dialog_type, self._TYPE_CONFIG["info"])
        self.result = None

        # --- 内容区域 ---
        content = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 20))
        content.pack(fill="both", expand=True)

        msg_frame = ttk.Frame(content, style="Dialog.TFrame")
        msg_frame.pack(fill="x")

        tk.Label(msg_frame, text=config["symbol"],
                 font=("Microsoft YaHei UI", 28, "bold"),
                 fg=config["color"], bg=CARD_BG).pack(side="left", padx=(0, 16))

        tk.Label(msg_frame, text=message,
                 font=("Microsoft YaHei UI", 10),
                 wraplength=380, justify="left",
                 bg=CARD_BG, fg=TEXT_PRIMARY,
                 anchor="w").pack(side="left", fill="x", expand=True)

        # --- 按钮区域 ---
        btn_frame = ttk.Frame(content, style="Dialog.TFrame")
        btn_frame.pack(fill="x", pady=(20, 0))
        btn_inner = ttk.Frame(btn_frame, style="Dialog.TFrame")
        btn_inner.pack(expand=True)

        default_btn = None
        for btn_text in config["buttons"]:
            btn_style = "Primary.TButton" if btn_text in ("确定", "是") else "Danger.TButton"
            btn = ttk.Button(btn_inner, text=btn_text, style=btn_style, width=10,
                             command=lambda r=btn_text: self._done(r))
            btn.pack(side="left", padx=6)
            if btn_text in ("确定", "是"):
                default_btn = btn

        # --- 居中到父窗口 ---
        self.update_idletasks()
        self._center_over(parent)

        # --- 模态 & 焦点 ---
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: self._done(config["buttons"][-1]))
        if default_btn:
            default_btn.focus_set()
        else:
            self.focus_force()

        # 键盘快捷键
        self.bind("<Return>", lambda e: self._done(config["buttons"][0]))
        self.bind("<Escape>", lambda e: self._done(config["buttons"][-1]))

    def _center_over(self, parent):
        """将对话框居中到父窗口上"""
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()

        dw = self.winfo_width()
        dh = self.winfo_height()

        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2

        self.geometry(f"+{x}+{y}")

    def _done(self, result):
        self.result = result
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


# ======================== 加载/进度对话框 ========================

class LoadingDialog(tk.Toplevel):
    """居中在父窗口上的加载/进度对话框，可程序化关闭"""

    def __init__(self, parent, title="处理中", message="请稍候..."):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)

        # 去掉窗口关闭按钮，防止用户中途关闭
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self.configure(bg=CARD_BG)

        content = ttk.Frame(self, style="Dialog.TFrame", padding=(28, 22))
        content.pack(fill="both", expand=True)

        # 旋转动画图标
        self._spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_idx = 0
        self._spinner_label = tk.Label(content, text=self._spinner_chars[0],
                                       font=("Consolas", 22), fg=PRIMARY, bg=CARD_BG)
        self._spinner_label.pack(side="left", padx=(0, 16))

        # 右侧文字区域
        text_frame = ttk.Frame(content, style="Dialog.TFrame")
        text_frame.pack(side="left", fill="x", expand=True)

        self._msg_var = tk.StringVar(value=message)
        ttk.Label(text_frame, textvariable=self._msg_var,
                  style="Dialog.TLabel",
                  wraplength=360, justify="left", anchor="w").pack(fill="x")

        # 进度条
        self._progress = ttk.Progressbar(text_frame, mode="determinate", length=360)
        self._progress.pack(fill="x", pady=(10, 0))

        self._progress_var = tk.StringVar(value="")
        self._progress_label = ttk.Label(text_frame, textvariable=self._progress_var,
                                         style="Muted.TLabel")
        self._progress_label.pack(fill="x", pady=(4, 0))

        # 居中到父窗口
        self.update_idletasks()
        self._center_over(parent)

        # 启动旋转动画
        self._animate_spinner()

    def _animate_spinner(self):
        """旋转动画"""
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_chars)
        self._spinner_label.config(text=self._spinner_chars[self._spinner_idx])
        self._after_id = self.after(80, self._animate_spinner)

    def _center_over(self, parent):
        """将对话框居中到父窗口上"""
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()

        dw = self.winfo_width()
        dh = self.winfo_height()

        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2

        self.geometry(f"+{x}+{y}")

    def update_message(self, message):
        """更新主消息文字"""
        self._msg_var.set(message)

    def update_progress(self, current, total, detail=""):
        """更新进度条和进度文字"""
        if total > 0:
            self._progress["maximum"] = total
            self._progress["value"] = current
            pct = int(current / total * 100)
            self._progress_var.set(f"{current} / {total}  ({pct}%)  {detail}")
        else:
            self._progress_var.set(detail)

    def close(self):
        """关闭对话框"""
        if hasattr(self, "_after_id"):
            self.after_cancel(self._after_id)
        self.destroy()


# ======================== 输入对话框 ========================

class _InputDialog(tk.Toplevel):
    """居中在父窗口上的输入对话框，替代 simpledialog.askstring"""

    def __init__(self, parent, title, prompt, initialvalue=""):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)

        self.result = None

        self.configure(bg=CARD_BG)

        content = ttk.Frame(self, style="Dialog.TFrame", padding=(24, 20))
        content.pack(fill="both", expand=True)

        ttk.Label(content, text=prompt,
                  style="Dialog.TLabel").pack(anchor="w", pady=(0, 10))

        self._entry_var = tk.StringVar(value=initialvalue)
        entry = ttk.Entry(content, textvariable=self._entry_var,
                          width=40)
        entry.pack(fill="x", pady=(0, 16))
        entry.focus_set()

        btn_frame = ttk.Frame(content, style="Dialog.TFrame")
        btn_frame.pack(fill="x")
        btn_inner = ttk.Frame(btn_frame, style="Dialog.TFrame")
        btn_inner.pack(expand=True)

        ttk.Button(btn_inner, text="确定", style="Primary.TButton", width=10,
                   command=self._on_ok).pack(side="left", padx=6)
        ttk.Button(btn_inner, text="取消", style="Danger.TButton", width=10,
                   command=self._on_cancel).pack(side="left", padx=6)

        self.update_idletasks()
        self._center_over(parent)

        self.grab_set()
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _center_over(self, parent):
        """将对话框居中到父窗口上"""
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()

        dw = self.winfo_width()
        dh = self.winfo_height()

        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2

        self.geometry(f"+{x}+{y}")

    def _on_ok(self):
        self.result = self._entry_var.get()
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()


# ======================== 公开 API ========================

def showinfo(title, message, parent=None):
    """显示信息对话框，居中在 parent 上"""
    dlg = _MsgDialog(parent, title, message, "info")
    parent.wait_window(dlg)
    return "ok"


def showwarning(title, message, parent=None):
    """显示警告对话框，居中在 parent 上"""
    dlg = _MsgDialog(parent, title, message, "warning")
    parent.wait_window(dlg)
    return "ok"


def showerror(title, message, parent=None):
    """显示错误对话框，居中在 parent 上"""
    dlg = _MsgDialog(parent, title, message, "error")
    parent.wait_window(dlg)
    return "ok"


def askyesno(title, message, parent=None):
    """显示是/否对话框，居中在 parent 上。返回 True/False"""
    dlg = _MsgDialog(parent, title, message, "question")
    parent.wait_window(dlg)
    return dlg.result == "是"


def askstring(title, prompt, parent=None, initialvalue=""):
    """显示输入对话框，居中在 parent 上。返回输入字符串或 None"""
    dlg = _InputDialog(parent, title, prompt, initialvalue)
    parent.wait_window(dlg)
    return dlg.result
