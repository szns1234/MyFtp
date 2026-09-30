"""文件定时扫描模块

使用轮询方式定期扫描本地目录，通过文件快照（mtime）检测变更，
替代实时监控（watchdog），避免误报。
"""

import os
import json
import ctypes
import threading
from datetime import datetime
from collections import OrderedDict


def _set_hidden(path):
    """将文件或目录设为 Windows 隐藏属性（不影响正常读写）"""
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x2
        ctypes.windll.kernel32.SetFileAttributesW(path, FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


class FileMonitor:
    """项目文件定时扫描器，通过快照对比检测变更后记录到待上传列表，由用户手动上传"""

    def __init__(self, ftp_client, config_manager, on_event=None):
        """
        Args:
            ftp_client: FTPClient 实例
            config_manager: ConfigManager 实例
            on_event: 回调函数 (name, event_type, file_path, message) -> None
        """
        self.ftp = ftp_client
        self.config = config_manager
        self.on_event = on_event
        self._running = False
        self._monitored_name = None  # 当前扫描的服务器名称
        self._auto_monitor = False  # 是否处于自动扫描模式（区分 scan_once 和 start）
        self._lock = threading.RLock()  # 可重入锁，scan_once/start 内部调用 stop 不会死锁
        # 待上传文件列表: { 本地绝对路径: {"rel": 相对路径, "remote": 远程路径, "action": 操作类型, "time": 时间} }
        self._pending = OrderedDict()
        self._pending_lock = threading.Lock()

        # 定时扫描相关
        self._scan_interval = 3.0  # 扫描间隔（秒）
        self._scan_timer = None
        self._next_scan_time = None  # 下次扫描的预期时间戳（供 GUI 倒计时使用）
        self._scanning = False  # 当前是否正在执行扫描（供 GUI 区分"扫描中"和"倒计时"）
        self._scan_lock = threading.Lock()  # 确保同一时间只有一个扫描在执行
        # 文件快照: { 文件路径: mtime }，记录上次扫描时的文件状态
        self._snapshot = {}

    # ======================== 启动 / 停止 ========================

    def start(self, name):
        """开始扫描指定服务器对应的项目目录（不自动上传，只记录变更）"""
        with self._lock:
            if self._running:
                self.stop()

            server = self.config.get_server(name)
            if not server:
                return False, f"服务器 '{name}' 不存在"

            local_path = server.get("local_path", "")
            if not local_path or not os.path.exists(local_path):
                return False, f"本地路径不存在: {local_path}"

            self._running = True
            self._auto_monitor = True
            self._monitored_name = name

            # 执行扫描
            self._do_scan_work(name)

            # 启动定时扫描
            self._start_scan_timer()

            msg = f"扫描已启动: {name}（仅记录变更，不自动上传）"
            self._notify(name, "monitor_start", "", msg)
            return True, msg

    def scan_once(self, name):
        """执行一次性扫描，不启动定时扫描器。
        扫描完成后保持 _running=True（支持上传操作），但不会自动定时检测变更。"""
        with self._lock:
            if self._running:
                self.stop()

            server = self.config.get_server(name)
            if not server:
                return False, f"服务器 '{name}' 不存在"

            local_path = server.get("local_path", "")
            if not local_path or not os.path.exists(local_path):
                return False, f"本地路径不存在: {local_path}"

            self._running = True
            self._auto_monitor = False  # 一次性扫描，不是自动模式
            self._monitored_name = name

            # 执行扫描（不启动定时器）。手动刷新时，若从未同步过则全量列出
            self._do_scan_work(name, include_all_when_never_synced=True)

            msg = f"扫描完成: {name}"
            self._notify(name, "scan_once", "", msg)
            return True, msg

    def _do_scan_work(self, name, include_all_when_never_synced=False):
        """执行扫描工作的公共方法（start 和 scan_once 共用）

        Args:
            include_all_when_never_synced: 从未同步过（无 last_sync）时，是否把
                本地所有未排除文件都列为待上传。手动点「刷新扫描」传 True，
                这样新服务器扫一次就能看到全部文件；自动扫描保持 False，
                避免首次勾选就全量列出。
        """
        # 清空待上传列表
        with self._pending_lock:
            self._pending.clear()

        # 加载持久化快照
        self._load_snapshot(name)

        # 获取当前排除规则
        exclude_patterns = self.config.get_exclude_patterns(name)

        # 基于修改时间扫描待上传文件（捕获停止期间的变更）
        self._scan_by_mtime(include_all_when_never_synced=include_all_when_never_synced)

        # 检测删除的文件（旧快照中有，但当前文件系统中已不存在）
        self._detect_deleted_files()

        # 清理被过滤规则排除的文件（排除规则可能在上次运行后新增/修改过）
        with self._pending_lock:
            to_remove = []
            for local_file_path, info in self._pending.items():
                if _should_exclude(local_file_path, exclude_patterns):
                    to_remove.append(local_file_path)
            for path in to_remove:
                del self._pending[path]

        # 重建快照为当前状态（初始扫描后，后续只检测增量变更）
        self._rebuild_snapshot()

        # 保存快照
        self._save_snapshot(name)

    def stop(self):
        """停止扫描"""
        with self._lock:
            if self._scan_timer:
                self._scan_timer.cancel()
                self._scan_timer = None
            self._running = False
            self._auto_monitor = False
            self._next_scan_time = None
            self._scanning = False
            name = self._monitored_name
            self._monitored_name = None

            # 保存快照
            if name:
                self._save_snapshot(name)

            self._notify(name or "", "monitor_stop", "", "扫描已停止")

    @property
    def is_running(self):
        return self._running

    @property
    def monitored_name(self):
        """当前正在扫描的服务器名称"""
        return self._monitored_name

    @property
    def next_scan_time(self):
        """下次扫描的预期时间戳，None 表示未在运行"""
        return self._next_scan_time

    @property
    def is_scanning(self):
        """当前是否正在执行扫描（非倒计时等待阶段）"""
        return self._scanning

    @property
    def scan_interval(self):
        """扫描间隔（秒）"""
        return self._scan_interval

    # ======================== 定时扫描 ========================

    def _start_scan_timer(self):
        """启动定时扫描定时器"""
        if self._scan_timer:
            self._scan_timer.cancel()
        import time
        self._next_scan_time = time.time() + self._scan_interval
        self._scanning = False
        self._scan_timer = threading.Timer(self._scan_interval, self._scan)
        self._scan_timer.daemon = True
        self._scan_timer.start()

    def _scan(self):
        """定时扫描：对比快照检测增量变更。
        使用 _scan_lock 确保同一时间只有一个扫描在执行（防止定时器和 rescan 同时触发）。
        """
        if not self._running or not self._monitored_name:
            return

        # 获取扫描锁，确保同一时间只有一个扫描在执行
        if not self._scan_lock.acquire(blocking=False):
            # 另一个扫描正在执行，跳过本次（定时器会在那个扫描完成后重启）
            return

        self._scanning = True
        try:
            server = self.config.get_server(self._monitored_name)
            if not server:
                return

            local_path = server.get("local_path", "")
            if not local_path or not os.path.exists(local_path):
                return

            exclude_patterns = self.config.get_exclude_patterns(self._monitored_name)
            self._do_scan_core(server, local_path, exclude_patterns)

        except Exception as e:
            # 扫描异常时通知，但不中断后续扫描
            try:
                self._notify(self._monitored_name, "scan_error", "", f"扫描异常: {e}")
            except Exception:
                pass

        finally:
            self._scanning = False
            self._scan_lock.release()
            # 无论是否异常，只要还在运行就继续定时扫描
            if self._running:
                self._start_scan_timer()

    def _do_scan_core(self, server, local_path, exclude_patterns):
        """扫描核心逻辑：对比快照检测增量变更（被 _scan 和 rescan 共用）。
        调用者需已持有 _scan_lock。
        """
        remote_path = server.get("remote_path", "/")
        if not remote_path:
            remote_path = "/"

        local_base = local_path.replace("\\", "/")
        remote_base = remote_path.rstrip("/")

        # 扫描当前文件状态
        current_files = {}  # { file_path: mtime }
        for root, dirs, files in os.walk(local_path):
            dirs[:] = [d for d in dirs
                       if not _should_exclude(os.path.join(root, d), exclude_patterns)]
            for filename in files:
                file_path = os.path.join(root, filename)
                if _should_exclude(file_path, exclude_patterns):
                    continue
                try:
                    mtime = os.path.getmtime(file_path)
                    current_files[file_path] = mtime
                except Exception:
                    continue

        # 对比快照检测变更
        added_count = 0
        deleted_count = 0
        cancelled_count = 0
        with self._pending_lock:
            existing_paths = set(self._pending.keys())

            # 检测新增和修改的文件
            for file_path, mtime in current_files.items():
                old_mtime = self._snapshot.get(file_path)
                if old_mtime is None:
                    # 新文件（快照中不存在）
                    if file_path in existing_paths:
                        # 文件已在 pending 中，检查是否是删除后恢复
                        info = self._pending.get(file_path)
                        action = info.get("action", "") if info else ""
                        if action == "delete":
                            # 删除后撤回恢复 → 取消删除记录（远程文件还在，无需操作）
                            del self._pending[file_path]
                            cancelled_count += 1
                    else:
                        self._add_to_pending_internal(file_path, local_base, remote_base, "create")
                        added_count += 1
                elif mtime != old_mtime:
                    # 修改的文件（mtime 变化）
                    if file_path not in existing_paths:
                        self._add_to_pending_internal(file_path, local_base, remote_base, "modify")
                        added_count += 1

            # 检测删除的文件（快照中有，当前没有）
            for file_path in list(self._snapshot.keys()):
                if file_path not in current_files:
                    if file_path in existing_paths:
                        info = self._pending.get(file_path)
                        action = info.get("action", "") if info else ""
                        if action == "create":
                            # 文件新建后又删除 → 取消操作，无需上传或删除远程
                            del self._pending[file_path]
                            cancelled_count += 1
                        elif action == "modify":
                            # 文件修改后又删除 → 变为删除操作
                            self._add_delete_to_pending_internal(file_path, local_base, remote_base)
                            deleted_count += 1
                        # action == "delete" 则不重复添加
                    else:
                        # 快照中有但当前不存在，且不在待上传列表 → 新增删除记录
                        self._add_delete_to_pending_internal(file_path, local_base, remote_base)
                        deleted_count += 1

        # 更新快照为当前状态
        self._snapshot = current_files

        # 保存快照
        self._save_snapshot(self._monitored_name)

        # 智能通知
        parts = []
        if added_count:
            parts.append(f"新增/修改 {added_count} 个")
        if deleted_count:
            parts.append(f"删除 {deleted_count} 个")
        if cancelled_count:
            parts.append(f"取消 {cancelled_count} 个（创建后删除）")
        if parts:
            self._notify(self._monitored_name, "scan", "", "检测到变更: " + "，".join(parts))

    def _add_to_pending_internal(self, file_path, local_base, remote_base, action):
        """内部方法：添加文件到待上传列表（需要在 _pending_lock 内调用）"""
        file_path_norm = file_path.replace("\\", "/")
        rel = os.path.relpath(file_path_norm, local_base).replace("\\", "/")
        remote = remote_base + "/" + rel.lstrip("/")
        if not remote.startswith("/"):
            remote = "/" + remote

        try:
            mtime = os.path.getmtime(file_path)
            mtime_str = datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M:%S")
        except Exception:
            mtime_str = datetime.now().strftime("%m-%d %H:%M:%S")

        self._pending[file_path] = {
            "rel": rel,
            "remote": remote,
            "action": action,
            "time": mtime_str,
        }

    def _add_delete_to_pending_internal(self, file_path, local_base, remote_base):
        """内部方法：添加删除操作到待上传列表（需要在 _pending_lock 内调用）"""
        file_path_norm = file_path.replace("\\", "/")
        local_base_norm = local_base.rstrip("/") + "/"
        if file_path_norm.startswith(local_base_norm):
            rel = file_path_norm[len(local_base_norm):]
        else:
            rel = os.path.relpath(file_path_norm, local_base).replace("\\", "/")
        rel = rel.lstrip("/")

        remote = remote_base + "/" + rel
        if not remote.startswith("/"):
            remote = "/" + remote

        mtime_str = datetime.now().strftime("%m-%d %H:%M:%S")
        self._pending[file_path] = {
            "rel": rel,
            "remote": remote,
            "action": "delete",
            "time": mtime_str,
        }

    # ======================== 快照管理 ========================

    def _get_snapshot_path(self, name):
        """获取快照文件路径"""
        snapshot_dir = os.path.join(self.config.config_dir, "snapshots")
        os.makedirs(snapshot_dir, exist_ok=True)
        _set_hidden(snapshot_dir)
        # 替换文件名中不安全的字符
        safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        return os.path.join(snapshot_dir, f"{safe_name}.json")

    def _load_snapshot(self, name):
        """加载持久化快照"""
        path = self._get_snapshot_path(name)
        self._snapshot = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # JSON 的 key 可能丢失路径分隔符，直接使用
                self._snapshot = {k: v for k, v in data.items()}
            except Exception:
                self._snapshot = {}

    def _save_snapshot(self, name):
        """保存快照到磁盘"""
        path = self._get_snapshot_path(name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._snapshot, f, ensure_ascii=False)
        except Exception:
            pass

    def _rebuild_snapshot(self):
        """重建快照为当前文件状态"""
        if not self._monitored_name:
            return

        server = self.config.get_server(self._monitored_name)
        if not server:
            return

        local_path = server.get("local_path", "")
        if not local_path or not os.path.exists(local_path):
            return

        exclude_patterns = self.config.get_exclude_patterns(self._monitored_name)
        self._snapshot = {}

        for root, dirs, files in os.walk(local_path):
            dirs[:] = [d for d in dirs
                       if not _should_exclude(os.path.join(root, d), exclude_patterns)]
            for filename in files:
                file_path = os.path.join(root, filename)
                if _should_exclude(file_path, exclude_patterns):
                    continue
                try:
                    mtime = os.path.getmtime(file_path)
                    self._snapshot[file_path] = mtime
                except Exception:
                    continue

    # ======================== 待上传列表管理 ========================

    def add_pending(self, local_path, remote_path, action="modify", rel_path=None):
        """添加待上传文件到列表（线程安全）"""
        with self._pending_lock:
            if rel_path is not None:
                rel = rel_path
            else:
                try:
                    rel = os.path.relpath(local_path, self._get_local_base())
                    rel = rel.replace("\\", "/")
                except Exception:
                    rel = os.path.basename(local_path)

            mtime_str = datetime.now().strftime("%m-%d %H:%M:%S")
            try:
                if os.path.exists(local_path) and os.path.isfile(local_path):
                    mtime = os.path.getmtime(local_path)
                    mtime_str = datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M:%S")
            except Exception:
                pass

            self._pending[local_path] = {
                "rel": rel,
                "remote": remote_path,
                "action": action,
                "time": mtime_str,
            }
        self._notify(self._monitored_name or "", "pending", local_path,
                     f"检测到变更: {os.path.basename(local_path)}")

    def remove_pending(self, local_path):
        """从待上传列表中移除"""
        with self._pending_lock:
            if local_path in self._pending:
                del self._pending[local_path]

    def remove_from_snapshot(self, local_path):
        """从快照中移除指定路径（删除文件后调用，避免下次扫描重新检测到该文件）"""
        removed = False
        with self._lock:
            # 如果是文件，直接移除
            if local_path in self._snapshot:
                del self._snapshot[local_path]
                removed = True
            # 如果是目录，移除目录下所有文件
            keys_to_remove = [k for k in self._snapshot if k.startswith(local_path + os.sep)]
            for k in keys_to_remove:
                del self._snapshot[k]
                removed = True
            if removed and self._monitored_name:
                self._save_snapshot(self._monitored_name)
        return removed

    def clear_pending(self):
        """清空待上传列表"""
        with self._pending_lock:
            self._pending.clear()

    def get_pending(self):
        """获取待上传文件列表（返回列表）"""
        with self._pending_lock:
            return [(path, info.copy()) for path, info in self._pending.items()]

    def _get_local_base(self):
        """获取当前扫描的本地根路径"""
        if self._monitored_name:
            s = self.config.get_server(self._monitored_name)
            if s:
                return s.get("local_path", "")
        return ""

    # ======================== 手动扫描 ========================

    def rescan(self):
        """重新扫描并清理待上传列表，移除被过滤规则排除的文件，然后检测增量变更。
        会等待当前扫描完成后再执行（使用 _scan_lock 确保不与定时扫描同时执行）。
        """
        if not self._running or not self._monitored_name:
            return

        # 取消当前定时器，防止 rescan 执行期间定时器到期触发竞争
        if self._scan_timer:
            self._scan_timer.cancel()

        # 等待获取扫描锁（确保当前定时扫描完成后再执行 rescan）
        self._scan_lock.acquire()
        self._scanning = True
        try:
            # 获取锁后再次检查，防止在等待锁期间用户已停止扫描
            if not self._running or not self._monitored_name:
                return

            server = self.config.get_server(self._monitored_name)
            if not server:
                return

            local_path = server.get("local_path", "")
            exclude_patterns = self.config.get_exclude_patterns(self._monitored_name)

            # 清理被过滤的文件，保留真正需要上传的
            with self._pending_lock:
                to_remove = []
                for local_file_path, info in self._pending.items():
                    if _should_exclude(local_file_path, exclude_patterns):
                        to_remove.append(local_file_path)
                for path in to_remove:
                    del self._pending[path]

            # 执行增量扫描（对比快照检测变更）—— 直接调用 _scan 的核心逻辑
            self._do_scan_core(server, local_path, exclude_patterns)

        except Exception as e:
            try:
                self._notify(self._monitored_name, "scan_error", "", f"刷新扫描异常: {e}")
            except Exception:
                pass
        finally:
            self._scanning = False
            self._scan_lock.release()
            # rescan 完成后重启定时器
            if self._running:
                self._start_scan_timer()

    # ======================== 初始扫描（基于 last_sync） ========================

    def _detect_deleted_files(self):
        """检测删除的文件：旧快照中存在但当前文件系统中不存在的文件"""
        if not self._monitored_name or not self._snapshot:
            return

        server = self.config.get_server(self._monitored_name)
        if not server:
            return

        local_path = server.get("local_path", "")
        if not local_path or not os.path.exists(local_path):
            return

        remote_path = server.get("remote_path", "/")
        if not remote_path:
            remote_path = "/"

        exclude_patterns = self.config.get_exclude_patterns(self._monitored_name)
        local_base = local_path.replace("\\", "/")
        remote_base = remote_path.rstrip("/")

        # 扫描当前文件状态
        current_files = set()
        for root, dirs, files in os.walk(local_path):
            dirs[:] = [d for d in dirs
                       if not _should_exclude(os.path.join(root, d), exclude_patterns)]
            for filename in files:
                file_path = os.path.join(root, filename)
                if _should_exclude(file_path, exclude_patterns):
                    continue
                current_files.add(file_path)

        added_count = 0
        deleted_count = 0
        cancelled_count = 0
        with self._pending_lock:
            existing_paths = set(self._pending.keys())
            for file_path in list(self._snapshot.keys()):
                # 快照中有但当前不存在
                if file_path not in current_files:
                    if file_path in existing_paths:
                        info = self._pending.get(file_path)
                        action = info.get("action", "") if info else ""
                        if action == "create":
                            # 文件新建后又删除 → 取消操作
                            del self._pending[file_path]
                            cancelled_count += 1
                        elif action == "modify":
                            # 文件修改后又删除 → 变为删除操作
                            self._add_delete_to_pending_internal(file_path, local_base, remote_base)
                            deleted_count += 1
                    else:
                        # 不在待上传列表 → 新增删除记录
                        self._add_delete_to_pending_internal(file_path, local_base, remote_base)
                        deleted_count += 1

        # 智能通知
        parts = []
        if deleted_count:
            parts.append(f"删除 {deleted_count} 个")
        if cancelled_count:
            parts.append(f"取消 {cancelled_count} 个（创建后删除）")
        if parts:
            self._notify(self._monitored_name, "scan", "", "检测到变更: " + "，".join(parts))

    def _scan_by_mtime(self, include_all_when_never_synced=False):
        """基于修改时间扫描本地目录，将修改时间晚于上次同步时间的文件添加到待上传列表。

        如果从未同步过（last_sync 为 None）：
          · include_all_when_never_synced=False：不添加任何文件（自动扫描首次不全量上传）；
          · include_all_when_never_synced=True：把本地所有未排除文件都列为待上传
            （手动点「刷新扫描」时，让新服务器扫一次就能看到全部文件）。
        """
        if not self._monitored_name:
            return

        server = self.config.get_server(self._monitored_name)
        if not server:
            return

        local_path = server.get("local_path", "")
        if not local_path or not os.path.exists(local_path):
            return

        remote_path = server.get("remote_path", "/")
        if not remote_path:
            remote_path = "/"

        exclude_patterns = self.config.get_exclude_patterns(self._monitored_name)

        # 获取上次同步时间
        last_sync_str = server.get("last_sync")
        last_sync = None
        if last_sync_str:
            try:
                last_sync = datetime.fromisoformat(last_sync_str)
            except Exception:
                last_sync = None

        # 从未同步过时的处理：
        #   · 手动刷新（include_all_when_never_synced=True）→ 全量列出，不按 last_sync 过滤
        #   · 自动扫描（False）→ 不添加任何文件（避免首次启动全量上传）
        never_synced = not last_sync
        if never_synced and not include_all_when_never_synced:
            return

        # 获取已存在的 pending 路径，避免重复添加
        with self._pending_lock:
            existing_paths = set(self._pending.keys())

        added_count = 0
        local_base = local_path.replace("\\", "/")
        remote_base = remote_path.rstrip("/")

        for root, dirs, files in os.walk(local_path):
            dirs[:] = [d for d in dirs
                       if not _should_exclude(os.path.join(root, d), exclude_patterns)]

            for filename in files:
                file_path = os.path.join(root, filename)

                if _should_exclude(file_path, exclude_patterns):
                    continue

                # 如果已经在待上传列表中，跳过
                if file_path in existing_paths:
                    continue

                # 检查修改时间
                try:
                    mtime = os.path.getmtime(file_path)
                    mtime_dt = datetime.fromtimestamp(mtime)
                except Exception:
                    continue

                # 已同步过：只添加修改时间晚于上次同步的文件
                # 从未同步且要求全量：不按时间过滤，全部列出
                if not never_synced and mtime_dt <= last_sync:
                    continue

                # 计算相对路径和远程路径
                file_path_norm = file_path.replace("\\", "/")
                rel = os.path.relpath(file_path_norm, local_base).replace("\\", "/")
                remote = remote_base + "/" + rel.lstrip("/")
                if not remote.startswith("/"):
                    remote = "/" + remote

                # 添加到待上传列表：从未同步的全量列出记为 create，其余为 modify
                mtime_str = mtime_dt.strftime("%m-%d %H:%M:%S")
                with self._pending_lock:
                    self._pending[file_path] = {
                        "rel": rel,
                        "remote": remote,
                        "action": "create" if never_synced else "modify",
                        "time": mtime_str,
                    }
                existing_paths.add(file_path)
                added_count += 1

    # ======================== 上传 ========================

    def upload_pending(self, paths=None, on_progress=None):
        """手动上传待上传文件，连接FTP、上传、断开。
        paths: 指定上传的文件路径列表，None表示全部上传。
        on_progress: 回调 (index, total, rel_path, success, msg) -> None
        返回 (成功数, 失败数, 总大小, 摘要)
        """
        if not self._monitored_name:
            return 0, 0, 0, "没有正在扫描的项目"

        server = self.config.get_server(self._monitored_name)
        if not server:
            return 0, 0, 0, "服务器信息不存在"

        pending = self.get_pending()
        if paths is not None:
            path_set = set(paths)
            pending = [(p, info) for p, info in pending if p in path_set]

        if not pending:
            return 0, 0, 0, "没有待上传的文件"

        total = len(pending)

        # 生成批次ID（用于日志分组：同一次上传操作的所有文件共享同一个 batch_id）
        import time
        batch_id = f"{int(time.time())}_{server['name']}"

        # 创建文件日志（按服务器分目录+时间戳命名）
        # 用 try-except 包裹，确保日志失败绝不影响上传
        log_file_path = None
        log_write = None
        try:
            log_file_path, log_write = self.config.create_batch_log(
                server["name"], "upload", total)
        except Exception:
            log_write = lambda *a, **kw: None  # 空操作

        # 连接FTP - 先断开再连接，确保连接是新的
        if self.ftp.is_connected:
            self.ftp.disconnect()
        ok, msg = self.ftp.connect(
            server["host"], server["port"],
            server["username"], server["password"],
            use_tls=bool(server.get("use_tls")))
        if not ok:
            return 0, total, 0, f"连接失败: {msg}"

        success_count = 0
        fail_count = 0
        total_size = 0
        uploaded_paths = []
        fail_details = []

        for i, (local_path, info) in enumerate(pending):
            action = info.get("action", "")
            is_dir_action = action.startswith("dir_")

            if is_dir_action:
                remote_path = info["remote"]

                # 检查是否是目录删除操作
                if action == "dir_delete":
                    ok, msg = self.ftp.delete_directory(remote_path)
                    if ok:
                        success_count += 1
                        uploaded_paths.append(local_path)
                        rel_name = os.path.basename(local_path)
                        self.config.add_log_entry(server["name"], "rmdir",
                                                  rel_name, "success", f"删除远程目录: {remote_path}", 0,
                                                  batch_id=batch_id)
                        log_write("rmdir", rel_name, "success", f"删除远程目录: {remote_path}", 0)
                        self._notify(server["name"], "rmdir", rel_name,
                                     f"✓ [删除目录] {rel_name}")
                        if on_progress:
                            on_progress(i + 1, total, rel_name, True, f"已删除远程目录: {remote_path}")
                    else:
                        if "No such file" in msg or "not found" in msg.lower():
                            success_count += 1
                            uploaded_paths.append(local_path)
                            rel_name = os.path.basename(local_path)
                            self.config.add_log_entry(server["name"], "rmdir",
                                                      rel_name, "success", f"远程目录不存在，无需删除: {remote_path}", 0,
                                                      batch_id=batch_id)
                            log_write("rmdir", rel_name, "success", f"远程目录不存在，无需删除: {remote_path}", 0)
                            self._notify(server["name"], "rmdir", rel_name,
                                         f"✓ [删除目录] {rel_name} (目录不存在)")
                            if on_progress:
                                on_progress(i + 1, total, rel_name, True, f"远程目录不存在: {remote_path}")
                        else:
                            fail_count += 1
                            rel_name = os.path.basename(local_path)
                            fail_details.append(f"  ✗ [删除目录] {rel_name}: {msg}")
                            self.config.add_log_entry(server["name"], "rmdir",
                                                      rel_name, "error", f"删除目录失败: {msg}", 0,
                                                      batch_id=batch_id)
                            log_write("rmdir", rel_name, "error", f"删除目录失败: {msg}", 0)
                            if on_progress:
                                on_progress(i + 1, total, rel_name, False, f"删除目录失败: {msg}")
                    continue

                # 目录创建操作
                dir_ok = self.ftp.ensure_remote_dir(remote_path.lstrip("/"))
                if dir_ok:
                    success_count += 1
                    uploaded_paths.append(local_path)
                    rel_name = os.path.basename(local_path)
                    self.config.add_log_entry(server["name"], "mkdir",
                                              rel_name, "success", f"创建远程目录: {remote_path}", 0,
                                              batch_id=batch_id)
                    log_write("mkdir", rel_name, "success", f"创建远程目录: {remote_path}", 0)
                    self._notify(server["name"], "mkdir", rel_name,
                                 f"✓ [目录] {rel_name}")
                    if on_progress:
                        on_progress(i + 1, total, rel_name, True, f"目录已创建: {remote_path}")
                else:
                    fail_count += 1
                    rel_name = os.path.basename(local_path)
                    fail_details.append(f"  ✗ [目录] {rel_name}: 创建失败")
                    self.config.add_log_entry(server["name"], "mkdir",
                                              rel_name, "error", f"无法创建远程目录: {remote_path}", 0,
                                              batch_id=batch_id)
                    log_write("mkdir", rel_name, "error", f"无法创建远程目录: {remote_path}", 0)
                    if on_progress:
                        on_progress(i + 1, total, rel_name, False, "创建目录失败")
                continue

            # 文件操作
            remote_path = info["remote"]

            # 检查是否是删除操作
            if action == "delete":
                # 先检查是文件还是目录
                is_dir = False
                file_exists = False
                try:
                    parts = remote_path.rstrip("/").split("/")
                    if len(parts) > 1:
                        filename = parts[-1]
                        dir_path = "/".join(parts[:-1]) or "/"
                    else:
                        filename = remote_path
                        dir_path = "/"

                    self.ftp.ftp.cwd(dir_path)
                    items, _ = self.ftp.list_dir(".")
                    for item in items:
                        if item["name"] == filename:
                            is_dir = item["is_dir"]
                            file_exists = True
                            break
                    self.ftp.ftp.cwd("/")
                except Exception:
                    pass

                # 如果文件/目录不存在，视为删除成功
                if not file_exists:
                    success_count += 1
                    uploaded_paths.append(local_path)
                    self.config.add_log_entry(server["name"], "delete",
                                              info["rel"], "success", f"远程文件不存在，无需删除: {remote_path}", 0,
                                              batch_id=batch_id)
                    log_write("delete", info["rel"], "success", f"远程文件不存在，无需删除: {remote_path}", 0)
                    continue

                # 根据类型选择删除方法
                if is_dir:
                    ok, msg = self.ftp.delete_directory(remote_path)
                else:
                    ok, msg = self.ftp.delete_file(remote_path)

                if ok:
                    success_count += 1
                    uploaded_paths.append(local_path)
                else:
                    if "No such file" in msg or "not found" in msg.lower():
                        success_count += 1
                        uploaded_paths.append(local_path)
                        self.config.add_log_entry(server["name"], "delete",
                                                  info["rel"], "success", f"远程文件不存在，无需删除: {remote_path}", 0,
                                                  batch_id=batch_id)
                        log_write("delete", info["rel"], "success", f"远程文件不存在，无需删除: {remote_path}", 0)
                    else:
                        fail_count += 1
                        fail_details.append(f"  ✗ [删除] {info['rel']}: {msg}")
                continue

            # 检查本地文件是否存在（上传操作需要本地文件）
            if not os.path.exists(local_path) or not os.path.isfile(local_path):
                fail_count += 1
                fail_details.append(f"  ✗ {info['rel']}: 本地文件不存在")
                self.config.add_log_entry(server["name"], "upload",
                                          info["rel"], "error", "本地文件不存在",
                                          batch_id=batch_id)
                log_write("upload", info["rel"], "error", "本地文件不存在")
                if on_progress:
                    on_progress(i + 1, total, info["rel"], False, "本地文件不存在")
                continue

            file_size = os.path.getsize(local_path)
            ok, msg = self.ftp.upload_file(local_path, remote_path)

            if ok:
                success_count += 1
                total_size += file_size
                uploaded_paths.append(local_path)
                self.config.add_log_entry(server["name"], "upload",
                                          info["rel"], "success", msg, file_size,
                                          batch_id=batch_id)
                log_write("upload", info["rel"], "success", msg, file_size)
                self._notify(server["name"], "upload", info["rel"],
                             f"✓ {info['rel']}")
                if on_progress:
                    on_progress(i + 1, total, info["rel"], True, msg)
            else:
                fail_count += 1
                fail_details.append(f"  ✗ {info['rel']}: {msg}")
                self.config.add_log_entry(server["name"], "upload",
                                          info["rel"], "error", msg, file_size,
                                          batch_id=batch_id)
                log_write("upload", info["rel"], "error", msg, file_size)
                self._notify(server["name"], "upload", info["rel"],
                             f"✗ {info['rel']}: {msg}")
                if on_progress:
                    on_progress(i + 1, total, info["rel"], False, msg)

        # 从待上传列表中移除已上传成功的
        for p in uploaded_paths:
            self.remove_pending(p)

        # 更新服务器统计
        s = self.config.get_server(server["name"])
        if s and success_count > 0:
            s["sync_count"] = s.get("sync_count", 0) + success_count
            s["last_sync"] = datetime.now().isoformat()
            self.config.save()

        # 更新快照：移除已删除文件的记录，确保已上传的文件不会重复检测
        for p in uploaded_paths:
            action = None
            for _, info in pending:
                if _ == p:
                    action = info.get("action", "")
                    break
            if action == "delete":
                # 已删除的文件从快照中移除
                self._snapshot.pop(p, None)
            else:
                # 已上传的文件更新快照中的 mtime
                try:
                    if os.path.exists(p):
                        self._snapshot[p] = os.path.getmtime(p)
                except Exception:
                    pass

        # 保存快照
        if self._monitored_name:
            self._save_snapshot(self._monitored_name)

        # 断开FTP（扫描不需要保持连接）
        self.ftp.disconnect()

        # 写入文件日志摘要
        try:
            if log_file_path:
                self.config.write_batch_summary(log_file_path, success_count, fail_count, total_size)
        except Exception:
            pass

        summary = f"上传完成: 成功 {success_count}/{total}, 失败 {fail_count}, 共 {total_size/1024:.1f} KB"
        if fail_details:
            summary += "\n失败详情:\n" + "\n".join(fail_details)
        return success_count, fail_count, total_size, summary

    def upload_files_direct(self, local_paths, server_name, on_progress=None):
        """直接上传指定的本地文件列表（不依赖 pending 列表）。
        
        用于从同步日志右键重新上传：根据服务器配置的 local_path/remote_path 
        自动计算每个文件的远程路径。
        
        Args:
            local_paths: 本地文件绝对路径列表
            server_name: 服务器名称
            on_progress: 回调 (index, total, rel_path, success, msg) -> None
        Returns:
            (成功数, 失败数, 总大小, 摘要)
        """
        server = self.config.get_server(server_name)
        if not server:
            return 0, len(local_paths), 0, "服务器信息不存在"
        
        local_base = server.get("local_path", "")
        remote_base = server.get("remote_path", "/")
        if not local_base:
            return 0, len(local_paths), 0, "服务器未配置本地路径"
        
        # 构建待上传列表: [(local_path, {"rel":..., "remote":..., "action":"upload"})]
        pending = []
        for lp in local_paths:
            lp_norm = lp.replace("\\", "/")
            try:
                rel = os.path.relpath(lp_norm, local_base).replace("\\", "/")
            except ValueError:
                continue
            remote = remote_base + "/" + rel.lstrip("/")
            if not remote.startswith("/"):
                remote = "/" + remote
            pending.append((lp, {"rel": rel, "remote": remote, "action": "upload"}))
        
        if not pending:
            return 0, 0, 0, "没有有效的文件路径"
        
        total = len(pending)
        import time
        batch_id = f"{int(time.time())}_{server['name']}"
        
        # 创建文件日志
        log_write = lambda *a, **kw: None
        log_file_path = None
        try:
            log_file_path, log_write = self.config.create_batch_log(
                server["name"], "upload", total)
        except Exception:
            pass
        
        # 连接FTP
        if self.ftp.is_connected:
            self.ftp.disconnect()
        ok, msg = self.ftp.connect(
            server["host"], server["port"],
            server["username"], server["password"],
            use_tls=bool(server.get("use_tls")))
        if not ok:
            return 0, total, 0, f"连接失败: {msg}"
        
        success_count = 0
        fail_count = 0
        total_size = 0
        fail_details = []
        
        for i, (local_path, info) in enumerate(pending):
            remote_path = info["remote"]
            
            if not os.path.exists(local_path) or not os.path.isfile(local_path):
                fail_count += 1
                fail_details.append(f"  ✗ {info['rel']}: 本地文件不存在")
                self.config.add_log_entry(server["name"], "upload",
                                          info["rel"], "error", "本地文件不存在",
                                          batch_id=batch_id)
                log_write("upload", info["rel"], "error", "本地文件不存在")
                if on_progress:
                    on_progress(i + 1, total, info["rel"], False, "本地文件不存在")
                continue
            
            file_size = os.path.getsize(local_path)
            ok, msg = self.ftp.upload_file(local_path, remote_path)
            
            if ok:
                success_count += 1
                total_size += file_size
                self.config.add_log_entry(server["name"], "upload",
                                          info["rel"], "success", msg, file_size,
                                          batch_id=batch_id)
                log_write("upload", info["rel"], "success", msg, file_size)
                self._notify(server["name"], "upload", info["rel"], f"✓ {info['rel']}")
                if on_progress:
                    on_progress(i + 1, total, info["rel"], True, msg)
            else:
                fail_count += 1
                fail_details.append(f"  ✗ {info['rel']}: {msg}")
                self.config.add_log_entry(server["name"], "upload",
                                          info["rel"], "error", msg, file_size,
                                          batch_id=batch_id)
                log_write("upload", info["rel"], "error", msg, file_size)
                self._notify(server["name"], "upload", info["rel"], f"✗ {info['rel']}: {msg}")
                if on_progress:
                    on_progress(i + 1, total, info["rel"], False, msg)
        
        # 更新服务器统计
        s = self.config.get_server(server["name"])
        if s and success_count > 0:
            s["sync_count"] = s.get("sync_count", 0) + success_count
            s["last_sync"] = datetime.now().isoformat()
            self.config.save()
        
        self.ftp.disconnect()
        
        try:
            if log_file_path:
                self.config.write_batch_summary(log_file_path, success_count, fail_count, total_size)
        except Exception:
            pass
        
        summary = f"上传完成: 成功 {success_count}/{total}, 失败 {fail_count}, 共 {total_size/1024:.1f} KB"
        if fail_details:
            summary += "\n失败详情:\n" + "\n".join(fail_details)
        return success_count, fail_count, total_size, summary

    def _notify(self, name, event_type, file_path, message):
        if self.on_event:
            try:
                self.on_event(name, event_type, file_path, message)
            except Exception:
                pass


def _should_exclude(file_path, patterns):
    """检查文件是否应被排除

    支持三种模式：
      · *.ext  — 按扩展名通配
      · name   — 按文件名或路径片段子串匹配
      · dir/   — 按目录过滤，匹配该目录下的所有文件和子目录
    """
    filename = os.path.basename(file_path)
    file_path_norm = file_path.replace("\\", "/")
    for p in patterns:
        if p.startswith("*"):
            if filename.endswith(p[1:]):
                return True
        elif p.endswith("/"):
            # 目录过滤：在路径末尾补 / 确保目录边界匹配
            if p in file_path_norm + "/":
                return True
        else:
            if p in file_path_norm:
                return True
    return False
