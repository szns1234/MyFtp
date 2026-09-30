"""
MyFtp - 项目文件实时同步工具 GUI
基于 Tkinter 构建，包含服务器管理（含项目监控）、文件浏览和同步日志三个标签页
"""

import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime

from core.config_manager import ConfigManager
from core.ftp_client import FTPClient
from core.file_monitor import FileMonitor
from gui import msgbox as messagebox
from gui.msgbox import askstring, LoadingDialog


class App:
    """主应用窗口"""

    # ---- 颜色主题 - 现代扁平化设计 ----
    BG = "#f0f2f5"
    CARD_BG = "#ffffff"
    PRIMARY = "#2563eb"
    PRIMARY_HOVER = "#1d4ed8"
    PRIMARY_LIGHT = "#dbeafe"
    SUCCESS = "#16a34a"
    SUCCESS_LIGHT = "#dcfce7"
    DANGER = "#dc2626"
    DANGER_LIGHT = "#fee2e2"
    WARNING = "#d97706"
    WARNING_LIGHT = "#fef3c7"
    TEXT_PRIMARY = "#1e293b"
    TEXT_SECONDARY = "#64748b"
    TEXT_MUTED = "#94a3b8"
    BORDER = "#e2e8f0"
    HEADER_BG = "#1e293b"
    STATUS_BG = "#f8fafc"

    def __init__(self, root):
        self.root = root
        self.root.title("MyFtp - 项目文件同步工具")
        self.root.geometry("900x920")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)

        self.config = ConfigManager()
        self.ftp = FTPClient()  # 用于监控和上传的主连接
        self.monitor = FileMonitor(self.ftp, self.config, on_event=self._on_monitor_event)
        
        # 操作锁，防止并发操作导致冲突
        self._operation_lock = threading.Lock()
        self._combo_guards = []
        self._current_operation = None  # 当前正在进行的操作: "upload", "download", "sync", None
        self._stop_requested = False  # 用于停止当前操作的标志

        self._setup_styles()  # 初始化自定义样式
        self._build_header()  # 顶部标题栏
        self._build_menu()
        self._build_notebook()
        self._build_status_bar()
        self._refresh_servers()
        self._refresh_log()
        self._refresh_pending()

    # ======================== 自定义样式 ========================

    def _setup_styles(self):
        """配置全局 ttk 样式 - 现代扁平化设计"""
        style = ttk.Style()
        style.theme_use("clam")

        # 通用字体
        default_font = ("Microsoft YaHei UI", 10)
        small_font = ("Microsoft YaHei UI", 9)
        bold_font = ("Microsoft YaHei UI", 10, "bold")
        header_font = ("Microsoft YaHei UI", 14, "bold")

        # 根窗口背景
        style.configure(".", background=self.BG, font=default_font)

        # 卡片式 Frame
        style.configure("Card.TFrame", background=self.CARD_BG, relief="flat", borderwidth=0)
        style.configure("CardBorder.TFrame", background=self.CARD_BG, relief="solid",
                        borderwidth=1, bordercolor=self.BORDER)

        # 标题栏 Frame
        style.configure("Header.TFrame", background=self.HEADER_BG)

        # LabelFrame - 卡片式
        style.configure("TLabelframe", background=self.CARD_BG, relief="solid",
                        borderwidth=1, bordercolor=self.BORDER)
        style.configure("TLabelframe.Label", background=self.CARD_BG,
                        foreground=self.TEXT_PRIMARY, font=bold_font)

        # 标签
        style.configure("TLabel", background=self.BG, foreground=self.TEXT_PRIMARY, font=default_font)
        style.configure("Card.TLabel", background=self.CARD_BG, foreground=self.TEXT_PRIMARY, font=default_font)
        style.configure("Header.TLabel", background=self.HEADER_BG, foreground="#ffffff", font=header_font)
        style.configure("HeaderSub.TLabel", background=self.HEADER_BG, foreground="#94a3b8", font=small_font)
        style.configure("Bold.TLabel", font=bold_font)
        style.configure("Status.TLabel", background=self.STATUS_BG, foreground=self.TEXT_SECONDARY, font=small_font)
        style.configure("Success.TLabel", foreground=self.SUCCESS, font=bold_font)
        style.configure("Danger.TLabel", foreground=self.DANGER, font=bold_font)
        style.configure("Warning.TLabel", foreground=self.WARNING, font=bold_font)
        style.configure("Primary.TLabel", foreground=self.PRIMARY, font=bold_font)
        style.configure("Muted.TLabel", foreground=self.TEXT_MUTED, font=small_font)

        # 禁用状态通用配色（浅灰背景 + 灰色文字，视觉上明确不可点击）
        DISABLED_BG = "#e9ecef"
        DISABLED_FG = "#adb5bd"

        # 按钮 - 主色调
        style.configure("TButton", font=default_font, padding=(14, 6), relief="flat",
                        background=self.CARD_BG, foreground=self.TEXT_PRIMARY,
                        borderwidth=1, focusthickness=0)
        style.map("TButton",
                  background=[("active", self.PRIMARY_LIGHT), ("pressed", self.BORDER),
                             ("disabled", DISABLED_BG)],
                  foreground=[("active", self.PRIMARY), ("disabled", DISABLED_FG)])

        # 主按钮（强调）
        style.configure("Primary.TButton", font=bold_font, padding=(16, 7),
                        background=self.PRIMARY, foreground="#ffffff", borderwidth=0)
        style.map("Primary.TButton",
                  background=[("active", self.PRIMARY_HOVER), ("pressed", "#1e40af"),
                             ("disabled", DISABLED_BG)],
                  foreground=[("disabled", DISABLED_FG)])

        # 成功按钮
        style.configure("Success.TButton", font=bold_font, padding=(14, 6),
                        background=self.SUCCESS, foreground="#ffffff", borderwidth=0)
        style.map("Success.TButton",
                  background=[("active", "#15803d"), ("pressed", "#166534"),
                             ("disabled", DISABLED_BG)],
                  foreground=[("disabled", DISABLED_FG)])

        # 危险按钮
        style.configure("Danger.TButton", font=bold_font, padding=(14, 6),
                        background=self.DANGER, foreground="#ffffff", borderwidth=0)
        style.map("Danger.TButton",
                  background=[("active", "#b91c1c"), ("pressed", "#991b1b"),
                             ("disabled", DISABLED_BG)],
                  foreground=[("disabled", DISABLED_FG)])

        # 警告按钮
        style.configure("Warning.TButton", font=bold_font, padding=(14, 6),
                        background=self.WARNING, foreground="#ffffff", borderwidth=0)
        style.map("Warning.TButton",
                  background=[("active", "#d97706"), ("pressed", "#b45309"),
                             ("disabled", DISABLED_BG)],
                  foreground=[("disabled", DISABLED_FG)])

        # 工具栏按钮（紧凑）
        style.configure("Toolbar.TButton", font=small_font, padding=(10, 4),
                        background=self.CARD_BG, foreground=self.TEXT_PRIMARY,
                        borderwidth=1, bordercolor=self.BORDER)
        style.map("Toolbar.TButton",
                  background=[("active", self.PRIMARY_LIGHT), ("pressed", self.BORDER),
                             ("disabled", DISABLED_BG)],
                  foreground=[("active", self.PRIMARY), ("disabled", DISABLED_FG)],
                  bordercolor=[("disabled", DISABLED_BG)])

        # 紧凑实心按钮（用于工具栏中有颜色的按钮，与 Toolbar 同尺寸但有实心背景）
        style.configure("Compact.Primary.TButton", font=small_font, padding=(8, 4),
                        background=self.PRIMARY, foreground="#ffffff", borderwidth=0)
        style.map("Compact.Primary.TButton",
                  background=[("active", self.PRIMARY_HOVER), ("pressed", "#1e40af"),
                             ("disabled", DISABLED_BG)],
                  foreground=[("disabled", DISABLED_FG)])

        style.configure("Compact.Success.TButton", font=small_font, padding=(8, 4),
                        background=self.SUCCESS, foreground="#ffffff", borderwidth=0)
        style.map("Compact.Success.TButton",
                  background=[("active", "#15803d"), ("pressed", "#166534"),
                             ("disabled", DISABLED_BG)],
                  foreground=[("disabled", DISABLED_FG)])

        style.configure("Compact.Danger.TButton", font=small_font, padding=(8, 4),
                        background=self.DANGER, foreground="#ffffff", borderwidth=0)
        style.map("Compact.Danger.TButton",
                  background=[("active", "#b91c1c"), ("pressed", "#991b1b"),
                             ("disabled", DISABLED_BG)],
                  foreground=[("disabled", DISABLED_FG)])

        style.configure("Compact.Warning.TButton", font=small_font, padding=(8, 4),
                        background=self.WARNING, foreground="#ffffff", borderwidth=0)
        style.map("Compact.Warning.TButton",
                  background=[("active", "#d97706"), ("pressed", "#b45309"),
                             ("disabled", DISABLED_BG)],
                  foreground=[("disabled", DISABLED_FG)])

        # 输入框
        style.configure("TEntry", font=default_font, padding=(8, 4),
                        fieldbackground=self.CARD_BG, foreground=self.TEXT_PRIMARY,
                        borderwidth=1, bordercolor=self.BORDER)
        style.map("TEntry",
                  fieldbackground=[("focus", self.CARD_BG)],
                  bordercolor=[("focus", self.PRIMARY)])

        # 下拉框
        style.configure("TCombobox", font=default_font, padding=(8, 4),
                        fieldbackground=self.CARD_BG, foreground=self.TEXT_PRIMARY,
                        borderwidth=1, bordercolor=self.BORDER,
                        arrowcolor=self.TEXT_SECONDARY)
        style.map("TCombobox",
                  fieldbackground=[("focus", self.CARD_BG)],
                  bordercolor=[("focus", self.PRIMARY)])

        # Notebook 标签页
        style.configure("TNotebook", background=self.BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=default_font, padding=(18, 8),
                        background=self.BG, foreground=self.TEXT_SECONDARY,
                        borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", self.CARD_BG), ("active", self.PRIMARY_LIGHT)],
                  foreground=[("selected", self.PRIMARY), ("active", self.TEXT_PRIMARY)],
                  borderwidth=[("selected", 0)],
                  padding=[("selected", (18, 8))])

        # Treeview（表格）
        style.configure("Treeview", font=default_font, rowheight=30,
                        background=self.CARD_BG, foreground=self.TEXT_PRIMARY,
                        fieldbackground=self.CARD_BG, borderwidth=0)
        style.map("Treeview",
                  background=[("selected", self.PRIMARY_LIGHT)],
                  foreground=[("selected", self.PRIMARY)])
        style.configure("Treeview.Heading", font=bold_font, padding=(8, 6),
                        background=self.BG, foreground=self.TEXT_PRIMARY,
                        borderwidth=0, relief="flat")
        style.map("Treeview.Heading",
                  background=[("active", self.PRIMARY_LIGHT)],
                  foreground=[("active", self.PRIMARY)])

        # 进度条
        style.configure("TProgressbar", thickness=8, background=self.PRIMARY,
                        troughcolor=self.BORDER, borderwidth=0)

        # 分隔符
        style.configure("TSeparator", background=self.BORDER)

        # 滚动条
        style.configure("TScrollbar", background=self.BG, bordercolor=self.BORDER,
                        arrowcolor=self.TEXT_SECONDARY, troughcolor=self.BG,
                        borderwidth=0)
        style.map("TScrollbar",
                  background=[("active", self.PRIMARY_LIGHT), ("pressed", self.PRIMARY_LIGHT)])

        # Checkbutton
        style.configure("TCheckbutton", font=default_font, background=self.BG,
                        foreground=self.TEXT_PRIMARY, padding=(4, 2))
        style.map("TCheckbutton",
                  background=[("active", self.BG)])

        # Radiobutton
        style.configure("TRadiobutton", font=default_font, background=self.BG,
                        foreground=self.TEXT_PRIMARY, padding=(4, 2))
        style.map("TRadiobutton",
                  background=[("active", self.BG)])

        # 对话框内的 Label
        style.configure("Dialog.TLabel", background=self.CARD_BG, foreground=self.TEXT_PRIMARY, font=default_font)
        style.configure("Dialog.TFrame", background=self.CARD_BG)

    # ======================== 顶部标题栏 ========================

    def _build_header(self):
        """构建顶部标题栏"""
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(fill="x", side="top")

        inner = ttk.Frame(header, style="Header.TFrame", padding=(20, 12))
        inner.pack(fill="x")

        # 左侧：应用图标和名称
        ttk.Label(inner, text="⚡ MyFtp", style="Header.TLabel").pack(side="left")

        # 右侧：版本信息
        ttk.Label(inner, text="v1.1.0 · 项目文件同步工具",
                  style="HeaderSub.TLabel").pack(side="right")

    # ======================== 菜单栏 ========================

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="导出配置", command=self._export_config)
        file_menu.add_command(label="导入配置", command=self._import_config)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.config(menu=menubar)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _export_config(self):
        """导出配置到文件"""
        default_name = f"myftp_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = filedialog.asksaveasfilename(
            title="导出配置",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            parent=self.root
        )
        if not path:
            return
        ok, msg = self.config.export_config(path)
        if ok:
            messagebox.showinfo("成功", msg, parent=self.root)
        else:
            messagebox.showerror("失败", msg, parent=self.root)

    def _import_config(self):
        """从文件导入配置"""
        path = filedialog.askopenfilename(
            title="导入配置",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            parent=self.root
        )
        if not path:
            return
        if not messagebox.askyesno("确认", "导入配置将覆盖当前配置，是否继续？", parent=self.root):
            return
        ok, msg = self.config.import_config(path)
        if ok:
            # 刷新所有界面
            self._refresh_servers()
            self._refresh_server_combo()
            self._refresh_pending()
            self._refresh_log()
            messagebox.showinfo("成功", msg, parent=self.root)
        else:
            messagebox.showerror("失败", msg, parent=self.root)

    # ======================== Notebook ========================

    def _build_notebook(self):
        # Notebook 外层的卡片容器
        nb_container = ttk.Frame(self.root, style="Card.TFrame", padding=(0, 0))
        nb_container.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        self.nb = ttk.Notebook(nb_container)
        self.nb.pack(fill="both", expand=True)

        # 服务器管理（含项目监控）
        self.server_frame = ttk.Frame(self.nb, style="Card.TFrame")
        self.nb.add(self.server_frame, text="📁  服务器管理")
        self._build_server_tab()

        # 下载文件
        self.download_frame = ttk.Frame(self.nb, style="Card.TFrame")
        self.nb.add(self.download_frame, text="📥  下载文件")
        self._build_download_tab()

        # 同步日志
        self.log_frame = ttk.Frame(self.nb, style="Card.TFrame")
        self.nb.add(self.log_frame, text="📋  同步日志")
        self._build_log_tab(self.log_frame)

        # 切换标签页时刷新
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, event=None):
        """切换标签页时刷新数据"""
        current_tab = self.nb.index(self.nb.select())
        if current_tab == 0:  # 服务器管理
            self._refresh_servers()
            self._refresh_pending()
        elif current_tab == 1:  # 下载文件
            self._update_download_server_display()
        elif current_tab == 2:  # 同步日志
            self._refresh_log()

    def _update_download_server_display(self):
        """更新下载文件Tab中显示当前选中的服务器"""
        name = self.server_select_var.get()
        if name:
            self.download_current_server_var.set(name)
        else:
            self.download_current_server_var.set("未选择")

    # ======================== 服务器管理 Tab（含项目监控） ========================

    def _build_server_tab(self):
        frame = self.server_frame

        # ==================== 主布局 ====================
        main_frame = ttk.Frame(frame, style="Card.TFrame")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ==================== 顶部工具栏（卡片式） ====================
        toolbar_card = ttk.Frame(main_frame, style="Card.TFrame", padding=(12, 10))
        toolbar_card.pack(fill="x", pady=(0, 10))

        ttk.Label(toolbar_card, text="服务器:", style="Bold.TLabel").pack(side="left", padx=(0, 6))
        self.server_select_var = tk.StringVar(name="server_select")
        self.server_select_combo = ttk.Combobox(toolbar_card, textvariable=self.server_select_var, 
                                                 width=20, state="readonly", exportselection=False)
        self.server_select_combo.pack(side="left", padx=4)
        self.server_select_combo.bind("<<ComboboxSelected>>", self._on_server_combo_select)
        self.server_select_combo.bind("<<ComboboxSelected>>", lambda e: self._restore_combo_text(), add="+")
        self._keep_combo_text(self.server_select_combo, self.server_select_var)

        ttk.Separator(toolbar_card, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(toolbar_card, text="🔄 刷新", command=self._on_refresh_server_click, style="Compact.Success.TButton").pack(side="left", padx=2)
        ttk.Button(toolbar_card, text="➕ 新建", command=self._show_server_dialog, style="Compact.Primary.TButton").pack(side="left", padx=2)
        ttk.Button(toolbar_card, text="✏️ 编辑", command=self._edit_selected_server, style="Compact.Warning.TButton").pack(side="left", padx=2)
        ttk.Button(toolbar_card, text="🗑 删除", command=self._remove_server, style="Compact.Danger.TButton").pack(side="left", padx=2)
        ttk.Separator(toolbar_card, orient="vertical").pack(side="left", fill="y", padx=10)
        self.test_conn_btn = ttk.Button(
            toolbar_card, text="🔌 测试连接", command=self._test_connection, style="Compact.Success.TButton")
        self.test_conn_btn.pack(side="left", padx=2)

        # ==================== 待上传文件区域（卡片式） ====================
        pending_group = ttk.LabelFrame(main_frame, text="📄 待上传文件", padding=8)
        pending_group.pack(fill="both", expand=True)
        self._build_pending_tab(pending_group)


    def _build_pending_tab(self, parent):
        """构建待上传文件面板"""
        # 操作按钮行
        pending_btns = ttk.Frame(parent, style="Card.TFrame", padding=(4, 4))
        pending_btns.pack(fill="x")
        self.scan_btn = ttk.Button(pending_btns, text="🔄 刷新扫描", command=self._refresh_pending_with_filter, style="Compact.Success.TButton")
        self.scan_btn.pack(side="left", padx=2)
        ttk.Separator(pending_btns, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(pending_btns, text="⬆ 上传选中", command=self._upload_selected, style="Compact.Primary.TButton").pack(side="left", padx=2)
        ttk.Button(pending_btns, text="⬆ 全部上传", command=self._upload_all_pending, style="Compact.Success.TButton").pack(side="left", padx=2)
        ttk.Button(pending_btns, text="✖ 移除选中", command=self._remove_selected_pending, style="Compact.Danger.TButton").pack(side="left", padx=2)
        ttk.Separator(pending_btns, orient="vertical").pack(side="left", fill="y", padx=6)
        self.auto_scan_var = tk.BooleanVar(value=False)
        self.auto_scan_cb = tk.Checkbutton(pending_btns, text="⏱ 自动扫描", variable=self.auto_scan_var,
                        command=self._on_auto_scan_toggled, state="disabled",
                        font=("Microsoft YaHei UI", 9), bg=self.CARD_BG, fg=self.TEXT_PRIMARY,
                        activebackground=self.CARD_BG, activeforeground=self.TEXT_PRIMARY,
                        selectcolor=self.CARD_BG, relief="flat", bd=0,
                        padx=4, pady=2, cursor="hand2")
        self.auto_scan_cb.pack(side="left", padx=2)
        # 倒计时显示标签（自动扫描勾选后显示距下次扫描的剩余秒数）
        self.countdown_var = tk.StringVar(value="")
        self.countdown_label = ttk.Label(pending_btns, textvariable=self.countdown_var,
                                         style="Muted.TLabel")
        self.countdown_label.pack(side="left", padx=(2, 0))
        self._countdown_after_id = None  # after() 的 ID，用于取消定时回调
        self.pending_count_var = tk.StringVar(value="待上传: 0 个文件")
        ttk.Label(pending_btns, textvariable=self.pending_count_var,
                  style="Warning.TLabel").pack(side="right", padx=4)

        # 文件列表
        pending_list_frame = ttk.Frame(parent, style="Card.TFrame")
        pending_list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        pcols = ("file", "action", "time")
        self.pending_tree = ttk.Treeview(pending_list_frame, columns=pcols, show="headings", height=10)
        pheaders = {"file": "文件路径", "action": "操作类型", "time": "修改时间"}
        pwidths = {"file": 250, "action": 90, "time": 150}
        for c in pcols:
            self.pending_tree.heading(c, text=pheaders[c],
                                     command=lambda col=c: self._sort_pending_tree(col))
            self.pending_tree.column(c, width=pwidths[c])
        # 默认按修改时间降序
        self._pending_sort_col = "time"
        self._pending_sort_reverse = True
        self._update_pending_headings()
        self.pending_tree.pack(side="left", fill="both", expand=True)
        psb = ttk.Scrollbar(pending_list_frame, orient="vertical", command=self.pending_tree.yview)
        self.pending_tree.configure(yscrollcommand=psb.set)
        psb.pack(side="right", fill="y")

        # 右键上下文菜单
        self.pending_context_menu = tk.Menu(self.pending_tree, tearoff=0)
        self.pending_context_menu.add_command(label="加入过滤", command=self._add_to_excludes)
        self.pending_context_menu.add_command(label="删除文件", command=self._delete_pending_file)
        self.pending_tree.bind("<Button-3>", self._show_pending_context_menu)

    # --- 服务器增删改 ---

    def _new_server(self):
        """新建服务器 - 清空表单"""
        self._clear_server_form()
        self.server_select_var.set("")
        self.save_server_btn.config(text="添加服务器")
        self._set_status("新建服务器 - 请填写信息后保存")

    def _save_server(self):
        """保存服务器（添加或更新）"""
        v = self.server_vars
        name = v["server_name"].get().strip()
        host = v["server_host"].get().strip()
        
        if not name or not host:
            messagebox.showwarning("提示", "请填写名称和主机地址", parent=self.root)
            return
        
        # 检查是新增还是更新
        selected_name = self.server_select_var.get()
        
        if selected_name:
            # 更新现有服务器
            ok, msg = self.config.update_server(
                name=selected_name,
                new_name=name,
                host=host,
                port=int(v["server_port"].get().strip() or "21"),
                username=v["server_user"].get().strip(),
                password=v["server_pass"].get().strip(),
                remote_path=v["server_rpath"].get().strip() or "/",
                local_path=v["server_lpath"].get().strip(),
            )
            if ok:
                self._refresh_server_combo()
                self.server_select_var.set(name)
        else:
            # 添加新服务器
            ok, msg = self.config.add_server(
                name=name,
                host=host,
                port=int(v["server_port"].get().strip() or "21"),
                username=v["server_user"].get().strip(),
                password=v["server_pass"].get().strip(),
                remote_path=v["server_rpath"].get().strip() or "/",
                local_path=v["server_lpath"].get().strip(),
            )
            if ok:
                self._refresh_server_combo()
                self.server_select_var.set(name)
                self.save_server_btn.config(text="保存修改")
        
        if ok:
            self._set_status(f"✓ {msg}")
        else:
            messagebox.showwarning("提示", msg, parent=self.root)

    def _keep_combo_text(self, combo, variable):
        """记录这个下拉框，供选中后统一恢复显示。"""
        self._combo_guards.append((combo, variable))

    def _restore_combo_text(self):
        """Windows 上多个只读下拉框会互相清空，选中任意一个后把两边文字都写回。"""
        for combo, variable in self._combo_guards:
            value = variable.get()
            if value and combo.get() != value:
                combo.set(value)

    def _on_refresh_server_click(self):
        """手动点刷新：未选服务器时提示，不影响打开页面时的自动刷新。"""
        if not self._require_selected_server():
            return
        self._refresh_server_combo()

    def _refresh_server_combo(self):
        """刷新服务器下拉列表，保留当前选择。"""
        servers = [s["name"] for s in self.config.get_servers()]
        current = self.server_select_var.get()
        self.server_select_combo["values"] = servers
        if current in servers:
            self.server_select_var.set(current)
        elif current:
            self.server_select_var.set("")
        self._restore_combo_text()

    def _on_server_combo_select(self, event=None):
        """下拉框选择服务器 - 自动断开旧连接，切换到新服务器并加载其文件。"""
        name = self.server_select_var.get()
        # 同步更新下载页顶部显示的当前服务器
        self._update_download_server_display()
        # 切换服务器时，若已连接则先异步断开，断开后自动连接新服务器
        if self.ftp.is_connected:
            self._set_download_buttons_state(False, busy=True)
            self._show_download_wait("正在切换服务器")

            def _do_switch_disconnect():
                try:
                    self.ftp.disconnect()
                except Exception:
                    pass
                self.root.after(0, self._close_download_wait)
                self.root.after(0, lambda: self.download_tree.delete(*self.download_tree.get_children()))
                self.root.after(0, lambda: self._set_download_buttons_state(False))
                # 选中了新服务器则自动连接并加载文件，否则仅提示
                if name:
                    self.root.after(0, self._download_connect)
                else:
                    self.root.after(0, lambda: self._set_status("已断开连接"))

            threading.Thread(target=_do_switch_disconnect, daemon=True).start()
        elif name:
            # 之前未连接，直接连上新选的服务器并加载文件
            self._download_connect()

        if name:
            self.auto_scan_cb.config(state="normal")
            if self.auto_scan_var.get():
                self._start_monitor_for_server(name)
        else:
            self.auto_scan_cb.config(state="disabled")
            self.auto_scan_var.set(False)

    def _add_server(self):
        """添加服务器（旧方法，保留兼容）"""
        v = self.server_vars
        name = v["server_name"].get().strip()
        host = v["server_host"].get().strip()
        if not name or not host:
            messagebox.showwarning("提示", "请填写名称和主机地址", parent=self.root)
            return
        ok, msg = self.config.add_server(
            name=name,
            host=host,
            port=int(v["server_port"].get().strip() or "21"),
            username=v["server_user"].get().strip(),
            password=v["server_pass"].get().strip(),
            remote_path=v["server_rpath"].get().strip() or "/",
            local_path=v["server_lpath"].get().strip(),
        )
        if ok:
            self._refresh_server_combo()
            self._clear_server_form()
        messagebox.showinfo("结果", msg, parent=self.root)

    def _update_server(self):
        sel = self.server_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个服务器", parent=self.root)
            return
        old_name = self.server_tree.item(sel[0], "values")[0]
        v = self.server_vars
        new_name = v["server_name"].get().strip()
        
        # 获取远程路径值
        remote_path = v["server_rpath"].get().strip()
        print(f"[DEBUG] 更新服务器 - 远程路径输入值: '{remote_path}'")
        if not remote_path:
            remote_path = "/"
        
        if self.monitor.is_running:
            if self.monitor.monitored_name == old_name:
                self.monitor.stop()
        ok, msg = self.config.update_server(
            name=old_name,
            new_name=new_name,
            host=v["server_host"].get().strip(),
            port=int(v["server_port"].get().strip() or "21"),
            username=v["server_user"].get().strip(),
            password=v["server_pass"].get().strip(),
            remote_path=remote_path,
            local_path=v["server_lpath"].get().strip(),
        )
        if ok:
            self._refresh_servers()
            # 验证保存结果
            server = self.config.get_server(new_name if new_name else old_name)
            if server:
                print(f"[DEBUG] 更新后配置 - remote_path: '{server.get('remote_path', 'NOT SET')}'")
        messagebox.showinfo("结果", msg, parent=self.root)

    def _remove_server(self):
        """删除选中的服务器"""
        name = self.server_select_var.get()
        if not name:
            messagebox.showwarning("提示", "请先选择要删除的服务器", parent=self.root)
            return
        if messagebox.askyesno("确认", f"确定删除服务器 '{name}' 吗？", parent=self.root):
            # 如果正在扫描这个服务器，先停止
            if self.monitor.is_running and self.monitor.monitored_name == name:
                self.monitor.stop()
                self._set_monitor_status(False)
                self.auto_scan_var.set(False)
            ok, msg = self.config.remove_server(name)
            if ok:
                self._refresh_server_combo()
                self.server_select_var.set("")
                self.auto_scan_cb.config(state="disabled")
            messagebox.showinfo("结果", msg, parent=self.root)

    def _test_connection(self):
        """测试选中的服务器连接"""
        if getattr(self, "_test_wait", None):
            return
        name = self.server_select_var.get()
        if not name:
            messagebox.showwarning("提示", "请先选择要测试的服务器", parent=self.root)
            return
        server = self.config.get_server(name)
        if not server:
            messagebox.showwarning("提示", "服务器不存在", parent=self.root)
            return
        self._show_test_wait(server)
        threading.Thread(target=self._do_test_conn_server, args=(server,), daemon=True).start()

    def _show_test_wait(self, server):
        """测试进行中的等待窗，避免界面看起来像卡死。"""
        dialog = tk.Toplevel(self.root)
        dialog.title("连接测试")
        dialog.geometry("360x150")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.configure(bg=self.CARD_BG)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - 360) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 150) // 2
        dialog.geometry(f"+{x}+{y}")

        host = server.get("host", "")
        port = server.get("port", 21)
        spinner = tk.Label(
            dialog, text="◐", font=("Segoe UI Symbol", 22),
            bg=self.CARD_BG, fg=self.PRIMARY,
        )
        spinner.pack(pady=(18, 4))
        tk.Label(
            dialog, text=f"正在连接 {host}:{port}",
            font=("Microsoft YaHei UI", 10), bg=self.CARD_BG, fg=self.TEXT_PRIMARY,
        ).pack()
        hint = tk.Label(
            dialog, text="请稍候，超时约 30 秒",
            font=("Microsoft YaHei UI", 9), bg=self.CARD_BG, fg=self.TEXT_MUTED,
        )
        hint.pack(pady=(2, 0))

        frames = ("◐", "◓", "◑", "◒")
        state = {"index": 0, "after_id": None, "ticks": 0}

        def tick():
            state["index"] = (state["index"] + 1) % len(frames)
            state["ticks"] += 1
            if dialog.winfo_exists():
                spinner.config(text=frames[state["index"]])
                hint.config(text=f"请稍候，已等待 {state['ticks'] // 2} 秒")
                state["after_id"] = dialog.after(500, tick)

        state["after_id"] = dialog.after(500, tick)
        self.test_conn_btn.config(state="disabled", text="⏳ 测试中")
        self._test_wait = {"dialog": dialog, "state": state}
        dialog.grab_set()

    def _close_test_wait(self):
        wait = getattr(self, "_test_wait", None)
        self._test_wait = None
        if self.test_conn_btn.winfo_exists():
            self.test_conn_btn.config(state="normal", text="🔌 测试连接")
        if not wait:
            return
        dialog = wait["dialog"]
        after_id = wait["state"].get("after_id")
        if after_id and dialog.winfo_exists():
            dialog.after_cancel(after_id)
        if dialog.winfo_exists():
            dialog.grab_release()
            dialog.destroy()

    def _do_test_conn_server(self, server):
        """测试指定服务器的连接"""
        ftp = FTPClient()
        ok, msg = ftp.connect(
            host=server.get("host", ""),
            port=server.get("port", 21),
            username=server.get("username", ""),
            password=server.get("password", ""),
            use_tls=bool(server.get("use_tls")),
        )
        if ok:
            ftp.disconnect()
        self.root.after(0, lambda: self._on_test_done(ok, msg))

    def _on_test_done(self, ok, msg):
        self._close_test_wait()
        self._set_status(msg)
        if ok:
            messagebox.showinfo("连接测试", msg, parent=self.root)
        else:
            messagebox.showerror("连接测试", msg, parent=self.root)

    def _on_server_select(self, event=None):
        sel = self.server_tree.selection()
        if not sel:
            return
        name = self.server_tree.item(sel[0], "values")[0]
        s = self.config.get_server(name)
        if not s:
            return
        v = self.server_vars
        v["server_name"].set(s["name"])
        v["server_host"].set(s["host"])
        v["server_port"].set(s["port"])
        v["server_user"].set(s["username"])
        v["server_pass"].set(s.get("password", ""))
        v["server_rpath"].set(s.get("remote_path", "/"))
        v["server_lpath"].set(s.get("local_path", ""))
        
        # 加载该服务器的排除规则
        self._load_excludes_for_server(name)

    def _clear_server_form(self):
        for key in ("server_name", "server_host", "server_user", "server_pass", "server_lpath"):
            self.server_vars[key].set("")
        self.server_vars["server_port"].set("21")
        self.server_vars["server_rpath"].set("/")

    def _show_server_dialog(self, edit_mode=False, server_name=None):
        """显示添加/编辑服务器弹窗"""
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑服务器" if edit_mode else "添加服务器")
        dialog.geometry("450x560")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.configure(bg=self.CARD_BG)
        dialog.grab_set()
        
        # 居中到主窗口
        dialog.update_idletasks()
        px = self.root.winfo_rootx()
        py = self.root.winfo_rooty()
        pw = self.root.winfo_width()
        ph = self.root.winfo_height()
        dw = dialog.winfo_width()
        dh = dialog.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # 表单变量
        vars_dict = {}
        
        # 主框架
        main_frame = ttk.Frame(dialog, style="Card.TFrame", padding=15)
        main_frame.pack(fill="both", expand=True)
        
        # 标题
        ttk.Label(main_frame, text="服务器配置", style="Bold.TLabel").pack(pady=(0, 15))
        
        # 表单区域
        form_frame = ttk.Frame(main_frame, style="Card.TFrame")
        form_frame.pack(fill="x")
        
        # 名称
        ttk.Label(form_frame, text="名称:", style="Bold.TLabel", width=10).grid(row=0, column=0, sticky="w", pady=6)
        vars_dict["name"] = tk.StringVar(value=server_name if edit_mode else "")
        ttk.Entry(form_frame, textvariable=vars_dict["name"], width=35).grid(
            row=0, column=1, sticky="ew", padx=(4, 0), pady=6)
        
        # 主机 + 端口
        ttk.Label(form_frame, text="主机:", style="Bold.TLabel", width=10).grid(row=1, column=0, sticky="w", pady=6)
        host_frame = ttk.Frame(form_frame, style="Card.TFrame")
        host_frame.grid(row=1, column=1, sticky="w", pady=6, padx=(4, 0))
        vars_dict["host"] = tk.StringVar()
        ttk.Entry(host_frame, textvariable=vars_dict["host"], width=22).pack(side="left")
        ttk.Label(host_frame, text="端口:", style="Card.TLabel").pack(side="left", padx=(10, 0))
        vars_dict["port"] = tk.StringVar(value="21")
        ttk.Entry(host_frame, textvariable=vars_dict["port"], width=6).pack(side="left", padx=(4, 0))
        
        # 用户名 + 密码
        ttk.Label(form_frame, text="用户名:", style="Bold.TLabel", width=10).grid(row=2, column=0, sticky="w", pady=6)
        auth_frame = ttk.Frame(form_frame, style="Card.TFrame")
        auth_frame.grid(row=2, column=1, sticky="w", pady=6, padx=(4, 0))
        vars_dict["user"] = tk.StringVar()
        ttk.Entry(auth_frame, textvariable=vars_dict["user"], width=14).pack(side="left")
        ttk.Label(auth_frame, text="密码:", style="Card.TLabel").pack(side="left", padx=(10, 0))
        vars_dict["pass"] = tk.StringVar()
        ttk.Entry(auth_frame, textvariable=vars_dict["pass"], width=14, show="*").pack(side="left", padx=(4, 0))

        ttk.Label(form_frame, text="加密:", style="Bold.TLabel", width=10).grid(row=3, column=0, sticky="w", pady=6)
        vars_dict["use_tls"] = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form_frame, text="显式 FTPS（AUTH TLS，端口 21，被动模式）",
            variable=vars_dict["use_tls"],
        ).grid(row=3, column=1, sticky="w", padx=(4, 0), pady=6)
        
        # 远程路径
        ttk.Label(form_frame, text="远程路径:", style="Bold.TLabel", width=10).grid(row=4, column=0, sticky="w", pady=6)
        vars_dict["rpath"] = tk.StringVar(value="/")
        ttk.Entry(form_frame, textvariable=vars_dict["rpath"], width=35).grid(
            row=4, column=1, sticky="ew", padx=(4, 0), pady=6)
        
        # 本地路径
        ttk.Label(form_frame, text="本地路径:", style="Bold.TLabel", width=10).grid(row=5, column=0, sticky="w", pady=6)
        lpath_frame = ttk.Frame(form_frame, style="Card.TFrame")
        lpath_frame.grid(row=5, column=1, sticky="ew", pady=6, padx=(4, 0))
        vars_dict["lpath"] = tk.StringVar()
        ttk.Entry(lpath_frame, textvariable=vars_dict["lpath"], width=28).pack(side="left", fill="x", expand=True)
        ttk.Button(lpath_frame, text="浏览...", style="Toolbar.TButton",
                   command=lambda: self._browse_local_dir_dialog(vars_dict["lpath"])).pack(side="left", padx=4)
        
        # 排除规则
        ttk.Label(form_frame, text="排除规则:", style="Bold.TLabel", width=10).grid(row=6, column=0, sticky="nw", pady=6)
        excl_frame = ttk.Frame(form_frame, style="Card.TFrame")
        excl_frame.grid(row=6, column=1, sticky="nsew", pady=6, padx=(4, 0))
        excl_text = tk.Text(excl_frame, height=5, wrap="word", font=("Microsoft YaHei UI", 9))
        excl_text.pack(side="left", fill="both", expand=True)
        excl_scroll = ttk.Scrollbar(excl_frame, orient="vertical", command=excl_text.yview)
        excl_text.configure(yscrollcommand=excl_scroll.set)
        excl_scroll.pack(side="right", fill="y")
        ttk.Label(form_frame, text="(每行一个规则，如: *.log, temp/)", 
                 style="Muted.TLabel").grid(row=7, column=1, sticky="w", padx=(4, 0))
        
        form_frame.columnconfigure(1, weight=1)
        
        # 如果是编辑模式，填充数据
        if edit_mode and server_name:
            server = self.config.get_server(server_name)
            if server:
                vars_dict["name"].set(server.get("name", ""))
                vars_dict["host"].set(server.get("host", ""))
                vars_dict["port"].set(str(server.get("port", 21)))
                vars_dict["user"].set(server.get("username", ""))
                vars_dict["pass"].set(server.get("password", ""))
                vars_dict["rpath"].set(server.get("remote_path", "/"))
                vars_dict["lpath"].set(server.get("local_path", ""))
                vars_dict["use_tls"].set(bool(server.get("use_tls")))
                excludes = self.config.get_exclude_patterns(server_name)
                if excludes:
                    excl_text.insert("1.0", "\n".join(excludes))
        
        # 按钮区域 - 居中显示
        btn_frame = ttk.Frame(main_frame, style="Card.TFrame")
        btn_frame.pack(fill="x", pady=(25, 0))
        
        # 使用内部框架实现按钮居中
        btn_inner = ttk.Frame(btn_frame, style="Card.TFrame")
        btn_inner.pack(expand=True)
        
        def do_save():
            name = vars_dict["name"].get().strip()
            host = vars_dict["host"].get().strip()
            if not name or not host:
                messagebox.showwarning("提示", "请填写名称和主机地址", parent=dialog)
                return
            
            excludes = [line.strip() for line in excl_text.get("1.0", "end").split("\n") if line.strip()]
            
            if edit_mode and server_name:
                # 更新
                ok, msg = self.config.update_server(
                    name=server_name,
                    new_name=name,
                    host=host,
                    port=int(vars_dict["port"].get().strip() or "21"),
                    username=vars_dict["user"].get().strip(),
                    password=vars_dict["pass"].get().strip(),
                    remote_path=vars_dict["rpath"].get().strip() or "/",
                    local_path=vars_dict["lpath"].get().strip(),
                    use_tls=vars_dict["use_tls"].get(),
                )
                if ok:
                    self.config.update_server_excludes(name, excludes)
            else:
                # 添加
                ok, msg = self.config.add_server(
                    name=name,
                    host=host,
                    port=int(vars_dict["port"].get().strip() or "21"),
                    username=vars_dict["user"].get().strip(),
                    password=vars_dict["pass"].get().strip(),
                    remote_path=vars_dict["rpath"].get().strip() or "/",
                    local_path=vars_dict["lpath"].get().strip(),
                    use_tls=vars_dict["use_tls"].get(),
                )
                if ok:
                    self.config.update_server_excludes(name, excludes)
            
            if ok:
                self._refresh_server_combo()
                self.server_select_var.set(name)
                dialog.destroy()
                messagebox.showinfo("结果", msg, parent=self.root)
            else:
                messagebox.showinfo("结果", msg, parent=dialog)
        
        # 保存按钮使用强调样式
        save_btn = ttk.Button(btn_inner, text="保存", command=do_save, style="Primary.TButton", width=12)
        save_btn.pack(side="left", padx=(0, 12))
        ttk.Button(btn_inner, text="取消", command=dialog.destroy, style="Danger.TButton", width=12).pack(side="left")
        
        # 聚焦到第一个输入框
        dialog.after(100, lambda: dialog.focus_force())

    def _on_test_dialog_done(self, ok, msg, btn):
        """弹窗测试连接完成回调"""
        btn.config(state="normal", text="测试连接")
        if ok:
            messagebox.showinfo("连接测试", msg, parent=self.root)
        else:
            messagebox.showerror("连接测试", msg, parent=self.root)

    def _browse_local_dir_dialog(self, var):
        """弹窗中浏览本地目录"""
        d = filedialog.askdirectory(title="选择项目本地目录", parent=self.root)
        if d:
            var.set(d)

    def _edit_selected_server(self):
        """编辑选中的服务器"""
        name = self.server_select_var.get()
        if not name:
            messagebox.showwarning("提示", "请先选择要编辑的服务器", parent=self.root)
            return
        self._show_server_dialog(edit_mode=True, server_name=name)

    def _refresh_servers(self):
        """刷新服务器列表（更新下拉框）"""
        self._refresh_server_combo()

    # --- 浏览本地/远程目录 ---

    def _browse_local_dir(self):
        d = filedialog.askdirectory(title="选择项目本地目录", parent=self.root)
        if d:
            self.server_vars["server_lpath"].set(d)

    def _browse_remote_dir(self):
        """弹出远程目录选择对话框"""
        v = self.server_vars
        name = v["server_name"].get().strip()
        host = v["server_host"].get().strip()
        if not host:
            messagebox.showwarning("提示", "请先填写主机地址", parent=self.root)
            return
        # 临时构造服务器信息用于对话框
        server = {
            "host": host,
            "port": int(v["server_port"].get().strip() or "21"),
            "username": v["server_user"].get().strip(),
            "password": v["server_pass"].get().strip(),
            "remote_path": v["server_rpath"].get().strip() or "/",
            "use_tls": bool(v.get("server_tls") and v["server_tls"].get()),
        }
        dlg = RemoteDirDialog(self.root, self.ftp, server, v["server_rpath"].get() or "/")
        self.root.wait_window(dlg.top)
        if dlg.selected_path:
            v["server_rpath"].set(dlg.selected_path)

    # --- 排除规则 ---

    def _auto_save_excludes(self):
        """自动保存当前选中服务器的排除规则（无提示）- 兼容旧接口"""
        self._auto_save_excludes_text()

    def _auto_save_excludes_text(self):
        """自动保存当前选中服务器的排除规则（多行文本框版本）"""
        name = self._get_selected_server_name()
        if not name:
            return

        # 从多行文本框获取内容，每行一个规则
        text = self.excl_text.get("1.0", "end").strip()
        patterns = [p.strip() for p in text.split("\n") if p.strip()]

        ok, msg = self.config.update_server_excludes(name, patterns)
        if ok:
            print(f"[DEBUG] 自动保存项目 '{name}' 的排除规则: {len(patterns)} 条")

    def _save_excludes(self):
        """手动保存（兼容旧接口）"""
        self._auto_save_excludes_text()

    def _load_excludes_for_server(self, name):
        """加载指定服务器的排除规则到输入框"""
        patterns = self.config.get_exclude_patterns(name)
        self.excl_text.delete("1.0", "end")
        if patterns:
            self.excl_text.insert("1.0", "\n".join(patterns))

    # --- 扫描操作 ---

    def _get_selected_server_name(self):
        """获取当前选中的服务器名称（从下拉框）"""
        name = self.server_select_var.get()
        if not name:
            messagebox.showwarning("提示", "请先选择服务器", parent=self.root)
            return None
        return name

    def _ensure_monitor_running(self):
        """检查扫描器是否正在运行（仅做校验，不启动扫描）。返回是否已就绪。"""
        if self.monitor.is_running and self.monitor.monitored_name == self._get_selected_server_name():
            return True
        return False

    def _start_monitor_async(self, name):
        """在后台线程中启动监控扫描，避免阻塞UI"""
        # 显示正在启动的状态
        self._set_monitor_status_scan()
        self.auto_scan_cb.config(state="disabled")

        def do_start():
            try:
                ok, msg = self.monitor.start(name)
                self.root.after(0, lambda: self._on_monitor_started(ok, msg, name))
            except Exception as e:
                self.root.after(0, lambda: self._on_monitor_started(False, str(e), name))

        threading.Thread(target=do_start, daemon=True).start()

    def _on_monitor_started(self, ok, msg, name):
        """后台线程启动扫描完成后的回调（在主线程执行）"""
        self.auto_scan_cb.config(state="normal")
        if ok:
            self._set_monitor_status(True, name)
            self.sync_btn.config(state="normal")
            # 刷新待上传列表
            self._refresh_pending()
            self._refresh_servers()
            # 启动倒计时显示
            self._start_countdown()
        else:
            # 启动失败，取消勾选
            self.auto_scan_var.set(False)
            self._restore_monitor_status()
            self._stop_countdown()
            messagebox.showerror("错误", msg, parent=self.root)

    # ======================== 扫描倒计时显示 ========================

    def _start_countdown(self):
        """启动 UI 倒计时定时器，每秒更新显示"""
        self._stop_countdown()
        self._update_countdown()

    def _stop_countdown(self):
        """停止倒计时显示"""
        if self._countdown_after_id is not None:
            try:
                self.root.after_cancel(self._countdown_after_id)
            except Exception:
                pass
            self._countdown_after_id = None
        self.countdown_var.set("")

    def _update_countdown(self):
        """每秒更新倒计时文字"""
        self._countdown_after_id = None
        if not self.monitor.is_running:
            self.countdown_var.set("")
            return

        if self.monitor.is_scanning:
            # 正在执行扫描
            self.countdown_var.set("( 扫描中... )")
        elif self.monitor.next_scan_time is not None:
            import time
            remaining = self.monitor.next_scan_time - time.time()
            if remaining < 0:
                remaining = 0
            self.countdown_var.set(f"( {int(remaining) + 1}s 后扫描 )")
        else:
            self.countdown_var.set("")

        # 每秒刷新
        self._countdown_after_id = self.root.after(1000, self._update_countdown)

    def _start_monitor_for_server(self, name):
        """校验服务器配置并异步启动监控（供复选框和下拉框使用）"""
        # 如果已经在自动扫描同一个服务器，直接返回
        if self.monitor.is_running and self.monitor._auto_monitor and self.monitor.monitored_name == name:
            # 定时器可能因异常中断，确保定时扫描仍在运行
            if not self.monitor._scan_timer or not self.monitor._scan_timer.is_alive():
                self.monitor._start_scan_timer()
            self._set_monitor_status(True, name)
            self.sync_btn.config(state="normal")
            self._start_countdown()
            return True

        # 正在运行其他服务器，先停止
        if self.monitor.is_running:
            self.monitor.stop()

        server = self.config.get_server(name)
        if not server:
            self.auto_scan_var.set(False)
            return False

        local_path = server.get("local_path", "")
        if not local_path or not os.path.exists(local_path):
            self.auto_scan_var.set(False)
            messagebox.showerror("错误", f"本地路径不存在或未配置: {local_path}", parent=self.root)
            return False

        # 异步启动扫描（避免卡UI）
        self._start_monitor_async(name)
        return True

    def _on_auto_scan_toggled(self):
        """自动扫描复选框状态切换"""
        if self.auto_scan_var.get():
            # 勾选：启动定时扫描（在后台线程中执行，避免卡UI）
            name = self._get_selected_server_name()
            if not name:
                self.auto_scan_var.set(False)
                return
            if not self._start_monitor_for_server(name):
                # 启动失败，取消勾选
                self.auto_scan_var.set(False)
                return
        else:
            # 取消勾选：停止定时扫描
            if self.monitor.is_running:
                self.monitor.stop()
            self._set_monitor_status(False)
            self._stop_countdown()

    # --- 待上传文件操作 ---

    def _update_pending_headings(self):
        """更新列标题显示排序箭头"""
        pheaders = {"file": "文件路径", "action": "操作类型", "time": "修改时间"}
        arrow = " ▼" if self._pending_sort_reverse else " ▲"
        for c in ("file", "action", "time"):
            base = pheaders[c]
            self.pending_tree.heading(c, text=base + (arrow if c == self._pending_sort_col else ""),
                                      command=lambda col2=c: self._sort_pending_tree(col2))

    def _sort_pending_tree(self, col, toggle=True):
        """点击列标题排序待上传列表"""
        # 切换排序方向（仅点击时切换，刷新时不切换）
        if toggle:
            if self._pending_sort_col == col:
                self._pending_sort_reverse = not self._pending_sort_reverse
            else:
                self._pending_sort_col = col
                self._pending_sort_reverse = False

        items = list(self.pending_tree.get_children(""))
        items.sort(key=lambda k: self.pending_tree.set(k, col), reverse=self._pending_sort_reverse)

        for index, k in enumerate(items):
            self.pending_tree.move(k, "", index)

        self._update_pending_headings()

    def _refresh_pending(self):
        """刷新待上传文件列表"""
        self.pending_tree.delete(*self.pending_tree.get_children())
        pending = self.monitor.get_pending()
        action_map = {
            "modify": "修改",
            "create": "新建",
            "move": "移动",
            "delete": "删除",
            "dir_create": "新建目录",
            "dir_delete": "删除目录"
        }
        for local_path, info in pending:
            action_text = action_map.get(info["action"], info["action"])
            self.pending_tree.insert("", "end",
                                     values=(info["rel"], action_text, info["time"], info["remote"]))
        count = len(pending)
        self.pending_count_var.set(f"待同步: {count} 个文件")
        # 如果之前有排序列，刷新后重新应用排序（不切换方向）
        if self._pending_sort_col:
            self._sort_pending_tree(self._pending_sort_col, toggle=False)

    def _require_selected_server(self):
        """这些操作都依赖当前服务器，未选择时只提示选择服务器。"""
        name = self.server_select_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请先选择服务器", parent=self.root)
            return None
        return name

    def _refresh_pending_with_filter(self):
        """扫描文件并刷新待上传列表（独立于自动扫描，可单独使用）"""
        name = self._require_selected_server()
        if not name:
            return

        # 禁用按钮，防止重复点击
        self.scan_btn.config(state="disabled")
        # 显示扫描中状态
        self._set_monitor_status_scan()

        # 判断是增量扫描（自动扫描运行中）还是全量一次性扫描
        if self.monitor.is_running and self.monitor._auto_monitor and self.monitor.monitored_name == name:
            def do_rescan():
                try:
                    self.monitor.rescan()
                finally:
                    self.root.after(0, self._refresh_pending)
                    self.root.after(0, self._restore_monitor_status)
                    self.root.after(0, lambda: self.scan_btn.config(state="normal"))
            threading.Thread(target=do_rescan, daemon=True).start()
        else:
            # 监控未运行，执行一次性扫描（不启动定时器）
            server = self.config.get_server(name)
            if not server:
                self._restore_monitor_status()
                self.scan_btn.config(state="normal")
                return

            local_path = server.get("local_path", "")
            if not local_path or not os.path.exists(local_path):
                messagebox.showerror("错误", f"本地路径不存在: {local_path}", parent=self.root)
                self._restore_monitor_status()
                self.scan_btn.config(state="normal")
                return

            def do_scan_once():
                try:
                    ok, msg = self.monitor.scan_once(name)
                    if not ok:
                        self.root.after(0, lambda: messagebox.showerror("错误", msg, parent=self.root))
                finally:
                    self.root.after(0, self._refresh_pending)
                    self.root.after(0, self._restore_monitor_status)
                    self.root.after(0, lambda: self.scan_btn.config(state="normal"))

            threading.Thread(target=do_scan_once, daemon=True).start()

    def _upload_selected(self):
        """手动上传选中的待上传文件"""
        if not self._require_selected_server():
            return
        sel = self.pending_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在待上传列表中选择文件", parent=self.root)
            return
        if not self._ensure_monitor_running():
            messagebox.showwarning("提示", "请先勾选「自动扫描」以启动文件监控", parent=self.root)
            return
        # 获取选中文件对应的本地路径
        pending = self.monitor.get_pending()
        pending_map = {info["rel"]: local_path for local_path, info in pending}
        paths = []
        for s in sel:
            vals = self.pending_tree.item(s, "values")
            rel = vals[0]
            if rel in pending_map:
                paths.append(pending_map[rel])
        if not paths:
            return
        self._start_upload(paths)

    def _upload_all_pending(self):
        """上传所有待上传文件"""
        if not self._require_selected_server():
            return
        pending = self.monitor.get_pending()
        if not pending:
            messagebox.showinfo("提示", "没有待上传的文件", parent=self.root)
            return
        if not self._ensure_monitor_running():
            messagebox.showwarning("提示", "请先勾选「自动扫描」以启动文件监控", parent=self.root)
            return
        paths = [p for p, info in pending]
        self._start_upload(paths)

    def _start_upload(self, paths):
        """启动上传，显示 Loading 对话框"""
        self._upload_loading = LoadingDialog(self.root, "上传中",
                                             f"正在上传 {len(paths)} 个文件，请稍候...")
        self._upload_loading.update_progress(0, len(paths), "准备中...")
        threading.Thread(target=self._do_upload_pending, args=(paths,), daemon=True).start()

    def _do_upload_pending(self, paths):
        """在子线程中执行上传，带逐文件进度"""
        # 检查是否有其他操作正在进行
        if not self._operation_lock.acquire(blocking=False):
            self.root.after(0, lambda: self._upload_loading.close())
            self.root.after(0, lambda: messagebox.showwarning("提示", "有其他操作正在进行，请稍后再试", parent=self.root))
            return
        
        try:
            self._current_operation = "upload"
            total = len(paths)
            
            def on_progress(index, total, rel_path, success, msg):
                detail = f"{'✓' if success else '✗'} {rel_path}"
                self.root.after(0, lambda i=index, t=total, d=detail: self._upload_loading.update_progress(i, t, d))
                # 每上传完一个文件就刷新待上传列表
                self.root.after(0, self._refresh_pending)

            success, fail, size, summary = self.monitor.upload_pending(paths, on_progress=on_progress)
            self.root.after(0, self._refresh_pending)
            self.root.after(0, self._refresh_servers)
            self.root.after(0, self._refresh_log)
            # 关闭 Loading 对话框，显示结果
            self.root.after(0, lambda: self._upload_loading.close())
            self.root.after(0, lambda: messagebox.showinfo("上传结果", summary, parent=self.root))
        except Exception as e:
            err = f"上传出错: {e}"
            self.root.after(0, lambda: self._upload_loading.close())
            self.root.after(0, lambda: messagebox.showerror("错误", err, parent=self.root))
        finally:
            self._current_operation = None
            self._operation_lock.release()

    def _remove_selected_pending(self):
        """从待上传列表中移除选中文件"""
        if not self._require_selected_server():
            return
        sel = self.pending_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择要移除的文件", parent=self.root)
            return
        pending = self.monitor.get_pending()
        pending_map = {info["rel"]: local_path for local_path, info in pending}
        for s in sel:
            vals = self.pending_tree.item(s, "values")
            rel = vals[0]
            if rel in pending_map:
                self.monitor.remove_pending(pending_map[rel])
        self._refresh_pending()

    # --- 右键菜单操作 ---

    def _show_pending_context_menu(self, event):
        """右键点击待上传列表时弹出上下文菜单"""
        item = self.pending_tree.identify_row(event.y)
        if item:
            # 选中右键所在的行（保留已有选区）
            if item not in self.pending_tree.selection():
                self.pending_tree.selection_set(item)
            self.pending_context_menu.tk_popup(event.x_root, event.y_root)

    def _add_to_excludes(self):
        """将选中的文件加入排除规则"""
        sel = self.pending_tree.selection()
        if not sel:
            return

        server_name = self.monitor.monitored_name or self.server_select_var.get()
        if not server_name:
            messagebox.showwarning("提示", "请先选择服务器", parent=self.root)
            return

        # 收集选中的文件信息
        pending = self.monitor.get_pending()
        pending_map = {info["rel"]: (local_path, info) for local_path, info in pending}

        selected_items = []
        for s in sel:
            vals = self.pending_tree.item(s, "values")
            rel_path = vals[0]
            if rel_path in pending_map:
                local_path, info = pending_map[rel_path]
                selected_items.append((rel_path, local_path))

        if not selected_items:
            return

        if len(selected_items) == 1:
            # 单选：弹窗让用户选择过滤类型
            rel_path, local_path = selected_items[0]
            patterns_to_add = self._show_exclude_dialog(rel_path)
            if not patterns_to_add:
                return
        else:
            # 多选：收集所有文件名，去重
            patterns_to_add = []
            for rel_path, _ in selected_items:
                filename = os.path.basename(rel_path)
                if filename not in patterns_to_add:
                    patterns_to_add.append(filename)

            preview = "\n".join(f"  · {p}" for p in patterns_to_add[:10])
            if len(patterns_to_add) > 10:
                preview += f"\n  ... 等共 {len(patterns_to_add)} 条"
            if not messagebox.askyesno("确认",
                    f"将为 {len(selected_items)} 个文件添加以下过滤规则:\n\n{preview}", parent=self.root):
                return

        if not patterns_to_add:
            return

        # 获取现有排除规则并添加新规则
        existing_patterns = self.config.get_exclude_patterns(server_name)
        new_patterns = list(existing_patterns)
        added = 0
        for p in patterns_to_add:
            if p and p not in new_patterns:
                new_patterns.append(p)
                added += 1

        if added > 0:
            self.config.update_server_excludes(server_name, new_patterns)

        # 从待上传列表中移除这些文件
        for _, local_path in selected_items:
            self.monitor.remove_pending(local_path)

        self._refresh_pending()
        messagebox.showinfo("成功", f"已添加 {added} 条过滤规则\n(可在服务器编辑中查看)", parent=self.root)

    def _show_exclude_dialog(self, rel_path):
        """弹出过滤规则选择对话框，返回选中的规则列表

        提供三种过滤方式：
          · 文件名 — 精确匹配文件名，如 app.py
          · 扩展名 — 按扩展名通配，如 *.py
          · 所在目录 — 排除该文件所在的目录，如 gui/
        """
        filename = os.path.basename(rel_path)
        _, ext = os.path.splitext(filename)
        # 计算所在目录的相对路径
        dir_part = os.path.dirname(rel_path).replace("\\", "/")
        dir_pattern = dir_part + "/" if dir_part else ""

        dialog = tk.Toplevel(self.root)
        dialog.title("加入过滤规则")
        dialog.geometry("420x340")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.configure(bg=self.CARD_BG)
        dialog.grab_set()

        # 居中到主窗口
        dialog.update_idletasks()
        px = self.root.winfo_rootx()
        py = self.root.winfo_rooty()
        pw = self.root.winfo_width()
        ph = self.root.winfo_height()
        dw = dialog.winfo_width()
        dh = dialog.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dialog.geometry(f"+{x}+{y}")

        main = ttk.Frame(dialog, style="Card.TFrame", padding=15)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text=f"文件: {rel_path}",
                  style="Bold.TLabel").pack(anchor="w", pady=(0, 12))

        choice_var = tk.StringVar(value="filename")

        # 文件名选项
        rb1_frame = ttk.Frame(main, style="Card.TFrame")
        rb1_frame.pack(fill="x", pady=4)
        ttk.Radiobutton(rb1_frame, text="按文件名", value="filename",
                        variable=choice_var).pack(side="left")
        ttk.Label(rb1_frame, text=f"  →  {filename}",
                  style="Muted.TLabel").pack(side="left", padx=(4, 0))

        # 扩展名选项
        rb2_frame = ttk.Frame(main, style="Card.TFrame")
        rb2_frame.pack(fill="x", pady=4)
        ttk.Radiobutton(rb2_frame, text="按扩展名", value="ext",
                        variable=choice_var).pack(side="left")
        ttk.Label(rb2_frame, text=f"  →  *{ext}" if ext else "  →  (无扩展名)",
                  style="Muted.TLabel").pack(side="left", padx=(4, 0))

        # 目录选项
        rb3_frame = ttk.Frame(main, style="Card.TFrame")
        rb3_frame.pack(fill="x", pady=4)
        if dir_pattern:
            ttk.Radiobutton(rb3_frame, text="按所在目录", value="dir",
                            variable=choice_var).pack(side="left")
            ttk.Label(rb3_frame, text=f"  →  {dir_pattern}",
                      style="Muted.TLabel").pack(side="left", padx=(4, 0))
        else:
            ttk.Radiobutton(rb3_frame, text="按所在目录", value="dir",
                            variable=choice_var, state="disabled").pack(side="left")
            ttk.Label(rb3_frame, text="  →  (文件在根目录，无目录可过滤)",
                      style="Muted.TLabel").pack(side="left", padx=(4, 0))

        # 自定义规则选项
        rb4_frame = ttk.Frame(main, style="Card.TFrame")
        rb4_frame.pack(fill="x", pady=4)
        ttk.Radiobutton(rb4_frame, text="自定义规则", value="custom",
                        variable=choice_var).pack(side="left")

        # 自定义输入框（默认填入目录规则，方便改动）
        custom_entry = ttk.Entry(main, width=48)
        # 默认填入目录规则，若无目录则填入文件名
        default_custom = dir_pattern if dir_pattern else filename
        custom_entry.insert(0, default_custom)
        custom_entry.pack(fill="x", pady=(4, 0))
        ttk.Label(main, text="输入自定义过滤规则，如 *.tmp、temp/、config.json",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        # 输入框获焦时自动选中"自定义规则"
        def on_entry_focus(event):
            choice_var.set("custom")
        custom_entry.bind("<FocusIn>", on_entry_focus)

        result = {"patterns": None}

        def on_confirm():
            choice = choice_var.get()
            custom = custom_entry.get().strip()
            patterns = []
            if choice == "custom":
                if custom:
                    patterns.append(custom)
            elif choice == "filename":
                patterns.append(filename)
            elif choice == "ext" and ext:
                patterns.append(f"*{ext}")
            elif choice == "dir" and dir_pattern:
                patterns.append(dir_pattern)
            result["patterns"] = patterns
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(main, style="Card.TFrame")
        btn_frame.pack(fill="x", pady=(15, 0))
        btn_inner = ttk.Frame(btn_frame, style="Card.TFrame")
        btn_inner.pack(expand=True)
        ttk.Button(btn_inner, text="确定", command=on_confirm, style="Primary.TButton", width=12).pack(side="left", padx=(0, 12))
        ttk.Button(btn_inner, text="取消", command=on_cancel, style="Danger.TButton", width=12).pack(side="left")

        dialog.after(100, lambda: dialog.focus_force())
        self.root.wait_window(dialog)
        return result["patterns"] or []

    def _delete_pending_file(self):
        """删除选中的本地文件"""
        sel = self.pending_tree.selection()
        if not sel:
            return

        # 收集选中的文件信息
        pending = self.monitor.get_pending()
        pending_map = {info["rel"]: (local_path, info) for local_path, info in pending}

        to_delete = []
        already_gone = []
        for s in sel:
            vals = self.pending_tree.item(s, "values")
            rel_path = vals[0]
            if rel_path in pending_map:
                local_path, info = pending_map[rel_path]
                action = info.get("action", "")
                # 已是删除操作的文件，本地已不存在
                if action in ("delete", "dir_delete"):
                    already_gone.append(rel_path)
                elif os.path.exists(local_path):
                    to_delete.append((rel_path, local_path))
                else:
                    already_gone.append(rel_path)

        if not to_delete:
            if already_gone:
                messagebox.showinfo("提示", "选中的文件本地已不存在或已是删除操作", parent=self.root)
            return

        # 确认删除
        file_list = "\n".join(f"  · {rp}" for rp, _ in to_delete[:15])
        if len(to_delete) > 15:
            file_list += f"\n  ... 等共 {len(to_delete)} 个"
        if not messagebox.askyesno("确认删除",
                f"确定删除以下本地文件吗？\n\n{file_list}\n\n此操作不可恢复！", parent=self.root):
            return

        # 执行删除
        success = []
        fail = []
        for rel_path, local_path in to_delete:
            try:
                if os.path.isfile(local_path):
                    os.remove(local_path)
                elif os.path.isdir(local_path):
                    shutil.rmtree(local_path)
                success.append(rel_path)
                self.monitor.remove_pending(local_path)
                self.monitor.remove_from_snapshot(local_path)
            except Exception as e:
                fail.append(f"{rel_path}: {e}")

        self._refresh_pending()

        if fail:
            messagebox.showerror("部分失败",
                f"成功删除 {len(success)} 个, 失败 {len(fail)} 个:\n\n" +
                "\n".join(fail[:10]), parent=self.root)
        else:
            messagebox.showinfo("成功", f"已删除 {len(success)} 个文件", parent=self.root)

    # --- 全量同步 ---

    def _full_sync(self):
        name = self._get_selected_server_name()
        if not name:
            return
        server = self.config.get_server(name)
        if not server:
            return
        local_path = server.get("local_path", "")
        if not local_path or not os.path.exists(local_path):
            messagebox.showerror("错误", f"本地路径不存在或未配置: {local_path}", parent=self.root)
            return

        # 确认提示
        remote_path = server.get("remote_path", "/")
        if not messagebox.askyesno("确认拉取", 
            f"确定要拉取远程服务器的全部文件吗？\n\n"
            f"服务器: {name}\n"
            f"远程路径: {remote_path}\n"
            f"本地路径: {local_path}\n\n"
            f"此操作将下载远程目录中的所有文件到本地，\n"
            f"如果文件较多可能需要较长时间。", parent=self.root):
            return

        # 检查是否有其他操作正在进行
        if not self._operation_lock.acquire(blocking=False):
            messagebox.showwarning("提示", "有其他操作正在进行，请稍后再试", parent=self.root)
            return
        
        self._stop_requested = False
        self._current_operation = "sync"
        
        # 更新按钮状态：同步期间禁用所有操作按钮（包括连接）
        self.root.after(0, lambda: self._set_download_buttons_state(False, busy=True))
        self.root.after(0, lambda: self.stop_btn.config(state="normal"))
        
        self._set_status("正在连接服务器并同步...")
        threading.Thread(target=self._do_full_sync, args=(server,), daemon=True).start()

    def _stop_operation(self):
        """停止当前正在进行的操作"""
        self._stop_requested = True
        self._set_status("正在停止操作...")
    
    def _do_full_sync(self, server):
        try:
            ok, msg = self.ftp.connect(
                server["host"], server["port"], server["username"], server["password"],
                use_tls=bool(server.get("use_tls")))
            if not ok:
                self.root.after(0, lambda: messagebox.showerror("错误", msg, parent=self.root))
                self.root.after(0, lambda: self._set_status(msg))
                return
            self.root.after(0, lambda: self._set_status("拉取文件同步中... (点击停止可中断)"))

            def cb(rel, action, success, message):
                # 检查是否请求停止
                if self._stop_requested:
                    raise KeyboardInterrupt("用户停止")
                self.root.after(0, lambda: self._set_status(f"{'✓' if success else '✗'} {rel}"))

            count, size, summary = self.ftp.sync_directory(
                server.get("local_path", ""), server.get("remote_path", "/"),
                exclude_patterns=self.config.get_exclude_patterns(server["name"]),
                callback=cb)
            
            if self._stop_requested:
                summary = "同步已停止"
            
            # 更新同步统计
            s = self.config.get_server(server["name"])
            if s and not self._stop_requested:
                s["sync_count"] = s.get("sync_count", 0) + count
                s["last_sync"] = datetime.now().isoformat()
                self.config.save()
            self.ftp.disconnect()
            self.root.after(0, lambda: self._set_status(summary))
            if not self._stop_requested:
                self.root.after(0, lambda: messagebox.showinfo(
                    "同步完成", f"{summary}\n总大小: {size/1024:.1f} KB", parent=self.root))
            else:
                self.root.after(0, lambda: messagebox.showinfo("提示", "同步已停止", parent=self.root))
            self.root.after(0, self._refresh_servers)
        except KeyboardInterrupt:
            self.ftp.disconnect()
        except Exception as e:
            err = f"拉取文件同步出错: {e}"
            self.root.after(0, lambda: self._set_status(err))
            self.root.after(0, lambda: messagebox.showerror("错误", err, parent=self.root))
        finally:
            self._current_operation = None
            self._stop_requested = False
            self._operation_lock.release()
            # 恢复按钮状态（同步结束后FTP已断开，所有操作按钮保持禁用，连接按钮恢复可用）
            self.root.after(0, lambda: self._set_download_buttons_state(False, busy=False))
            self.root.after(0, lambda: self.stop_btn.config(state="disabled"))

    # ======================== 下载文件 Tab ========================

    def _build_download_tab(self):
        """构建下载文件标签页 - 使用当前选中的服务器"""
        frame = self.download_frame
        
        main_frame = ttk.Frame(frame, style="Card.TFrame")
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # --- 顶部工具栏：主要操作（卡片式） ---
        toolbar = ttk.Frame(main_frame, style="Card.TFrame", padding=(12, 10))
        toolbar.pack(fill="x", pady=(0, 10))
        
        # 当前服务器显示
        ttk.Label(toolbar, text="服务器:", style="Bold.TLabel").pack(side="left", padx=(0, 4))
        self.download_current_server_var = tk.StringVar(value="未选择")
        ttk.Label(toolbar, textvariable=self.download_current_server_var, 
                  style="Primary.TLabel").pack(side="left", padx=(0, 20))
        
        # 主要操作按钮（紧凑实心风格）
        self.sync_btn = ttk.Button(toolbar, text="📥 拉取文件", command=self._full_sync, style="Compact.Primary.TButton", state="disabled")
        self.sync_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(toolbar, text="⏹ 停止", command=self._stop_operation, style="Compact.Danger.TButton", state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=12)
        
        # 连接控制
        self.download_btn_connect = ttk.Button(toolbar, text="🔗 连接", command=self._download_connect, style="Compact.Success.TButton")
        self.download_btn_connect.pack(side="left", padx=2)
        self.download_btn_disconnect = ttk.Button(toolbar, text="🔌 断开", command=self._download_disconnect, style="Compact.Danger.TButton", state="disabled")
        self.download_btn_disconnect.pack(side="left", padx=2)
        
        # --- 远程文件浏览区（卡片式） ---
        browser_group = ttk.LabelFrame(main_frame, text="📂 远程文件浏览", padding=12)
        browser_group.pack(fill="both", expand=True)
        
        # 工具栏：路径和操作（合并为一行）
        toolbar1 = ttk.Frame(browser_group, style="Card.TFrame")
        toolbar1.pack(fill="x", pady=(0, 8))
        
        ttk.Label(toolbar1, text="路径:", style="Bold.TLabel").pack(side="left")
        self.download_path_var = tk.StringVar(value="/")
        path_entry = ttk.Entry(toolbar1, textvariable=self.download_path_var, width=35)
        path_entry.pack(side="left", padx=6, fill="x", expand=True)
        self.download_btn_navigate = ttk.Button(toolbar1, text="进入", command=self._download_navigate, style="Compact.Primary.TButton", state="disabled")
        self.download_btn_navigate.pack(side="left", padx=2)
        
        ttk.Separator(toolbar1, orient="vertical").pack(side="left", fill="y", padx=8)
        self.download_btn_up = ttk.Button(toolbar1, text="⬆ 上级", command=self._download_up, style="Toolbar.TButton", state="disabled")
        self.download_btn_up.pack(side="left", padx=2)
        self.download_btn_refresh = ttk.Button(toolbar1, text="🔄 刷新", command=self._download_refresh, style="Compact.Success.TButton", state="disabled")
        self.download_btn_refresh.pack(side="left", padx=2)
        self.download_btn_mkdir = ttk.Button(toolbar1, text="📁 新建", command=self._download_mkdir, style="Compact.Warning.TButton", state="disabled")
        self.download_btn_mkdir.pack(side="left", padx=2)
        self.download_btn_delete = ttk.Button(toolbar1, text="🗑 删除", command=self._download_delete, style="Compact.Danger.TButton", state="disabled")
        self.download_btn_delete.pack(side="left", padx=2)
        
        # 下载按钮（右侧突出显示）
        self.download_btn_download = ttk.Button(toolbar1, text="⬇ 下载选中", command=self._download_selected, style="Primary.TButton", state="disabled")
        self.download_btn_download.pack(side="right", padx=(8, 0))
        
        # 文件列表
        list_frame = ttk.Frame(browser_group, style="Card.TFrame")
        list_frame.pack(fill="both", expand=True)
        
        cols = ("name", "type", "size", "date")
        self.download_tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=15)
        # 排序状态
        self._dl_sort_col = "name"
        self._dl_sort_reverse = False
        self._dl_user_sorted = False  # 用户是否手动点击过列标题排序
        dheaders = {"name": "名称", "type": "类型", "size": "大小", "date": "日期"}
        for c in cols:
            self.download_tree.heading(c, text=dheaders[c],
                                       command=lambda col=c: self._sort_download_tree(col))
        self.download_tree.column("name", width=280, minwidth=150)
        self.download_tree.column("type", width=60, anchor="center")
        self.download_tree.column("size", width=90, anchor="e")
        self.download_tree.column("date", width=130)
        self.download_tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.download_tree.yview)
        self.download_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        # 目录/文件行的视觉区分
        self.download_tree.tag_configure("dir", foreground=self.PRIMARY,
                                         font=("Microsoft YaHei UI", 10, "bold"))
        self.download_tree.tag_configure("file", foreground=self.TEXT_PRIMARY)
        
        # 双击进入目录
        self.download_tree.bind("<Double-1>", self._on_download_double_click)
        # 右键上下文菜单
        self.download_context_menu = tk.Menu(self.download_tree, tearoff=0,
                                            font=("Microsoft YaHei UI", 9))
        self.download_context_menu.add_command(label="⬇ 下载选中", command=self._download_selected)
        self.download_context_menu.add_command(label="📂 进入目录", command=self._download_enter_dir)
        self.download_context_menu.add_separator()
        self.download_context_menu.add_command(label="🗑 删除", command=self._download_delete)
        self.download_context_menu.add_separator()
        self.download_context_menu.add_command(label="🔄 刷新", command=self._download_refresh)
        self.download_tree.bind("<Button-3>", self._show_download_context_menu)
        
        # 提示信息
        hint_frame = ttk.Frame(browser_group, style="Card.TFrame")
        hint_frame.pack(fill="x", pady=(6, 0))
        ttk.Label(hint_frame, text='💡 提示: 双击目录进入，选中文件/目录后点击右侧"下载选中"按钮',
                 style="Muted.TLabel").pack(side="left")
        
        # 初始化显示当前服务器
        self._update_download_server_display()

    def _set_download_buttons_state(self, enabled, busy=False):
        """统一启用/禁用下载Tab中所有依赖连接的操作按钮。

        Args:
            enabled: True=已连接（启用操作按钮），False=未连接（禁用操作按钮）
            busy: True=正在执行耗时操作（如同步），此时连接按钮也禁用
        """
        state = "normal" if enabled else "disabled"
        self.sync_btn.config(state=state)
        self.download_btn_disconnect.config(state=state)
        self.download_btn_navigate.config(state=state)
        self.download_btn_up.config(state=state)
        self.download_btn_refresh.config(state=state)
        self.download_btn_mkdir.config(state=state)
        self.download_btn_delete.config(state=state)
        self.download_btn_download.config(state=state)
        # 连接按钮：已连接或忙碌时禁用，否则启用
        self.download_btn_connect.config(state="disabled" if (enabled or busy) else "normal")

    def _show_download_wait(self, message):
        """连接或断开时的等待动画，避免界面看起来像没有响应。"""
        self._close_download_wait()
        dialog = tk.Toplevel(self.root)
        dialog.title("请稍候")
        dialog.geometry("340x130")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.configure(bg=self.CARD_BG)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - 340) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 130) // 2
        dialog.geometry(f"+{x}+{y}")

        spinner = tk.Label(
            dialog, text="◐", font=("Segoe UI Symbol", 22),
            bg=self.CARD_BG, fg=self.PRIMARY,
        )
        spinner.pack(pady=(18, 4))
        message_label = tk.Label(
            dialog, text=message, wraplength=300,
            font=("Microsoft YaHei UI", 10), bg=self.CARD_BG, fg=self.TEXT_PRIMARY,
        )
        message_label.pack()
        hint = tk.Label(
            dialog, text="已等待 0 秒",
            font=("Microsoft YaHei UI", 9), bg=self.CARD_BG, fg=self.TEXT_MUTED,
        )
        hint.pack(pady=(2, 0))

        frames = ("◐", "◓", "◑", "◒")
        state = {"index": 0, "after_id": None, "ticks": 0}

        def tick():
            state["index"] = (state["index"] + 1) % len(frames)
            state["ticks"] += 1
            if dialog.winfo_exists():
                spinner.config(text=frames[state["index"]])
                extra = state.get("hint")
                waited = f"已等待 {state['ticks'] // 2} 秒"
                hint.config(text=f"{extra}，{waited}" if extra else waited)
                state["after_id"] = dialog.after(500, tick)

        state["after_id"] = dialog.after(500, tick)
        self._download_wait = {
            "dialog": dialog, "state": state,
            "message": message_label, "hint": hint,
        }
        dialog.grab_set()
        self._set_status(message)

    def _update_download_wait(self, message, hint=None):
        """更新已打开的等待窗文字，不重置动画。"""
        wait = getattr(self, "_download_wait", None)
        if not wait or not wait["dialog"].winfo_exists():
            return
        wait["message"].config(text=message)
        if hint is not None:
            wait["state"]["hint"] = hint
        self._set_status(message)

    def _close_download_wait(self):
        wait = getattr(self, "_download_wait", None)
        self._download_wait = None
        if not wait:
            return
        dialog = wait["dialog"]
        after_id = wait["state"].get("after_id")
        if after_id and dialog.winfo_exists():
            dialog.after_cancel(after_id)
        if dialog.winfo_exists():
            dialog.grab_release()
            dialog.destroy()

    def _download_connect(self):
        """连接到当前选中的服务器（使用服务器管理中的选择）"""
        name = self.server_select_var.get()
        if not name:
            messagebox.showwarning("提示", "请先在服务器管理中选择服务器", parent=self.root)
            return
        server = self.config.get_server(name)
        if not server:
            messagebox.showwarning("提示", "服务器配置不存在", parent=self.root)
            return
        # 禁用所有按钮，防止重复点击
        self._set_download_buttons_state(False, busy=True)
        self._show_download_wait(f"正在连接 {server['host']}:{server.get('port', 21)}")
        threading.Thread(target=self._do_download_connect, args=(server,), daemon=True).start()

    def _do_download_connect(self, server):
        """在子线程中执行连接"""
        try:
            ok, msg = self.ftp.connect(
                server["host"], server["port"], server["username"], server["password"],
                use_tls=bool(server.get("use_tls")))
            if not ok:
                self.root.after(0, self._close_download_wait)
                self.root.after(0, lambda: messagebox.showerror("错误", msg, parent=self.root))
                self.root.after(0, lambda: self._set_status(msg))
                self.root.after(0, lambda: self._set_download_buttons_state(False))
                return
            try:
                self.ftp.cwd(server.get("remote_path", "/"))
            except Exception:
                pass
            pwd = self.ftp.pwd()
            items, list_msg = self.ftp.list_dir(pwd)
            self.root.after(0, lambda: self.download_path_var.set(pwd))
            self.root.after(0, lambda: self._populate_download_tree(items, list_msg))
            self.root.after(0, self._close_download_wait)
            self.root.after(0, lambda: self._set_status(f"已连接到 {server['host']}"))
            # 连接成功，启用所有操作按钮
            self.root.after(0, lambda: self._set_download_buttons_state(True))
        except Exception as e:
            err = f"连接失败: {e}"
            self.root.after(0, self._close_download_wait)
            self.root.after(0, lambda: self._set_status(err))
            self.root.after(0, lambda: messagebox.showerror("错误", err, parent=self.root))
            self.root.after(0, lambda: self._set_download_buttons_state(False))

    def _download_disconnect(self):
        """断开连接（异步执行，避免阻塞GUI）"""
        # 先禁用所有按钮，防止重复操作
        self._set_download_buttons_state(False, busy=True)
        self._show_download_wait("正在断开连接")

        def _do_disconnect():
            try:
                self.ftp.disconnect()
            except Exception:
                pass
            self.root.after(0, self._close_download_wait)
            self.root.after(0, lambda: self.download_tree.delete(*self.download_tree.get_children()))
            self.root.after(0, lambda: self._set_download_buttons_state(False))
            self.root.after(0, lambda: self._set_status("已断开连接"))

        threading.Thread(target=_do_disconnect, daemon=True).start()

    def _update_download_headings(self):
        """更新远程文件列表列标题的排序箭头"""
        dheaders = {"name": "名称", "type": "类型", "size": "大小", "date": "日期"}
        arrow = " ▼" if self._dl_sort_reverse else " ▲"
        for c in ("name", "type", "size", "date"):
            base = dheaders[c]
            self.download_tree.heading(c, text=base + (arrow if c == self._dl_sort_col else ""),
                                       command=lambda col2=c: self._sort_download_tree(col2))

    def _sort_download_tree(self, col):
        """用户手动点击列标题排序远程文件列表。
        手动排序后不再强制目录在前，纯粹按用户选择的列排序。
        """
        if self._dl_sort_col == col:
            self._dl_sort_reverse = not self._dl_sort_reverse
        else:
            self._dl_sort_col = col
            self._dl_sort_reverse = False
        self._dl_user_sorted = True  # 标记用户已手动排序

        def sort_key(item_id):
            vals = self.download_tree.item(item_id, "values")
            if col == "name":
                return vals[0].lower()
            elif col == "size":
                return _parse_size(vals[2])
            elif col == "type":
                return (vals[1], vals[0].lower())
            elif col == "date":
                return vals[3]
            return ""

        items = list(self.download_tree.get_children(""))
        items.sort(key=sort_key, reverse=self._dl_sort_reverse)
        for index, item_id in enumerate(items):
            self.download_tree.move(item_id, "", index)
        self._update_download_headings()

    def _reapply_download_sort(self):
        """刷新/进入目录后重新应用当前排序状态。
        - 用户未手动排序时：目录在前 + 按名称升序（默认排序）
        - 用户已手动排序后：保持用户的排序方式不变
        """
        if not self._dl_user_sorted:
            # 默认排序：目录在前，再按名称排序
            def default_key(item_id):
                vals = self.download_tree.item(item_id, "values")
                is_dir = "目录" in vals[1]
                return (0 if is_dir else 1, vals[0].lower())
            items = list(self.download_tree.get_children(""))
            items.sort(key=default_key)
            for index, item_id in enumerate(items):
                self.download_tree.move(item_id, "", index)
        else:
            # 保持用户手动选择的排序方式
            col = self._dl_sort_col

            def user_key(item_id):
                vals = self.download_tree.item(item_id, "values")
                if col == "name":
                    return vals[0].lower()
                elif col == "size":
                    return _parse_size(vals[2])
                elif col == "type":
                    return (vals[1], vals[0].lower())
                elif col == "date":
                    return vals[3]
                return ""

            items = list(self.download_tree.get_children(""))
            items.sort(key=user_key, reverse=self._dl_sort_reverse)
            for index, item_id in enumerate(items):
                self.download_tree.move(item_id, "", index)
        self._update_download_headings()

    def _populate_download_tree(self, items, msg="", is_refresh=False):
        """填充下载页面的文件树
        
        Args:
            is_refresh: True=刷新（保持用户排序方式）; False=进入目录/连接（恢复默认排序）
        """
        self.download_tree.delete(*self.download_tree.get_children())
        if msg and msg != "OK":
            self._set_status(msg)
            return
        # 过滤 . 和 .. 条目
        filtered = [item for item in items if item["name"] not in (".", "..")]
        # 默认排序：目录在前，再按名称排序
        filtered.sort(key=lambda x: (0 if x["is_dir"] else 1, x["name"].lower()))
        for item in filtered:
            name = item["name"]
            is_dir = item["is_dir"]
            ftype = "📁 目录" if is_dir else "📄 文件"
            size = f"{item['size']:,}" if not is_dir else "—"
            tag = "dir" if is_dir else "file"
            self.download_tree.insert("", "end",
                                     text=name,
                                     values=(name, ftype, size, item.get("date", "")),
                                     tags=(tag,),
                                     open=False)
        self._set_status(f"共 {len(filtered)} 项")
        # 进入目录/连接时恢复默认排序；刷新时保持用户排序方式
        if not is_refresh:
            self._dl_user_sorted = False
            self._dl_sort_col = "name"
            self._dl_sort_reverse = False
        self._reapply_download_sort()

    def _on_download_double_click(self, event=None):
        """双击进入目录"""
        self._download_enter_dir()

    def _download_enter_dir(self):
        """进入选中的目录"""
        sel = self.download_tree.selection()
        if not sel:
            return
        vals = self.download_tree.item(sel[0], "values")
        name = vals[0]
        ftype = vals[1]
        if "目录" in ftype:
            current = self.download_path_var.get().rstrip("/")
            new_path = f"{current}/{name}"
            self._do_download_navigate(new_path)

    def _show_download_context_menu(self, event):
        """右键点击远程文件列表时弹出上下文菜单"""
        item = self.download_tree.identify_row(event.y)
        if item:
            # 选中右键所在的行
            if item not in self.download_tree.selection():
                self.download_tree.selection_set(item)
            self.download_context_menu.tk_popup(event.x_root, event.y_root)

    def _download_up(self):
        """返回上级目录"""
        current = self.download_path_var.get().rstrip("/")
        if current and current != "/":
            parent = "/".join(current.split("/")[:-1]) or "/"
            self._do_download_navigate(parent)

    def _download_navigate(self):
        """进入路径输入框中的目录"""
        path = self.download_path_var.get().strip()
        if not path:
            path = "/"
        self._do_download_navigate(path)

    def _do_download_navigate(self, path):
        """导航到指定路径"""
        if not self.ftp.is_connected:
            self._set_status("未连接服务器")
            return
        self._show_download_wait(f"正在进入 {path}")
        threading.Thread(target=self._do_download_navigate_thread, args=(path,), daemon=True).start()

    def _do_download_navigate_thread(self, path, is_refresh=False):
        """在子线程中执行导航"""
        try:
            ok, msg = self.ftp.cwd(path)
            if ok:
                pwd = self.ftp.pwd()
                items, list_msg = self.ftp.list_dir(pwd)
                self.root.after(0, self._close_download_wait)
                self.root.after(0, lambda: self.download_path_var.set(pwd))
                self.root.after(0, lambda: self._populate_download_tree(items, list_msg, is_refresh=is_refresh))
                self.root.after(0, lambda: self._set_status(f"已进入 {pwd}"))
            else:
                self.root.after(0, self._close_download_wait)
                self.root.after(0, lambda: self._set_status(f"进入目录失败: {msg}"))
        except Exception as e:
            self.root.after(0, self._close_download_wait)
            self.root.after(0, lambda: self._set_status(f"导航失败: {e}"))

    def _download_refresh(self):
        """刷新当前目录"""
        if not self.ftp.is_connected:
            self._set_status("未连接服务器")
            return
        path = self.download_path_var.get()
        self._show_download_wait("正在刷新")
        threading.Thread(target=self._do_download_navigate_thread, args=(path,), kwargs={"is_refresh": True}, daemon=True).start()

    def _download_mkdir(self):
        """新建目录"""
        if not self.ftp.is_connected:
            messagebox.showwarning("提示", "请先连接服务器", parent=self.root)
            return
        name = askstring("新建目录", "请输入目录名称:", parent=self.root)
        if not name:
            return
        if "/" in name or "\\" in name:
            messagebox.showwarning("提示", "目录名称不能包含路径分隔符", parent=self.root)
            return
        current = self.download_path_var.get()
        new_path = f"{current}/{name}".replace("//", "/")
        self._show_download_wait(f"正在创建目录 {name}")
        threading.Thread(target=self._do_download_mkdir, args=(new_path,), daemon=True).start()

    def _do_download_mkdir(self, path):
        """在子线程中创建目录"""
        try:
            ok, msg = self.ftp.mkdir(path)
            if ok:
                self.root.after(0, lambda: self._set_status(f"✓ 创建目录成功"))
                current = self.download_path_var.get()
                self.root.after(0, lambda: self._do_download_navigate(current))
            else:
                self.root.after(0, self._close_download_wait)
                self.root.after(0, lambda: self._set_status(f"创建目录失败: {msg}"))
        except Exception as e:
            self.root.after(0, self._close_download_wait)
            self.root.after(0, lambda: self._set_status(f"创建目录出错: {e}"))

    def _download_delete(self):
        """删除选中的文件或目录"""
        if not self.ftp.is_connected:
            messagebox.showwarning("提示", "请先连接服务器", parent=self.root)
            return
        sel = self.download_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择要删除的文件或目录", parent=self.root)
            return
        vals = self.download_tree.item(sel[0], "values")
        name, ftype = vals[0], vals[1]
        current = self.download_path_var.get()
        remote_path = f"{current}/{name}".replace("//", "/")
        
        if "目录" in ftype:
            if not messagebox.askyesno("确认删除", f"确定删除目录 '{name}' 及其所有内容吗？\n此操作不可恢复！", parent=self.root):
                return
        else:
            if not messagebox.askyesno("确认删除", f"确定删除文件 '{name}' 吗？\n此操作不可恢复！", parent=self.root):
                return
        
        self._show_download_wait(f"正在删除 {name}")
        threading.Thread(target=self._do_download_delete, args=(remote_path, ftype), daemon=True).start()

    def _do_download_delete(self, remote_path, ftype):
        """在子线程中执行删除"""
        try:
            if "目录" in ftype:
                ok, msg = self.ftp.delete_directory(remote_path)
            else:
                ok, msg = self.ftp.delete_file(remote_path)
            
            if ok:
                self.root.after(0, lambda: self._set_status(f"✓ 删除成功"))
                current = self.download_path_var.get()
                self.root.after(0, lambda: self._do_download_navigate(current))
            else:
                self.root.after(0, self._close_download_wait)
                self.root.after(0, lambda: self._set_status(f"删除失败: {msg}"))
        except Exception as e:
            self.root.after(0, self._close_download_wait)
            self.root.after(0, lambda: self._set_status(f"删除出错: {e}"))

    def _download_selected(self):
        """下载选中的文件或目录"""
        if not self.ftp.is_connected:
            messagebox.showwarning("提示", "请先连接服务器", parent=self.root)
            return
        sel = self.download_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择要下载的文件或目录", parent=self.root)
            return
        
        vals = self.download_tree.item(sel[0], "values")
        name, ftype = vals[0], vals[1]
        
        # 获取当前服务器配置的本地目录（使用服务器管理中选中的服务器）
        server_name = self.server_select_var.get()
        server = self.config.get_server(server_name)
        if not server:
            messagebox.showwarning("提示", "无法获取服务器配置", parent=self.root)
            return
        
        local_base = server.get("local_path", "")
        if not local_base:
            messagebox.showwarning("提示", "请先配置本地路径", parent=self.root)
            return
        if not os.path.exists(local_base):
            messagebox.showerror("错误", f"本地路径不存在: {local_base}", parent=self.root)
            return
        
        # 构建远程路径
        remote_path = f"{self.download_path_var.get()}/{name}".replace("//", "/")
        
        # 构建本地保存路径（保持目录结构）
        remote_base = server.get("remote_path", "/")
        if remote_path.startswith(remote_base):
            rel_path = remote_path[len(remote_base):].lstrip("/")
        else:
            rel_path = name
        
        local_path = os.path.join(local_base, rel_path.replace("/", os.sep))
        
        # 执行下载
        if "目录" in ftype:
            if not messagebox.askyesno("确认", f"确定下载目录 '{name}' 及其所有内容吗？", parent=self.root):
                return
            self._show_download_wait(f"正在下载目录 {name}")
            threading.Thread(target=self._do_download_directory,
                           args=(server, remote_path, local_path), daemon=True).start()
        else:
            # 确保父目录存在
            local_dir = os.path.dirname(local_path)
            if not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
            
            self._show_download_wait(f"正在下载 {name}")
            threading.Thread(target=self._do_download_single,
                           args=(server, remote_path, local_path), daemon=True).start()

    def _do_download_single(self, server, remote_path, local_path):
        """下载单个文件"""
        try:
            ok, msg = self.ftp.download_file(remote_path, local_path)
            self.root.after(0, self._close_download_wait)
            if ok:
                file_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
                self.config.add_log_entry(server["name"], "download", 
                                         os.path.basename(remote_path), "success", msg, file_size)
                # 状态栏提示 + 弹窗提示
                fname = os.path.basename(remote_path)
                self.root.after(0, lambda: self._set_status(f"✓ 下载完成: {fname}"))
                self.root.after(0, lambda: messagebox.showinfo("下载成功", f"文件下载成功！\n\n文件名: {fname}\n大小: {file_size:,} 字节\n保存到: {local_path}", parent=self.root))
            else:
                self.config.add_log_entry(server["name"], "download", 
                                         os.path.basename(remote_path), "error", msg)
                self.root.after(0, lambda: self._set_status(f"✗ 下载失败: {msg}"))
                self.root.after(0, lambda: messagebox.showerror("下载失败", f"文件下载失败！\n\n文件名: {os.path.basename(remote_path)}\n错误: {msg}", parent=self.root))
        except Exception as e:
            self.root.after(0, self._close_download_wait)
            self.root.after(0, lambda: self._set_status(f"下载出错: {e}"))
            self.root.after(0, lambda: messagebox.showerror("下载错误", f"下载过程中发生错误！\n\n错误信息: {str(e)}", parent=self.root))

    def _do_download_directory(self, server, remote_path, local_path):
        """递归下载整个目录"""
        try:
            dir_name = os.path.basename(remote_path)
            self.root.after(0, lambda: self._update_download_wait(f"正在下载目录 {dir_name}"))
            
            # 创建本地目录
            if not os.path.exists(local_path):
                os.makedirs(local_path, exist_ok=True)
            
            success_count = 0
            fail_count = 0
            total_size = 0
            
            def download_recursive(r_path, l_path):
                nonlocal success_count, fail_count, total_size
                
                # 列出远程目录内容
                items, _ = self.ftp.list_dir(r_path)
                
                for item in items:
                    item_name = item["name"]
                    
                    # 跳过 . 和 .. 目录
                    if item_name in (".", ".."):
                        continue
                    
                    # 规范化远程路径
                    if r_path.endswith("/"):
                        item_remote = f"{r_path}{item_name}"
                    else:
                        item_remote = f"{r_path}/{item_name}"
                    
                    item_local = os.path.join(l_path, item_name)
                    
                    if item["is_dir"]:
                        # 递归下载子目录
                        if not os.path.exists(item_local):
                            os.makedirs(item_local, exist_ok=True)
                        download_recursive(item_remote, item_local)
                    else:
                        # 下载文件
                        self.root.after(0, lambda n=item_name, c=success_count + fail_count: self._update_download_wait(
                            f"正在下载 {n}", f"已完成 {c} 个文件"))
                        ok, msg = self.ftp.download_file(item_remote, item_local)
                        if ok:
                            file_size = os.path.getsize(item_local) if os.path.exists(item_local) else 0
                            success_count += 1
                            total_size += file_size
                        else:
                            fail_count += 1
                            print(f"[WARN] 下载失败: {item_remote} - {msg}")
            
            download_recursive(remote_path, local_path)
            
            # 记录日志
            dir_name = os.path.basename(remote_path)
            self.config.add_log_entry(server["name"], "download", 
                                     dir_name, "success", 
                                     f"目录下载完成: {success_count} 个文件", total_size)
            
            # 状态栏提示 + 弹窗提示
            self.root.after(0, self._close_download_wait)
            self.root.after(0, lambda: self._set_status(f"✓ 目录下载完成: {dir_name}"))
            self.root.after(0, lambda: messagebox.showinfo("下载成功", f"目录下载成功！\n\n目录名: {dir_name}\n保存到: {local_path}", parent=self.root))
            
        except Exception as e:
            self.config.add_log_entry(server["name"], "download", 
                                     os.path.basename(remote_path), "error", str(e))
            self.root.after(0, self._close_download_wait)
            self.root.after(0, lambda: self._set_status(f"目录下载失败: {e}"))
            self.root.after(0, lambda: messagebox.showerror("下载失败", f"目录下载失败！\n\n错误: {e}", parent=self.root))

    # --- 下载文件 ---

    def _download_files(self):
        """从选中服务器的远程路径下载文件到配置的本地目录"""
        name = self._get_selected_server_name()
        if not name:
            return
        server = self.config.get_server(name)
        if not server:
            return
        
        # 获取配置的本地目录
        local_dir = server.get("local_path", "")
        if not local_dir:
            messagebox.showwarning("提示", "请先配置本地路径", parent=self.root)
            return
        if not os.path.exists(local_dir):
            messagebox.showerror("错误", f"本地路径不存在: {local_dir}", parent=self.root)
            return
        
        # 先弹出远程文件选择对话框
        dlg = RemoteFilePickerDialog(self.root, self.ftp, server, server.get("remote_path", "/"))
        self.root.wait_window(dlg.top)
        if not dlg.selected_files:
            return
        
        self._set_status(f"正在从 {server['host']} 下载到 {local_dir}...")
        threading.Thread(target=self._do_download_files,
                         args=(server, dlg.selected_files, local_dir), daemon=True).start()

    def _do_download_files(self, server, remote_files, local_dir):
        # 检查是否有其他操作正在进行
        if not self._operation_lock.acquire(blocking=False):
            self.root.after(0, lambda: messagebox.showwarning("提示", "有其他操作正在进行，请稍后再试", parent=self.root))
            return
        
        try:
            self._current_operation = "download"
            
            # 临时暂停扫描，避免下载的文件被检测为新增文件
            was_monitoring = self.monitor.is_running
            monitored_name = self.monitor.monitored_name
            if was_monitoring:
                print("[DEBUG] 临时暂停扫描，防止下载文件触发上传")
                self.monitor.stop()
            
            ok, msg = self.ftp.connect(
                server["host"], server["port"], server["username"], server["password"],
                use_tls=bool(server.get("use_tls")))
            if not ok:
                self.root.after(0, lambda: messagebox.showerror("错误", msg, parent=self.root))
                self.root.after(0, lambda: self._set_status(msg))
                return
            
            success_count = 0
            fail_count = 0
            total_size = 0
            
            for remote_path in remote_files:
                fname = os.path.basename(remote_path)
                
                # 检查是文件还是目录
                try:
                    items, _ = self.ftp.list_dir(remote_path)
                    is_dir = len(items) > 0 and any(item["is_dir"] for item in items) or False
                    # 更准确的判断：尝试列出该路径的内容
                    # 如果能列出内容且有子项，说明是目录
                    try:
                        # 尝试切换到该路径
                        old_pwd = self.ftp.pwd()
                        self.ftp.cwd(remote_path)
                        new_pwd = self.ftp.pwd()
                        self.ftp.cwd(old_pwd)
                        # 如果路径存在且能进入，说明是目录
                        is_dir = True
                    except Exception:
                        is_dir = False
                except Exception as e:
                    print(f"[DEBUG] 检查路径类型出错: {e}, 假设为文件")
                    is_dir = False
                
                local_path = os.path.join(local_dir, fname)
                
                if is_dir:
                    # 是目录，递归下载
                    print(f"[DEBUG] 检测到目录: {remote_path}，开始递归下载")
                    dir_ok, dir_count, dir_size = self._download_directory_recursive(
                        server, remote_path, local_path)
                    if dir_ok:
                        success_count += dir_count
                        total_size += dir_size
                        self.config.add_log_entry(server["name"], "download", fname, 
                                                  "success", f"目录下载完成: {dir_count} 个文件", dir_size)
                        self.root.after(0, lambda n=fname: self._set_status(f"✓ 下载目录 {n}"))
                    else:
                        fail_count += 1
                        self.config.add_log_entry(server["name"], "download", fname, "error", "目录下载失败")
                        self.root.after(0, lambda n=fname: self._set_status(f"✗ {n} (目录)"))
                else:
                    # 是文件，直接下载
                    ok, msg = self.ftp.download_file(remote_path, local_path)
                    if ok:
                        file_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
                        success_count += 1
                        total_size += file_size
                        self.config.add_log_entry(server["name"], "download", fname, "success", msg, file_size)
                        self.root.after(0, lambda n=fname: self._set_status(f"✓ 下载 {n}"))
                    else:
                        fail_count += 1
                        self.config.add_log_entry(server["name"], "download", fname, "error", msg)
                        self.root.after(0, lambda n=fname: self._set_status(f"✗ {n}"))
            
            self.ftp.disconnect()
            
            # 恢复扫描
            if was_monitoring:
                print("[DEBUG] 恢复扫描")
                self.monitor.start(monitored_name)
            
            summary = f"下载完成: {success_count}/{len(remote_files)} 个文件, 共 {total_size/1024:.1f} KB"
            self.root.after(0, lambda: self._set_status(summary))
            self.root.after(0, lambda: messagebox.showinfo("下载完成", summary, parent=self.root))
            self.root.after(0, self._refresh_log)
        except Exception as e:
            err = f"下载出错: {e}"
            self.root.after(0, lambda: self._set_status(err))
            self.root.after(0, lambda: messagebox.showerror("错误", err, parent=self.root))
        finally:
            self._current_operation = None
            self._operation_lock.release()

    def _normalize_ftp_path(self, path):
        """清理 FTP 路径，移除多余的 ./ 和 //"""
        import re
        # 替换多个斜杠为单个斜杠
        path = re.sub(r'/+', '/', path)
        # 处理 /./ 
        while '/./' in path or path.endswith('/.'):
            path = path.replace('/./', '/')
            if path.endswith('/.'):
                path = path[:-2]
        # 确保以 / 开头
        if not path.startswith('/'):
            path = '/' + path
        return path
    
    def _download_directory_recursive(self, server, remote_dir, local_dir):
        """递归下载目录及其内容
        返回: (是否成功, 文件数, 总大小)
        """
        try:
            # 清理路径，防止 ./ 循环
            remote_dir = self._normalize_ftp_path(remote_dir)
            
            # 创建本地目录
            if not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
            
            # 列出远程目录内容
            items, msg = self.ftp.list_dir(remote_dir)
            if not items:
                print(f"[DEBUG] 目录为空或无法读取: {remote_dir}")
                return True, 0, 0
            
            success_count = 0
            total_size = 0
            
            for item in items:
                # 清理文件名（移除可能的 . 和 ..）
                item_name = item['name'].strip()
                if item_name in ['.', '..']:
                    continue
                
                remote_path = self._normalize_ftp_path(f"{remote_dir}/{item_name}")
                local_path = os.path.join(local_dir, item_name)
                
                if item['is_dir']:
                    # 递归下载子目录
                    dir_ok, dir_count, dir_size = self._download_directory_recursive(
                        server, remote_path, local_path)
                    if dir_ok:
                        success_count += dir_count
                        total_size += dir_size
                        self.root.after(0, lambda n=item['name']: 
                            self._set_status(f"✓ 下载目录 {n}"))
                else:
                    # 下载文件
                    ok, msg = self.ftp.download_file(remote_path, local_path)
                    if ok:
                        file_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
                        success_count += 1
                        total_size += file_size
                        self.root.after(0, lambda n=item['name']: 
                            self._set_status(f"✓ 下载 {n}"))
                        self.config.add_log_entry(server["name"], "download", item['name'], 
                                                  "success", msg, file_size)
                    else:
                        self.root.after(0, lambda n=item['name']: 
                            self._set_status(f"✗ {n}: {msg}"))
                        self.config.add_log_entry(server["name"], "download", item['name'], 
                                                  "error", msg)
            
            return True, success_count, total_size
            
        except Exception as e:
            err = f"下载目录出错: {remote_dir} - {e}"
            print(f"[ERROR] {err}")
            self.root.after(0, lambda e=err: self._set_status(e))
            return False, 0, 0

    # ======================== 同步日志 Tab ========================

    def _build_log_tab(self, parent):
        """构建同步日志：左侧选择批次，右侧直接显示该批次文件。"""
        log_frame = ttk.Frame(parent, style="Card.TFrame")
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        top = ttk.Frame(log_frame, style="Card.TFrame", padding=(12, 10))
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="项目", style="Bold.TLabel").pack(side="left")
        self.log_filter_var = tk.StringVar(value="全部", name="log_filter")
        self.log_combo = ttk.Combobox(top, textvariable=self.log_filter_var,
                                      width=16, state="readonly", exportselection=False)
        self.log_combo.pack(side="left", padx=(6, 10))
        self.log_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_log())
        self.log_combo.bind("<<ComboboxSelected>>", lambda e: self._restore_combo_text(), add="+")
        self._keep_combo_text(self.log_combo, self.log_filter_var)

        ttk.Label(top, text="搜索", style="Bold.TLabel").pack(side="left")
        self.log_search_var = tk.StringVar()
        search_entry = ttk.Entry(top, textvariable=self.log_search_var, width=24)
        search_entry.pack(side="left", padx=(6, 4))
        search_entry.bind("<Return>", lambda e: self._refresh_log())
        ttk.Button(top, text="查找", command=self._refresh_log, style="Toolbar.TButton").pack(side="left", padx=2)
        ttk.Button(top, text="清空搜索", command=self._clear_log_search, style="Toolbar.TButton").pack(side="left", padx=2)
        ttk.Button(top, text="🔄 刷新", command=self._refresh_log, style="Compact.Success.TButton").pack(side="right", padx=2)
        ttk.Button(top, text="🗑 清空", command=self._clear_log, style="Compact.Danger.TButton").pack(side="right", padx=2)

        body = ttk.Frame(log_frame, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=2, minsize=280)
        body.columnconfigure(1, weight=5, minsize=360)
        body.rowconfigure(0, weight=1)
        batch_card = ttk.Frame(body, style="Card.TFrame", padding=8)
        file_card = ttk.Frame(body, style="Card.TFrame", padding=(12, 8, 8, 8))
        batch_card.grid(row=0, column=0, sticky="nsew")
        file_card.grid(row=0, column=1, sticky="nsew")

        self.log_summary_var = tk.StringVar(value="暂无批次")
        ttk.Label(batch_card, text="同步批次", style="Bold.TLabel").pack(anchor="w")
        ttk.Label(batch_card, textvariable=self.log_summary_var, style="TLabel").pack(anchor="w", pady=(0, 6))
        batch_list = ttk.Frame(batch_card, style="Card.TFrame")
        batch_list.pack(fill="both", expand=True)
        batch_list.rowconfigure(0, weight=1)
        batch_list.columnconfigure(0, weight=1)
        self.log_batch_tree = ttk.Treeview(
            batch_list, columns=("time", "project", "result"), show="headings", selectmode="browse")
        for column, title, width, anchor, stretch in (
            ("time", "时间", 96, "w", True),
            ("project", "项目", 72, "w", True),
            ("result", "结果", 52, "center", False),
        ):
            self.log_batch_tree.heading(column, text=title)
            self.log_batch_tree.column(column, width=width, minwidth=40, anchor=anchor, stretch=stretch)
        self.log_batch_tree.grid(row=0, column=0, sticky="nsew")
        batch_scroll = ttk.Scrollbar(batch_list, orient="vertical", command=self.log_batch_tree.yview)
        self.log_batch_tree.configure(yscrollcommand=batch_scroll.set)
        batch_scroll.grid(row=0, column=1, sticky="ns")
        self.log_batch_tree.tag_configure("batch_error", foreground=self.DANGER)
        self.log_batch_tree.tag_configure("batch_ok", foreground=self.SUCCESS)
        self.log_batch_tree.bind("<<TreeviewSelect>>", self._on_log_batch_select)

        file_head = ttk.Frame(file_card, style="Card.TFrame")
        file_head.pack(fill="x", pady=(0, 4))
        self.log_batch_title = tk.StringVar(value="请先选择左侧批次")
        title_label = ttk.Label(file_head, textvariable=self.log_batch_title, style="Bold.TLabel",
                                anchor="w", width=1)
        title_label.pack(fill="x")
        file_head.bind("<Configure>", lambda e: title_label.configure(wraplength=max(e.width, 1)))
        file_actions = ttk.Frame(file_card, style="Card.TFrame")
        file_actions.pack(fill="x", pady=(0, 6))
        ttk.Button(file_actions, text="重新上传", command=lambda: self._ask_reupload_log_file(), style="Compact.Primary.TButton").pack(side="left", padx=(0, 4))
        ttk.Button(file_actions, text="上传同目录", command=lambda: self._ask_reupload_log_dir(), style="Toolbar.TButton").pack(side="left", padx=2)
        ttk.Button(file_actions, text="复制路径", command=self._copy_log_file_path, style="Toolbar.TButton").pack(side="left", padx=2)

        file_list = ttk.Frame(file_card, style="Card.TFrame")
        file_list.pack(fill="both", expand=True)
        file_list.rowconfigure(0, weight=1)
        file_list.columnconfigure(0, weight=1)
        self.log_file_tree = ttk.Treeview(
            file_list, columns=("file", "status", "action", "size", "message"), show="headings", selectmode="browse")
        for column, title, width, anchor, stretch in (
            ("file", "文件", 180, "w", True),
            ("status", "状态", 48, "center", False),
            ("action", "操作", 48, "center", False),
            ("size", "大小", 60, "e", False),
            ("message", "详情", 100, "w", True),
        ):
            self.log_file_tree.heading(column, text=title)
            self.log_file_tree.column(column, width=width, minwidth=40, anchor=anchor, stretch=stretch)
        self.log_file_tree.grid(row=0, column=0, sticky="nsew")
        file_scroll = ttk.Scrollbar(file_list, orient="vertical", command=self.log_file_tree.yview)
        self.log_file_tree.configure(yscrollcommand=file_scroll.set)
        file_scroll.grid(row=0, column=1, sticky="ns")
        self.log_file_tree.tag_configure("success", foreground=self.SUCCESS)
        self.log_file_tree.tag_configure("error", foreground=self.DANGER)
        self.log_file_tree.tag_configure("info", foreground=self.WARNING)
        self.log_file_tree.bind("<Double-1>", lambda e: self._reupload_log_file())
        self.log_file_tree.bind("<<TreeviewSelect>>", self._on_log_file_select)
        self.log_file_tree.bind("<Button-3>", self._on_log_context_menu)

        self.log_action_hint = tk.StringVar(value="选择一个文件后，可重新上传或复制路径")
        hint_label = ttk.Label(file_card, textvariable=self.log_action_hint, style="TLabel", anchor="w", width=1)
        hint_label.pack(fill="x", pady=(6, 0))
        hint_label.bind("<Configure>", lambda e: hint_label.configure(wraplength=max(e.width, 1)))
        self.log_context_menu = tk.Menu(self.root, tearoff=0)
        self.log_context_menu.add_command(label="重新上传此文件", command=lambda: self._ask_reupload_log_file())
        self.log_context_menu.add_command(label="上传同目录所有文件", command=lambda: self._ask_reupload_log_dir())
        self.log_context_menu.add_separator()
        self.log_context_menu.add_command(label="复制文件路径", command=self._copy_log_file_path)
        self.log_batches = {}
        self.log_records = {}

    def _show_log_batch(self, batch_key):
        self.log_file_tree.delete(*self.log_file_tree.get_children())
        self.log_records = {}
        batch = self.log_batches.get(batch_key)
        if not batch:
            self.log_batch_title.set("请先选择左侧批次")
            self.log_action_hint.set("选择一个文件后，可重新上传或复制路径")
            return
        entries = batch["entries"]
        fail_count = sum(1 for entry in entries if entry.get("status") == "error")
        self.log_batch_title.set(f"{batch['project']}  ·  {batch['time']}  ·  {len(entries)} 个文件")
        ordered = sorted(entries, key=lambda entry: entry.get("status") != "error")
        for entry in ordered:
            status = entry.get("status", "")
            size = entry.get("size", 0)
            item_id = self.log_file_tree.insert("", "end", values=(
                entry.get("file", ""),
                self._log_status_text(status),
                self._log_action_text(entry.get("action", "")),
                f"{size:,}" if size else "—",
                entry.get("message", ""),
            ), tags=(status,))
            self.log_records[item_id] = entry
        if fail_count:
            self.log_file_tree.selection_set(self.log_file_tree.get_children()[0])
            self.log_file_tree.focus(self.log_file_tree.get_children()[0])
        self._on_log_file_select()

    def _clear_log_search(self):
        self.log_search_var.set("")
        self._refresh_log()

    def _log_matches(self, entry, keyword):
        if not keyword:
            return True
        fields = (
            entry.get("time", ""), entry.get("project", ""), entry.get("file", ""),
            entry.get("action", ""), entry.get("status", ""), entry.get("message", ""),
        )
        return keyword in " ".join(str(field) for field in fields).lower()

    @staticmethod
    def _log_short_time(value):
        """批次列表只显示月日时分，完整时间仍保留在右侧标题。"""
        text = str(value or "")
        if len(text) >= 16 and text[4] == "-" and text[10] == " ":
            return text[5:16]
        return text

    @staticmethod
    def _log_action_text(action):
        return {"upload": "上传", "download": "下载"}.get(action, action or "—")

    @staticmethod
    def _log_status_text(status):
        return {"success": "成功", "error": "失败", "info": "提示"}.get(status, status or "—")

    def _refresh_log(self):
        """刷新左侧批次，并保持当前批次或自动打开最新一批。"""
        previous = self.log_batch_tree.selection()
        previous_key = previous[0] if previous else ""
        self.log_batch_tree.delete(*self.log_batch_tree.get_children())
        self.log_batches = {}
        servers = ["全部"] + [s["name"] for s in self.config.get_servers()]
        current = self.log_filter_var.get()
        self.log_combo["values"] = servers
        if current not in servers:
            current = "全部"
            self.log_filter_var.set(current)
        self._restore_combo_text()

        keyword = self.log_search_var.get().strip().lower()
        entries = self.config.get_log_entries(
            project_name=None if current == "全部" else current, limit=500)
        entries = [entry for entry in entries if self._log_matches(entry, keyword)]

        grouped = {}
        for entry in entries:
            grouped.setdefault(entry.get("batch_id") or "__history__", []).append(entry)

        fail_total = sum(1 for entry in entries if entry.get("status") == "error")
        self.log_summary_var.set(
            f"{len(grouped)} 个批次，失败 {fail_total}" if entries else "没有匹配的日志")

        selected_key = ""
        for batch_key, batch_entries in grouped.items():
            latest = batch_entries[0]
            fail_count = sum(1 for entry in batch_entries if entry.get("status") == "error")
            project = latest.get("project", "历史记录") if batch_key != "__history__" else "历史记录"
            self.log_batches[batch_key] = {
                "project": project,
                "time": latest.get("time", ""),
                "entries": batch_entries,
            }
            self.log_batch_tree.insert("", "end", iid=batch_key, values=(
                self._log_short_time(latest.get("time", "")),
                project,
                f"失败 {fail_count}" if fail_count else f"{len(batch_entries)} 个",
            ), tags=("batch_error" if fail_count else "batch_ok",))
            if not selected_key or batch_key == previous_key or (not previous_key and fail_count):
                selected_key = batch_key

        if selected_key:
            self.log_batch_tree.selection_set(selected_key)
            self.log_batch_tree.focus(selected_key)
            self.log_batch_tree.see(selected_key)
        self._on_log_batch_select()

    def _on_log_batch_select(self, _event=None):
        selection = self.log_batch_tree.selection()
        self._show_log_batch(selection[0] if selection else "")

    def _on_log_file_select(self, _event=None):
        info = self._get_log_file_server_and_local()
        if not info:
            self.log_action_hint.set("选择一个文件后，可重新上传或复制路径")
            return
        _, local_path, rel_path = info
        self.log_action_hint.set(rel_path if os.path.exists(local_path) else f"本地文件不存在：{rel_path}")

    def _on_log_context_menu(self, event):
        """右键当前文件显示操作菜单。"""
        item = self.log_file_tree.identify_row(event.y)
        if not item:
            return
        self.log_file_tree.selection_set(item)
        self.log_context_menu.tk_popup(event.x_root, event.y_root)

    def _get_log_file_server_and_local(self):
        """获取当前选中日志文件的服务器名和本地完整路径。"""
        selection = self.log_file_tree.selection()
        if not selection:
            return None
        entry = self.log_records.get(selection[0])
        if not entry:
            return None

        server_name = entry.get("project", "")
        rel_path = entry.get("file", "")
        server = self.config.get_server(server_name)
        if not server or not rel_path:
            return None
        local_path = os.path.join(server.get("local_path", ""), rel_path.replace("/", os.sep))
        return server_name, local_path, rel_path

    def _defer_log_action(self, callback):
        """等当前点击结束后再弹窗，避免取消后焦点落回表格并清掉选中。"""
        selection = self.log_file_tree.selection()
        item = selection[0] if selection else ""

        def run():
            if item and self.log_file_tree.exists(item):
                self.log_file_tree.selection_set(item)
                self.log_file_tree.focus(item)
            callback()
            self.root.focus_set()

        self.root.after_idle(run)

    def _ask_reupload_log_file(self):
        self._defer_log_action(self._reupload_log_file)

    def _ask_reupload_log_dir(self):
        self._defer_log_action(self._reupload_log_dir)

    def _reupload_log_file(self):
        """重新上传右键选中的单个文件"""
        info = self._get_log_file_server_and_local()
        if not info:
            messagebox.showwarning("提示", "请先选择一个文件", parent=self.root)
            return
        server_name, local_path, rel_path = info
        if not os.path.exists(local_path):
            messagebox.showwarning("提示", f"本地文件不存在:\n{local_path}", parent=self.root)
            return
        if not messagebox.askyesno(
            "确认重新上传",
            f"确定重新上传这个文件到 [{server_name}] 吗？\n\n{rel_path}",
            parent=self.root,
        ):
            return
        self._start_direct_upload([local_path], server_name)

    def _reupload_log_dir(self):
        """上传右键文件所在目录下的所有文件"""
        info = self._get_log_file_server_and_local()
        if not info:
            messagebox.showwarning("提示", "请先选择一个文件", parent=self.root)
            return
        server_name, local_path, rel_path = info
        local_dir = os.path.dirname(local_path)
        if not os.path.isdir(local_dir):
            messagebox.showwarning("提示", f"本地目录不存在:\n{local_dir}", parent=self.root)
            return
        files = []
        for root_d, dirs, filenames in os.walk(local_dir):
            for fn in filenames:
                files.append(os.path.join(root_d, fn))
        if not files:
            messagebox.showinfo("提示", f"目录中没有文件:\n{local_dir}", parent=self.root)
            return
        if not messagebox.askyesno(
            "确认上传同目录",
            f"确定把该目录下的 {len(files)} 个文件上传到 [{server_name}] 吗？\n\n{local_dir}",
            parent=self.root,
        ):
            return
        self._start_direct_upload(files, server_name)

    def _copy_log_file_path(self):
        """复制选中的日志文件路径到剪贴板"""
        info = self._get_log_file_server_and_local()
        if not info:
            return
        _, local_path, rel_path = info
        self.root.clipboard_clear()
        self.root.clipboard_append(local_path)
        self._set_status(f"已复制: {local_path}")

    def _start_direct_upload(self, local_paths, server_name):
        """启动直接上传（不依赖 pending），显示 Loading 对话框"""
        self._upload_loading = LoadingDialog(self.root, "上传中",
                                             f"正在上传 {len(local_paths)} 个文件到 [{server_name}]，请稍候...")
        self._upload_loading.update_progress(0, len(local_paths), "准备中...")
        threading.Thread(target=self._do_direct_upload, args=(local_paths, server_name), daemon=True).start()

    def _do_direct_upload(self, local_paths, server_name):
        """在子线程中执行直接上传"""
        if not self._operation_lock.acquire(blocking=False):
            self.root.after(0, lambda: self._upload_loading.close())
            self.root.after(0, lambda: messagebox.showwarning("提示", "有其他操作正在进行，请稍后再试", parent=self.root))
            return
        try:
            self._current_operation = "upload"
            total = len(local_paths)

            def on_progress(index, total, rel_path, success, msg):
                detail = f"{'✓' if success else '✗'} {rel_path}"
                self.root.after(0, lambda i=index, t=total, d=detail: self._upload_loading.update_progress(i, t, d))

            success, fail, size, summary = self.monitor.upload_files_direct(
                local_paths, server_name, on_progress=on_progress)
            self.root.after(0, self._refresh_log)
            self.root.after(0, lambda: self._upload_loading.close())
            self.root.after(0, lambda: messagebox.showinfo("上传结果", summary, parent=self.root))
        except Exception as e:
            err = f"上传出错: {e}"
            self.root.after(0, lambda: self._upload_loading.close())
            self.root.after(0, lambda: messagebox.showerror("错误", err, parent=self.root))
        finally:
            self._current_operation = None
            self._operation_lock.release()

    def _clear_log(self):
        if messagebox.askyesno("确认", "确定清空所有日志吗？", parent=self.root):
            self.config.clear_log()
            self._refresh_log()

    # ======================== 状态栏 & 事件 ========================

    def _build_status_bar(self):
        bar = ttk.Frame(self.root, style="Status.TLabel")
        bar.pack(fill="x", side="bottom", padx=0, pady=0)

        inner = ttk.Frame(bar, style="Status.TLabel", padding=(16, 6))
        inner.pack(fill="x")
        
        # 监控状态指示器
        self.monitor_status_var = tk.StringVar(value="● 监控未启动")
        self.monitor_status_label = ttk.Label(
            inner, 
            textvariable=self.monitor_status_var,
            style="Status.TLabel"
        )
        self.monitor_status_label.pack(side="left", padx=(0, 20))

    def _set_monitor_status(self, running, name=None):
        """设置扫描状态显示"""
        if running:
            self.monitor_status_var.set(f"● 扫描运行中 - {name}")
            self.monitor_status_label.configure(style="Success.TLabel")
        else:
            self.monitor_status_var.set("● 扫描已停止")
            self.monitor_status_label.configure(style="Danger.TLabel")

    def _set_monitor_status_scan(self):
        """临时显示扫描中状态"""
        name = self.monitor.monitored_name or ""
        self.monitor_status_var.set(f"● 扫描中... {name}")
        self.monitor_status_label.configure(style="Warning.TLabel")

    def _restore_monitor_status(self):
        """扫描完成后恢复状态显示"""
        if self.monitor.is_running and self.monitor._auto_monitor:
            self._set_monitor_status(True, self.monitor.monitored_name)
        else:
            self._set_monitor_status(False)

    def _set_status(self, text):
        """状态栏显示（已简化）"""
        pass

    def _on_monitor_event(self, name, event_type, file_path, message):
        self.root.after(0, self._refresh_log)
        self.root.after(0, self._refresh_pending)
        # 扫描检测到变更时刷新列表
        if event_type in ("monitor_start", "monitor_stop", "scan"):
            self.root.after(0, self._refresh_servers)

    def _on_close(self):
        self._stop_countdown()
        if self.monitor.is_running:
            self.monitor.stop()
        self.ftp.disconnect()
        self.root.destroy()

    def _show_about(self):
        AboutDialog(self.root, self)


