"""配置管理模块"""

import json
import os
import sys
import ctypes
from datetime import datetime


def _set_hidden(path):
    """将文件或目录设为 Windows 隐藏属性（不影响正常读写）"""
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x2
        ctypes.windll.kernel32.SetFileAttributesW(path, FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


class ConfigManager:
    """管理应用配置和服务器列表（含项目监控信息）"""

    def __init__(self, config_dir=None):
        if config_dir is None:
            # 统一使用用户 AppData 目录，不放在软件目录下
            app_name = "MyFtp"
            if sys.platform == "win32":
                base = os.environ.get("APPDATA", os.path.expanduser("~"))
                config_dir = os.path.join(base, app_name)
            else:
                config_dir = os.path.join(os.path.expanduser("~"), ".config", app_name)
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "config.json")
        self.log_file = os.path.join(config_dir, "sync_log.json")
        self._ensure_dir()
        # 从旧目录迁移数据（如果旧目录存在且新目录为空）
        self._migrate_from_old_dir()
        self.config = self._load()
        self._migrate()

    def _migrate_from_old_dir(self):
        """从旧的软件目录下的 myftp 文件夹迁移数据到新目录"""
        # 如果新目录已有 config.json，不需要迁移
        if os.path.exists(self.config_file):
            return
        # 查找旧目录
        if getattr(sys, 'frozen', False):
            project_root = os.path.dirname(sys.executable)
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
        old_dir = os.path.join(project_root, "myftp")
        if not os.path.isdir(old_dir):
            return
        # 迁移所有文件和子目录
        import shutil
        try:
            for item in os.listdir(old_dir):
                src = os.path.join(old_dir, item)
                dst = os.path.join(self.config_dir, item)
                if os.path.isdir(src):
                    if not os.path.exists(dst):
                        shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        except Exception:
            pass

    def _ensure_dir(self):
        os.makedirs(self.config_dir, exist_ok=True)
        _set_hidden(self.config_dir)

    def _load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self._default_config()

    def _default_config(self):
        return {
            "servers": [],
            "settings": {
                "exclude_patterns": [],
                "auto_start_monitor": False,
                "debounce_seconds": 1.0,
                "upload_delay_seconds": 0.5,
            },
        }

    def _migrate(self):
        """兼容旧配置：将独立的 projects 合并到 servers 中"""
        changed = False
        old_projects = self.config.pop("projects", None)
        if old_projects:
            for p in old_projects:
                # 找到对应的服务器
                for s in self.config.get("servers", []):
                    if s["name"] == p.get("server_name"):
                        if "local_path" not in s or not s.get("local_path"):
                            s["local_path"] = p.get("local_path", "")
                        if "last_sync" not in s:
                            s["last_sync"] = p.get("last_sync")
                        if "sync_count" not in s:
                            s["sync_count"] = p.get("sync_count", 0)
                        # 如果项目的remote_path不同于服务器的，用项目的
                        if p.get("remote_path") and p["remote_path"] != s.get("remote_path"):
                            s["remote_path"] = p["remote_path"]
                        changed = True
                        break
            # 没找到对应服务器的项目，创建一个
            for p in old_projects:
                found = any(s["name"] == p.get("server_name") for s in self.config.get("servers", []))
                if not found:
                    self.config["servers"].append({
                        "name": p["name"],
                        "host": "",
                        "port": 21,
                        "username": "",
                        "password": "",
                        "remote_path": p.get("remote_path", "/"),
                        "local_path": p.get("local_path", ""),
                        "last_sync": p.get("last_sync"),
                        "sync_count": p.get("sync_count", 0),
                    })
                    changed = True
        # 确保每个 server 都有新字段
        for s in self.config.get("servers", []):
            if "local_path" not in s:
                s["local_path"] = ""
                changed = True
            if "last_sync" not in s:
                s["last_sync"] = None
                changed = True
            if "sync_count" not in s:
                s["sync_count"] = 0
                changed = True
            if "use_tls" not in s:
                s["use_tls"] = False
                changed = True
        if changed:
            self.save()

    def save(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    # ======================== 服务器管理 ========================

    def get_servers(self):
        return self.config.get("servers", [])

    def get_server(self, name):
        for s in self.get_servers():
            if s["name"] == name:
                return s
        return None

    def add_server(self, name, host, port=21, username="", password="",
                   remote_path="/", local_path="", use_tls=False):
        if self.get_server(name):
            return False, f"服务器 '{name}' 已存在"
        self.config["servers"].append({
            "name": name,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "remote_path": remote_path,
            "local_path": local_path,
            "use_tls": bool(use_tls),
            "last_sync": None,
            "sync_count": 0,
        })
        self.save()
        return True, f"服务器 '{name}' 添加成功"

    def update_server(self, name, **kwargs):
        for s in self.config["servers"]:
            if s["name"] == name:
                # 处理重命名
                new_name = kwargs.pop("new_name", None)
                if new_name and new_name != name:
                    # 检查新名称是否已存在
                    if any(srv["name"] == new_name for srv in self.config["servers"]):
                        return False, f"服务器名称 '{new_name}' 已存在"
                    s["name"] = new_name
                # 更新其他字段
                for k, v in kwargs.items():
                    if k in s or k == "use_tls":
                        s[k] = v
                self.save()
                display_name = new_name if new_name else name
                return True, f"服务器 '{display_name}' 更新成功"
        return False, f"服务器 '{name}' 不存在"

    def remove_server(self, name):
        before = len(self.config["servers"])
        self.config["servers"] = [s for s in self.config["servers"] if s["name"] != name]
        if len(self.config["servers"]) < before:
            self.save()
            return True, f"服务器 '{name}' 已删除"
        return False, f"服务器 '{name}' 不存在"

    # ======================== 兼容旧接口 ========================

    def get_projects(self):
        """兼容：返回服务器列表中配置了 local_path 的项作为项目"""
        return [s for s in self.get_servers() if s.get("local_path")]

    def get_project(self, name):
        """兼容：通过名称获取服务器（当作项目用）"""
        return self.get_server(name)

    # ======================== 设置管理 ========================

    def get_settings(self):
        return self.config.get("settings", {})

    def update_settings(self, **kwargs):
        self.config["settings"].update(kwargs)
        self.save()

    def get_exclude_patterns(self, server_name=None):
        """获取排除规则，如果指定了服务器名则返回该服务器的规则"""
        if server_name:
            server = self.get_server(server_name)
            if server:
                return server.get("exclude_patterns", [])
        # 返回全局默认规则
        return self.get_settings().get("exclude_patterns", [])
    
    def update_server_excludes(self, server_name, patterns):
        """更新指定服务器的排除规则"""
        for s in self.config["servers"]:
            if s["name"] == server_name:
                s["exclude_patterns"] = patterns
                self.save()
                return True, f"服务器 '{server_name}' 的排除规则已更新"
        return False, f"服务器 '{server_name}' 不存在"

    # ======================== 同步日志 ========================

    def load_log(self):
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"entries": []}

    def add_log_entry(self, project_name, action, file_path, status, message="", size=0, batch_id=None):
        log = self.load_log()
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "project": project_name,
            "action": action,
            "file": file_path,
            "status": status,
            "message": message,
            "size": size,
            "batch_id": batch_id,
        }
        log["entries"].insert(0, entry)
        # 最多保留500条
        log["entries"] = log["entries"][:500]
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)

    def clear_log(self):
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump({"entries": []}, f, indent=2, ensure_ascii=False)

    def get_log_entries(self, project_name=None, limit=100):
        log = self.load_log()
        entries = log.get("entries", [])
        if project_name:
            entries = [e for e in entries if e.get("project") == project_name]
        return entries[:limit]

    # ======================== 配置导入/导出 ========================

    def export_config(self, export_path):
        """导出配置（服务器列表+设置+同步日志）到指定文件"""
        import shutil
        data = {
            "config": self.config,
            "sync_log": self.load_log() if os.path.exists(self.log_file) else {"entries": []},
        }
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True, f"配置已导出到: {export_path}"

    def import_config(self, import_path):
        """从文件导入配置（覆盖当前配置）"""
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "config" not in data:
                return False, "无效的配置文件格式"
            self.config = data["config"]
            self.save()
            # 导入同步日志
            if "sync_log" in data:
                with open(self.log_file, "w", encoding="utf-8") as f:
                    json.dump(data["sync_log"], f, indent=2, ensure_ascii=False)
            return True, f"配置已从 {import_path} 导入成功"
        except (json.JSONDecodeError, IOError) as e:
            return False, f"导入失败: {e}"

    # ======================== 文件日志（按服务器分目录+时间戳） ========================

    def _get_file_logs_dir(self):
        """获取文件日志根目录: config_dir/logs/"""
        logs_dir = os.path.join(self.config_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        _set_hidden(logs_dir)
        return logs_dir

    def create_batch_log(self, server_name, operation_type, total_count):
        """创建批量操作日志文件

        在 config_dir/logs/服务器名/ 下创建 时间戳.log 文件

        Returns:
            (log_file_path, write_entry_func) - 文件路径和写入函数
        """
        # 构造服务器专属目录
        logs_dir = self._get_file_logs_dir()
        safe_name = server_name.replace("/", "_").replace("\\", "_").replace(":", "_")
        server_dir = os.path.join(logs_dir, safe_name)
        os.makedirs(server_dir, exist_ok=True)
        _set_hidden(server_dir)

        # 生成时间戳文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file_path = os.path.join(server_dir, f"{timestamp}.log")

        # 写入头部
        try:
            with open(log_file_path, "w", encoding="utf-8") as f:
                f.write(f"{'=' * 60}\n")
                f.write(f"=== 批量操作 ===\n")
                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"服务器: {server_name}\n")
                f.write(f"操作类型: {operation_type}\n")
                f.write(f"文件总数: {total_count}\n")
                f.write(f"{'-' * 60}\n")
        except Exception:
            pass

        # 返回写入函数（所有异常都静默处理，不影响主流程）
        def write_entry(file_path, action, status, message="", size=0):
            try:
                with open(log_file_path, "a", encoding="utf-8") as f:
                    status_symbol = "✓" if status == "success" else "✗"
                    size_str = f" ({size / 1024:.1f} KB)" if size > 0 else ""
                    entry_time = datetime.now().strftime("%H:%M:%S")
                    f.write(f"[{status_symbol}] {action}: {file_path}{size_str}\n")
                    if message:
                        f.write(f"    {message}\n")
                    f.write(f"    时间: {entry_time}\n\n")
            except Exception:
                pass

        return log_file_path, write_entry

    def write_batch_summary(self, log_file_path, success_count, fail_count, total_size):
        """写入批量操作摘要到文件日志"""
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"{'-' * 60}\n")
                f.write(f"摘要: 成功 {success_count} 个，失败 {fail_count} 个\n")
                if total_size > 0:
                    f.write(f"总大小: {total_size / 1024:.1f} KB\n")
                f.write(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'=' * 60}\n")
        except Exception:
            pass