class AboutDialog(tk.Toplevel):
    """自定义关于对话框 - 现代化设计"""

    # 配色方案
    BG = "#f8fafc"
    HEADER_BG = "#1e293b"
    HEADER_GRADIENT = "#334155"
    ACCENT = "#3b82f6"
    ACCENT_LIGHT = "#60a5fa"
    CARD_BG = "#ffffff"
    TEXT_PRIMARY = "#0f172a"
    TEXT_SECONDARY = "#475569"
    TEXT_MUTED = "#94a3b8"
    BORDER = "#e2e8f0"
    SUCCESS = "#10b981"

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("关于")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=self.BG)

        container = tk.Frame(self, bg=self.BG)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg=self.HEADER_BG, padx=18, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="MyFtp", font=("Microsoft YaHei UI", 16, "bold"),
                 bg=self.HEADER_BG, fg="#ffffff").pack(side="left")
        tk.Label(header, text="v1.1.0", font=("Microsoft YaHei UI", 9),
                 bg=self.ACCENT, fg="#ffffff", padx=8, pady=2).pack(side="left", padx=(10, 0))
        tk.Label(header, text="项目文件同步工具", font=("Microsoft YaHei UI", 9),
                 bg=self.HEADER_BG, fg="#cbd5e1").pack(side="right")

        content = tk.Frame(container, bg=self.CARD_BG, padx=18, pady=14)
        content.pack(fill="both", expand=True)

        tk.Label(content, text="管理 FTP 服务器，监控本地变更，并同步远程目录。",
                 font=("Microsoft YaHei UI", 9), bg=self.CARD_BG,
                 fg=self.TEXT_SECONDARY, anchor="w", justify="left").pack(fill="x")

        chips = tk.Frame(content, bg=self.CARD_BG)
        chips.pack(fill="x", pady=(12, 0))
        for index, text in enumerate(("服务器管理", "实时监控", "目录同步", "文件浏览", "操作日志", "配置备份")):
            chip = tk.Label(chips, text=text, font=("Microsoft YaHei UI", 9),
                            bg="#eff6ff", fg=self.ACCENT, padx=8, pady=4)
            chip.grid(row=index // 3, column=index % 3, sticky="ew", padx=3, pady=3)
            chips.columnconfigure(index % 3, weight=1)

        foot = tk.Frame(content, bg=self.CARD_BG)
        foot.pack(fill="x", pady=(14, 0))
        tk.Frame(foot, bg=self.BORDER, height=1).pack(fill="x", pady=(0, 10))
        tk.Label(foot, text="© 2024 MyFtp", font=("Microsoft YaHei UI", 8),
                 bg=self.CARD_BG, fg=self.TEXT_MUTED).pack(side="left")
        close_btn = tk.Button(foot, text="关闭", width=8,
                              font=("Microsoft YaHei UI", 9),
                              bg=self.ACCENT, fg="#ffffff",
                              activebackground="#2563eb", activeforeground="#ffffff",
                              relief="flat", bd=0, cursor="hand2",
                              command=self._on_close)
        close_btn.pack(side="right")

        # 按钮悬停效果
        def on_enter(e):
            close_btn.configure(bg="#2563eb")
        def on_leave(e):
            close_btn.configure(bg=self.ACCENT)
        close_btn.bind("<Enter>", on_enter)
        close_btn.bind("<Leave>", on_leave)

        # 键盘快捷键
        self.bind("<Return>", lambda e: self._on_close())
        self.bind("<Escape>", lambda e: self._on_close())

        # ==================== 居中到父窗口 ====================
        self._center_over(parent)

        # 模态 & 焦点
        self.grab_set()
        close_btn.focus_set()

    def _center_over(self, parent):
        """将对话框居中到父窗口上"""
        parent.update_idletasks()
        self.update_idletasks()

        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width() or 900
        ph = parent.winfo_height() or 920

        dw = self.winfo_width() or 420
        dh = self.winfo_height() or 240

        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2

        self.geometry(f"+{x}+{y}")

    def _on_close(self):
        self.grab_release()
        self.destroy()


class RemoteDirDialog:
    """远程目录选择对话框：连接FTP服务器后浏览目录树，选择目标目录"""

    # 颜色常量，与应用主题保持一致
    CARD_BG = "#ffffff"
    PRIMARY = "#2563eb"
    TEXT_PRIMARY = "#1e293b"
    TEXT_SECONDARY = "#64748b"
    BORDER = "#e2e8f0"

    def __init__(self, parent, ftp_client, server_info, initial_path="/"):
        self.ftp = ftp_client
        self.server = server_info
        self.selected_path = None
        self._connected_here = False

        self.top = tk.Toplevel(parent)
        self.top.title("选择远程目录")
        self.top.geometry("500x400")
        self.top.transient(parent)
        self.top.configure(bg=self.CARD_BG)
        self.top.grab_set()

        self._build_ui()
        self._connect_and_load(initial_path)

    def _build_ui(self):
        top = ttk.Frame(self.top, style="Card.TFrame", padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="当前路径:", style="Bold.TLabel").pack(side="left")
        self.path_var = tk.StringVar(value="/")
        ttk.Entry(top, textvariable=self.path_var, width=40).pack(side="left", padx=4)
        ttk.Button(top, text="跳转", style="Toolbar.TButton", command=self._goto).pack(side="left", padx=2)
        ttk.Button(top, text="上级", style="Toolbar.TButton", command=self._up).pack(side="left", padx=2)
        ttk.Button(top, text="刷新", style="Toolbar.TButton", command=self._refresh).pack(side="left", padx=2)

        list_frame = ttk.Frame(self.top, style="Card.TFrame", padding=8)
        list_frame.pack(fill="both", expand=True)
        cols = ("name", "date")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="tree headings", height=15)
        self.tree.heading("#0", text="目录名")
        self.tree.heading("name", text="目录名")
        self.tree.heading("date", text="日期")
        self.tree.column("#0", width=300)
        self.tree.column("name", width=300)
        self.tree.column("date", width=120)
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._on_double_click)

        bottom = ttk.Frame(self.top, style="Card.TFrame", padding=8)
        bottom.pack(fill="x")
        self.status_label = ttk.Label(bottom, text="正在连接...", style="Card.TLabel")
        self.status_label.pack(side="left")
        ttk.Button(bottom, text="选择此目录", style="Primary.TButton", command=self._select).pack(side="right", padx=4)
        ttk.Button(bottom, text="取消", style="Danger.TButton", command=self._cancel).pack(side="right", padx=4)

    def _connect_and_load(self, path):
        self.status_label.config(text="正在连接服务器...")
        threading.Thread(target=self._do_connect, args=(path,), daemon=True).start()

    def _do_connect(self, path):
        was_connected = self.ftp.is_connected
        if not was_connected:
            ok, msg = self.ftp.connect(
                self.server["host"], self.server["port"],
                self.server["username"], self.server["password"],
                use_tls=bool(self.server.get("use_tls")))
            if not ok:
                self.top.after(0, lambda: self._on_connect_fail(msg))
                return
            self._connected_here = True
        try:
            self.ftp.cwd(path)
        except Exception:
            try:
                self.ftp.cwd(self.server.get("remote_path", "/"))
            except Exception:
                pass
        self.top.after(0, lambda: self._after_connect())

    def _on_connect_fail(self, msg):
        self.status_label.configure(style="Danger.TLabel")
        self.status_label.config(text=f"连接失败: {msg}")
        messagebox.showerror("连接失败", msg, parent=self.top)

    def _after_connect(self):
        self.path_var.set(self.ftp.pwd())
        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.ftp.is_connected:
            self.status_label.configure(style="Danger.TLabel")
            self.status_label.config(text="未连接")
            return
        path = self.path_var.get()
        items, msg = self.ftp.list_dir(path)
        if msg != "OK" and not items:
            self.status_label.configure(style="Danger.TLabel")
            self.status_label.config(text=f"读取失败: {msg}")
            return
        count = 0
        for item in items:
            if item["is_dir"]:
                self.tree.insert("", "end",
                                 text=item["name"],
                                 values=(item["name"], item["date"]))
                count += 1
        self.status_label.configure(style="Card.TLabel")
        self.status_label.config(text=f"共 {count} 个子目录")

    def _on_double_click(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0], "values")[0]
        current = self.path_var.get().rstrip("/")
        new_path = f"{current}/{name}"
        ok, _ = self.ftp.cwd(new_path)
        if ok:
            self.path_var.set(self.ftp.pwd())
            self._refresh()

    def _goto(self):
        path = self.path_var.get().strip()
        ok, _ = self.ftp.cwd(path)
        if ok:
            self.path_var.set(self.ftp.pwd())
            self._refresh()
        else:
            messagebox.showwarning("提示", "无法切换到该路径", parent=self.top)

    def _up(self):
        ok, _ = self.ftp.cwd("..")
        if ok:
            self.path_var.set(self.ftp.pwd())
            self._refresh()

    def _select(self):
        self.selected_path = self.path_var.get()
        self._cleanup()
        self.top.destroy()

    def _cancel(self):
        self.selected_path = None
        self._cleanup()
        self.top.destroy()

    def _cleanup(self):
        if self._connected_here:
            self.ftp.disconnect()


class RemoteFilePickerDialog:
    """远程文件选择对话框：连接FTP后浏览远程目录，可选择多个文件下载"""

    # 颜色常量，与应用主题保持一致
    CARD_BG = "#ffffff"
    PRIMARY = "#2563eb"
    TEXT_PRIMARY = "#1e293b"
    TEXT_SECONDARY = "#64748b"
    BORDER = "#e2e8f0"

    def __init__(self, parent, ftp_client, server_info, initial_path="/"):
        self.ftp = ftp_client
        self.server = server_info
        self.selected_files = []
        self._connected_here = False

        self.top = tk.Toplevel(parent)
        self.top.title("选择要下载的远程文件")
        self.top.geometry("600x450")
        self.top.transient(parent)
        self.top.configure(bg=self.CARD_BG)
        self.top.grab_set()

        self._build_ui()
        self._connect_and_load(initial_path)

    def _build_ui(self):
        top = ttk.Frame(self.top, style="Card.TFrame", padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="当前路径:", style="Bold.TLabel").pack(side="left")
        self.path_var = tk.StringVar(value="/")
        ttk.Entry(top, textvariable=self.path_var, width=42).pack(side="left", padx=4)
        ttk.Button(top, text="跳转", style="Toolbar.TButton", command=self._goto).pack(side="left", padx=2)
        ttk.Button(top, text="上级", style="Toolbar.TButton", command=self._up).pack(side="left", padx=2)
        ttk.Button(top, text="刷新", style="Toolbar.TButton", command=self._refresh).pack(side="left", padx=2)

        # 提示
        hint = ttk.Frame(self.top, style="Card.TFrame", padding=(8, 0))
        hint.pack(fill="x")
        ttk.Label(hint, text="💡 提示: 双击进入目录，单击选中/取消文件（可多选）",
                  style="Muted.TLabel").pack(side="left")

        list_frame = ttk.Frame(self.top, style="Card.TFrame", padding=8)
        list_frame.pack(fill="both", expand=True)
        cols = ("name", "type", "size", "date")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="tree headings", height=15)
        self.tree.heading("#0", text="名称")
        self.tree.heading("name", text="名称")
        self.tree.heading("type", text="类型")
        self.tree.heading("size", text="大小")
        self.tree.heading("date", text="日期")
        self.tree.column("#0", width=220)
        self.tree.column("name", width=220)
        self.tree.column("type", width=60)
        self.tree.column("size", width=80)
        self.tree.column("date", width=120)
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # 已选文件列表
        sel_frame = ttk.LabelFrame(self.top, text="已选文件", padding=4)
        sel_frame.pack(fill="x", padx=8, pady=(0, 4))
        self.sel_label = ttk.Label(sel_frame, text="未选择", style="Card.TLabel")
        self.sel_label.pack(side="left")
        ttk.Button(sel_frame, text="清空选择", style="Toolbar.TButton", command=self._clear_selection).pack(side="right")

        bottom = ttk.Frame(self.top, style="Card.TFrame", padding=8)
        bottom.pack(fill="x")
        self.status_label = ttk.Label(bottom, text="正在连接...", style="Card.TLabel")
        self.status_label.pack(side="left")
        ttk.Button(bottom, text="确认下载", style="Primary.TButton", command=self._confirm).pack(side="right", padx=4)
        ttk.Button(bottom, text="取消", style="Danger.TButton", command=self._cancel).pack(side="right", padx=4)

    def _connect_and_load(self, path):
        self.status_label.config(text="正在连接服务器...")
        threading.Thread(target=self._do_connect, args=(path,), daemon=True).start()

    def _do_connect(self, path):
        was_connected = self.ftp.is_connected
        if not was_connected:
            ok, msg = self.ftp.connect(
                self.server["host"], self.server["port"],
                self.server["username"], self.server["password"],
                use_tls=bool(self.server.get("use_tls")))
            if not ok:
                self.top.after(0, lambda: self._on_connect_fail(msg))
                return
            self._connected_here = True
        try:
            self.ftp.cwd(path)
        except Exception:
            try:
                self.ftp.cwd(self.server.get("remote_path", "/"))
            except Exception:
                pass
        self.top.after(0, lambda: self._after_connect())

    def _on_connect_fail(self, msg):
        self.status_label.configure(style="Danger.TLabel")
        self.status_label.config(text=f"连接失败: {msg}")
        messagebox.showerror("连接失败", msg, parent=self.top)

    def _after_connect(self):
        self.path_var.set(self.ftp.pwd())
        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.ftp.is_connected:
            self.status_label.configure(style="Danger.TLabel")
            self.status_label.config(text="未连接")
            return
        path = self.path_var.get()
        items, msg = self.ftp.list_dir(path)
        if msg != "OK" and not items:
            self.status_label.configure(style="Danger.TLabel")
            self.status_label.config(text=f"读取失败: {msg}")
            return
        for item in items:
            name = item["name"]
            ftype = "目录" if item["is_dir"] else "文件"
            size = f"{item['size']:,}" if not item["is_dir"] else "—"
            self.tree.insert("", "end",
                             text=name,
                             values=(name, ftype, size, item["date"]))
        self.status_label.configure(style="Card.TLabel")
        self.status_label.config(text=f"共 {len(items)} 项")

    def _on_double_click(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        name = vals[0]
        ftype = vals[1]
        if ftype == "目录":
            current = self.path_var.get().rstrip("/")
            new_path = f"{current}/{name}"
            ok, _ = self.ftp.cwd(new_path)
            if ok:
                self.path_var.set(self.ftp.pwd())
                self._refresh()

    def _on_select(self, event=None):
        """单击文件/目录时切换选中状态"""
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        vals = self.tree.item(item, "values")
        name = vals[0]
        ftype = vals[1]  # "目录" 或 "文件"
        
        current_path = self.path_var.get().rstrip("/")
        full_path = f"{current_path}/{name}".replace("//", "/")
        
        tags = self.tree.item(item, "tags")
        if "selected" in tags:
            # 取消选中
            self.tree.item(item, tags=())
            if full_path in self.selected_files:
                self.selected_files.remove(full_path)
        else:
            # 选中（支持文件和目录）
            self.tree.item(item, tags=("selected",))
            if full_path not in self.selected_files:
                self.selected_files.append((full_path, ftype))
        self._update_sel_label()
        # 清除Treeview选中状态，方便下次点击
        self.tree.selection_remove(item)

    def _update_sel_label(self):
        count = len(self.selected_files)
        if count == 0:
            self.sel_label.configure(style="Muted.TLabel")
            self.sel_label.config(text="未选择")
        else:
            # selected_files 现在是元组列表: (path, ftype)
            names = []
            for item in self.selected_files:
                if isinstance(item, tuple):
                    names.append(f"{item[1]}:{os.path.basename(item[0])}")
                else:
                    # 兼容旧格式
                    names.append(os.path.basename(item))
            display = ", ".join(names)
            if len(display) > 60:
                display = display[:60] + "..."
            self.sel_label.configure(style="Primary.TLabel")
            self.sel_label.config(text=f"已选 {count} 项: {display}")

    def _clear_selection(self):
        self.selected_files.clear()
        for item in self.tree.get_children():
            self.tree.item(item, tags=())
        self._update_sel_label()

    def _goto(self):
        path = self.path_var.get().strip()
        ok, _ = self.ftp.cwd(path)
        if ok:
            self.path_var.set(self.ftp.pwd())
            self._refresh()
        else:
            messagebox.showwarning("提示", "无法切换到该路径", parent=self.top)

    def _up(self):
        ok, _ = self.ftp.cwd("..")
        if ok:
            self.path_var.set(self.ftp.pwd())
            self._refresh()

    def _confirm(self):
        if not self.selected_files:
            messagebox.showwarning("提示", "请先选择要下载的文件或目录", parent=self.top)
            return
        # 转换为纯路径列表（兼容旧格式）
        paths = []
        for item in self.selected_files:
            if isinstance(item, tuple):
                paths.append(item[0])
            else:
                paths.append(item)
        self.selected_files = paths
        self._cleanup()
        self.top.destroy()

    def _cancel(self):
        self.selected_files = []
        self._cleanup()
        self.top.destroy()

    def _cleanup(self):
        if self._connected_here:
            self.ftp.disconnect()


def _parse_size(s):
    """解析大小字符串（如 '1,234' → 1234），用于排序时比较"""
    try:
        return int(str(s).replace(",", ""))
    except Exception:
        return 0


def run():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    run()
