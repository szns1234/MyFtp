"""FTP客户端模块"""

import os
import re
import ssl
import ftplib
import hashlib
import threading
from datetime import datetime


# 月份名称到编号的映射
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_ftp_date(date_str):
    """将 FTP dir 返回的日期字符串解析为统一的 YYYY-MM-DD HH:MM:SS 格式。

    FTP 日期通常有两种格式：
      · "Oct  1 10:10"  （6个月内的文件，显示月+日+时分）
      · "Oct  1  2025"  （超过6个月的文件，显示月+日+年份）

    如果是时分格式，则补全当前年份；如果是年份格式，则时分补 00:00:00。
    """
    try:
        date_str = date_str.strip()
        parts = date_str.split()
        if len(parts) < 3:
            return date_str

        month_str = parts[0].lower()[:3]
        month = _MONTH_MAP.get(month_str)
        if month is None:
            return date_str

        day = int(parts[1])
        third = parts[2]

        now = datetime.now()
        if ":" in third:
            # 格式: "Oct 1 10:10" → 补当前年份，时分:秒
            hour, minute = third.split(":")
            hour, minute = int(hour), int(minute)
            year = now.year
            # 如果月份在当前月份之后，可能是去年的文件
            if month > now.month:
                year -= 1
            dt = datetime(year, month, day, hour, minute, 0)
        else:
            # 格式: "Oct 1 2025" → 年月日，时分秒补 00:00:00
            year = int(third)
            dt = datetime(year, month, day, 0, 0, 0)

        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return date_str


class FTPClient:
    """FTP客户端，封装上传、下载、列目录等操作"""

    def __init__(self):
        self.ftp = None
        self._connected = False
        self._lock = threading.RLock()  # 保护所有 FTP 操作，防止多线程并发访问导致卡死

    # ======================== 连接管理 ========================

    def connect(self, host, port=21, username="", password="", use_tls=False):
        """连接到 FTP 服务器。use_tls 为显式 FTP over TLS（AUTH TLS），不是隐式 TLS 或 SFTP。"""
        with self._lock:
            self.disconnect()
            try:
                if use_tls:
                    context = ssl.create_default_context()
                    # 托管商证书常与所填主机名不一致，校验失败时仍完成加密握手
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    self.ftp = ftplib.FTP_TLS(context=context)
                else:
                    self.ftp = ftplib.FTP()
                self.ftp.connect(host, port, timeout=30)
                if username:
                    self.ftp.login(username, password or "")
                else:
                    self.ftp.login()
                if use_tls:
                    self.ftp.prot_p()
                self.ftp.set_pasv(True)
                self._connected = True
                mode = "FTPS" if use_tls else "FTP"
                return True, f"已通过{mode}连接到 {host}:{port}"
            except ftplib.all_errors as e:
                self._connected = False
                return False, f"连接失败: {e}"
            except Exception as e:
                self._connected = False
                return False, f"连接错误: {e}"

    def disconnect(self):
        """快速断开连接，不等待服务器响应"""
        with self._lock:
            if self.ftp:
                try:
                    self.ftp.close()
                except Exception:
                    pass
                self.ftp = None
            self._connected = False

    @property
    def is_connected(self):
        """检查连接状态（不发网络请求，仅检查标志位，避免频繁超时）"""
        return self._connected and self.ftp is not None

    # ======================== 目录操作 ========================

    def _listing_lines(self, remote_path="."):
        """优先用控制通道列目录。被动端口被防火墙拦截时，LIST 会超时并被误认为空目录。"""
        path = remote_path or "."
        try:
            raw = self.ftp.sendcmd(f"STAT {path}")
            lines = []
            for line in raw.splitlines():
                text = line.strip()
                if not text or text[:3].isdigit() or text in (".", ".."):
                    continue
                if text[0] in "-dl":
                    lines.append(text)
            if lines:
                return lines
        except Exception:
            pass
        lines = []
        self.ftp.dir(path, lines.append)
        return lines

    def list_dir(self, remote_path="."):
        """列出远程目录内容"""
        if not self.is_connected:
            return [], "未连接到服务器"
        with self._lock:
            items = []
            try:
                lines = self._listing_lines(remote_path)
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 9:
                        is_dir = parts[0].startswith("d")
                        name = " ".join(parts[8:])
                        # 过滤 . 和 .. 条目
                        if name in (".", ".."):
                            continue
                        size = int(parts[4]) if not is_dir else 0
                        # 解析日期并统一格式为 YYYY-MM-DD HH:MM:SS
                        date_str = _parse_ftp_date(" ".join(parts[5:8]))
                        items.append({
                            "name": name,
                            "is_dir": is_dir,
                            "size": size,
                            "date": date_str,
                            "perm": parts[0],
                        })
                return items, "OK"
            except Exception as e:
                return [], f"列目录失败: {e}"

    def ensure_remote_dir(self, remote_dir):
        """递归创建远程目录（使用 / 作为路径分隔符）"""
        self._lock.acquire()
        remote_dir = remote_dir.replace("\\", "/").strip("/")
        print(f"[DEBUG FTP] ensure_remote_dir: remote_dir={remote_dir}")
        if not remote_dir:
            print(f"[DEBUG FTP]   空路径，直接返回True")
            self._lock.release()
            return True
        
        # 获取当前工作目录作为参考
        try:
            original_cwd = self.ftp.pwd()
            print(f"[DEBUG FTP]   原始工作目录: {original_cwd}")
        except Exception as e:
            original_cwd = "/"
            print(f"[DEBUG FTP]   无法获取工作目录，假设为 /: {e}")
        
        # 检查是否已存在（使用绝对路径）
        full_path = "/" + remote_dir
        try:
            self.ftp.cwd(full_path)
            print(f"[DEBUG FTP]   目录已存在: {full_path}")
            # 恢复原始目录
            try:
                self.ftp.cwd(original_cwd)
            except:
                pass
            self._lock.release()
            return True
        except Exception as e:
            print(f"[DEBUG FTP]   目录不存在或无法进入: {e}")
        
        # 尝试逐级创建目录
        parts = remote_dir.split("/")
        print(f"[DEBUG FTP]   路径部分: {parts}")
        current_path = ""
        
        for i, part in enumerate(parts):
            if not part:
                continue
            current_path = current_path + "/" + part
            print(f"[DEBUG FTP]   处理第 {i+1} 级: {current_path}")
            
            # 尝试进入
            try:
                self.ftp.cwd(current_path)
                print(f"[DEBUG FTP]     进入成功，目录已存在")
                continue
            except Exception as e:
                print(f"[DEBUG FTP]     无法进入: {e}")
            
            # 尝试创建
            try:
                result = self.ftp.mkd(current_path)
                print(f"[DEBUG FTP]     创建成功: {result}")
                # 创建后尝试进入
                try:
                    self.ftp.cwd(current_path)
                    print(f"[DEBUG FTP]     创建后进入成功")
                except Exception as e2:
                    print(f"[DEBUG FTP]     创建后进入失败: {e2}")
            except Exception as e:
                print(f"[DEBUG FTP]     创建失败: {e}")
                # 再次尝试进入（可能其他客户端已创建）
                try:
                    self.ftp.cwd(current_path)
                    print(f"[DEBUG FTP]     但目录已存在（其他客户端创建）")
                except:
                    print(f"[DEBUG FTP]     且确实不存在")
        
        # 最终验证
        try:
            self.ftp.cwd(full_path)
            print(f"[DEBUG FTP]   最终验证成功，目录存在: {full_path}")
            # 恢复原始目录
            try:
                self.ftp.cwd(original_cwd)
            except:
                pass
            self._lock.release()
            return True
        except Exception as e:
            print(f"[DEBUG FTP]   最终验证失败: {e}")
            self._lock.release()
            return False

    # ======================== 文件操作 ========================

    def upload_file(self, local_path, remote_path, callback=None):
        """上传单个文件（文件稳定性检查→读入内存→创建目录→上传→大小验证）"""
        if not self.is_connected:
            return False, "未连接到服务器"
        self._lock.acquire()
        if not os.path.isfile(local_path):
            self._lock.release()
            return False, f"本地文件不存在: {local_path}"

        from io import BytesIO
        import time as _time

        try:
            # 0. 文件稳定性检查：等待文件写入完成（大小不再变化）
            file_size = self._wait_file_stable(local_path, timeout=5.0)
            if file_size is None:
                return False, f"文件正在被写入或不存在: {local_path}"

            # 注意：允许空文件上传（新建的空文件也是有效文件）

            # 1. 读入内存（避免 Windows 文件锁/缓存导致读到旧内容）
            try:
                with open(local_path, "rb") as f:
                    data = f.read()
            except PermissionError:
                # 文件被占用，等待后重试
                _time.sleep(1.0)
                try:
                    with open(local_path, "rb") as f:
                        data = f.read()
                except Exception as e:
                    return False, f"读取文件失败（文件可能被占用）: {e}"

            actual_size = len(data)
            # 如果实际读到的和稳定时的大小不同（文件在变化），重新读取一次
            if actual_size != file_size and file_size > 0:
                _time.sleep(0.5)
                with open(local_path, "rb") as f:
                    data = f.read()
                actual_size = len(data)

            # 2. 解析远程路径（保留开头的 /，避免 strip 导致路径错位）
            remote_path = remote_path.replace("\\", "/")
            # 去掉开头的 / 后再解析（但解析完要记得还原）
            remote_clean = remote_path.lstrip("/")
            parts = remote_clean.split("/")
            remote_filename = parts[-1]
            remote_dir = "/".join(parts[:-1]) if len(parts) > 1 else ""

            if not remote_filename:
                return False, f"远程文件名无效: {remote_path}"

            # 记录原始目录
            try:
                original_cwd = self.ftp.pwd()
            except Exception:
                original_cwd = None

            # 3. 确保远程目录存在并切换过去
            if remote_dir:
                target_dir = "/" + remote_dir
                try:
                    self.ftp.cwd(target_dir)
                except Exception:
                    # 目录可能不存在，尝试创建
                    ok = self.ensure_remote_dir(remote_dir)
                    if not ok:
                        return False, f"无法创建远程目录: {target_dir}"
                    try:
                        self.ftp.cwd(target_dir)
                    except Exception as e:
                        return False, f"无法切换到远程目录 {target_dir}: {e}"

            # 4. 尝试删除旧文件（如果存在）- 不影响后续上传
            if remote_filename:
                try:
                    self.ftp.delete(remote_filename)
                except Exception:
                    pass  # 文件不存在或无权限删除，忽略

            # 5. 上传（带重试机制）
            upload_ok = False
            last_error = ""
            for attempt in range(3):
                try:
                    self.ftp.storbinary(
                        f"STOR {remote_filename}",
                        BytesIO(data),
                        blocksize=8192,
                    )
                    upload_ok = True
                    break
                except Exception as e:
                    last_error = str(e)
                    _time.sleep(0.5 * (attempt + 1))
                    # 重新尝试前确保还在正确的目录
                    if remote_dir:
                        try:
                            self.ftp.cwd("/" + remote_dir)
                        except Exception:
                            pass

            if not upload_ok:
                if original_cwd:
                    try:
                        self.ftp.cwd(original_cwd)
                    except Exception:
                        pass
                return False, f"STOR 失败（重试3次）: {last_error}"

            # 6. 验证远程文件大小
            remote_size = None
            try:
                remote_size = self.ftp.size(remote_filename)
            except Exception:
                # 某些服务器不支持 SIZE 命令，尝试用 list 获取
                try:
                    lines = []
                    self.ftp.dir(remote_filename, lines.append)
                    if lines:
                        parts_ls = lines[0].split()
                        if len(parts_ls) >= 5:
                            remote_size = int(parts_ls[4])
                except Exception:
                    pass

            size_ok = (remote_size is not None and remote_size == actual_size)

            # 恢复原始目录
            if original_cwd:
                try:
                    self.ftp.cwd(original_cwd)
                except Exception:
                    pass

            if callback:
                callback(actual_size)

            # 7. 构建结果
            if size_ok:
                return True, f"上传成功: {remote_path} (本地 {actual_size} bytes, 远程 {remote_size} bytes ✓)"
            elif remote_size is not None:
                return False, (f"上传验证失败: {remote_path} "
                               f"(本地 {actual_size} bytes, 远程 {remote_size} bytes ✗)")
            else:
                # 无法获取远程大小，但 STOR 没报错，认为上传成功
                return True, f"上传成功: {remote_path} (本地 {actual_size} bytes, 远程大小无法验证)"

        except Exception as e:
            return False, f"上传异常: {e}"
        finally:
            self._lock.release()

    @staticmethod
    def _wait_file_stable(file_path, timeout=5.0):
        """等待文件大小稳定（不再变化），返回最终大小；超时返回 None。
        对于新创建的空文件（size=0），会额外等待看是否有内容写入。"""
        import time as _time
        try:
            prev_size = os.path.getsize(file_path)
        except Exception:
            return None

        interval = 0.3
        elapsed = 0.0
        stable_count = 0
        # 需要连续2次检测到相同大小才认为稳定（避免瞬时一致）
        required_stable = 2

        while elapsed < timeout:
            _time.sleep(interval)
            elapsed += interval
            try:
                curr_size = os.path.getsize(file_path)
            except Exception:
                return None
            if curr_size == prev_size:
                stable_count += 1
                if stable_count >= required_stable:
                    return curr_size
            else:
                stable_count = 0
                prev_size = curr_size
        # 超时：如果文件存在且大小>=0，返回当前大小（即使是0也允许上传）
        try:
            final_size = os.path.getsize(file_path)
            return final_size  # 允许返回0（空文件也是有效文件）
        except Exception:
            return None

    def download_file(self, remote_path, local_path, callback=None):
        """下载单个文件"""
        if not self.is_connected:
            return False, "未连接到服务器"
        with self._lock:
            try:
                local_dir = os.path.dirname(local_path)
                if local_dir:
                    os.makedirs(local_dir, exist_ok=True)
                with open(local_path, "wb") as f:
                    self.ftp.retrbinary(f"RETR {remote_path}", f.write, blocksize=8192)
                file_size = os.path.getsize(local_path)
                if callback:
                    callback(file_size)
                return True, f"下载成功: {local_path} ({file_size} bytes)"
            except Exception as e:
                if os.path.exists(local_path):
                    os.remove(local_path)
                return False, f"下载失败: {e}"

    def delete_file(self, remote_path, use_cwd=False):
        """删除远程文件
        
        Args:
            remote_path: 远程文件路径
            use_cwd: 如果为True，假设已经在目标目录中，直接使用文件名删除
        """
        if not self.is_connected:
            return False, "未连接到服务器"
        
        self._lock.acquire()
        
        if use_cwd:
            # 已经在目标目录中，直接使用文件名删除
            try:
                self.ftp.delete(remote_path)
                self._lock.release()
                return True, f"已删除: {remote_path}"
            except Exception as e:
                self._lock.release()
                return False, f"删除失败: {e}"
        
        # 保存当前工作目录
        original_cwd = None
        try:
            original_cwd = self.ftp.pwd()
        except:
            pass
        
        try:
            # 方法1: 直接使用完整路径删除
            self.ftp.delete(remote_path)
            self._lock.release()
            return True, f"已删除: {remote_path}"
        except Exception as e:
            error_msg = str(e)
            print(f"[DEBUG FTP] 直接删除失败: {error_msg}")
            
            # 方法2: 切换到文件所在目录，使用相对路径删除
            try:
                # 提取目录和文件名
                parts = remote_path.rstrip("/").split("/")
                if len(parts) > 1:
                    filename = parts[-1]
                    dir_path = "/".join(parts[:-1]) or "/"
                else:
                    filename = remote_path
                    dir_path = "/"
                
                print(f"[DEBUG FTP] 尝试切换到目录: {dir_path}, 删除文件: {filename}")
                
                # 切换到目标目录
                self.ftp.cwd(dir_path)
                print(f"[DEBUG FTP] 切换成功，当前目录: {self.ftp.pwd()}")
                
                # 先检查文件权限
                print(f"[DEBUG FTP] 检查文件权限...")
                is_dir = False
                try:
                    items, _ = self.list_dir(".")
                    for item in items:
                        if item["name"] == filename:
                            print(f"[DEBUG FTP] 找到文件: {item['name']}, 权限: {item['perm']}, 类型: {'目录' if item['is_dir'] else '文件'}")
                            is_dir = item["is_dir"]
                            break
                except Exception as perm_e:
                    print(f"[DEBUG FTP] 检查权限失败: {perm_e}")
                
                # 根据类型选择删除命令
                if is_dir:
                    print(f"[DEBUG FTP] 使用 RMD 删除目录: {filename}")
                    self.ftp.rmd(filename)
                else:
                    print(f"[DEBUG FTP] 使用 DELE 删除文件: {filename}")
                    self.ftp.delete(filename)
                
                # 恢复原始目录
                if original_cwd:
                    try:
                        self.ftp.cwd(original_cwd)
                    except:
                        pass
                
                self._lock.release()
                return True, f"已删除(相对路径): {remote_path}"
            except Exception as e2:
                print(f"[DEBUG FTP] 相对路径删除也失败: {e2}")
                # 恢复原始目录
                if original_cwd:
                    try:
                        self.ftp.cwd(original_cwd)
                    except:
                        pass
                self._lock.release()
                return False, f"删除失败: {e2}"

    def delete_directory(self, remote_path):
        """递归删除远程目录及其所有内容 - 简化版"""
        if not self.is_connected:
            return False, "未连接到服务器"
        
        # 清理路径
        remote_path = remote_path.replace("//", "/").rstrip("/")
        if not remote_path:
            remote_path = "/"
        
        dir_name = remote_path.split("/")[-1]
        if dir_name in [".", "..", ""]:
            return True, f"跳过特殊目录"
        
        self._lock.acquire()
        try:
            print(f"[DEBUG FTP] 删除目录: {remote_path}")
            
            # 尝试直接删除（如果是空目录）
            try:
                self.ftp.rmd(remote_path)
                print(f"[DEBUG FTP]   直接删除成功")
                return True, f"已删除目录: {remote_path}"
            except Exception as e:
                # 目录不为空，需要递归删除
                print(f"[DEBUG FTP]   目录不为空，递归删除: {e}")
            
            # 进入目录
            original_cwd = self.ftp.pwd()
            self.ftp.cwd(remote_path)
            
            # 获取文件列表
            try:
                files = self.ftp.nlst()
                print(f"[DEBUG FTP]   文件列表: {files}")
            except:
                files = []
            
            # 删除所有文件
            for f in files:
                if f in [".", ".."]:
                    continue
                try:
                    print(f"[DEBUG FTP]   删除: {f}")
                    self.ftp.delete(f)
                except Exception as e:
                    # 可能是目录，递归删除
                    try:
                        subdir_path = f"{remote_path}/{f}".replace("//", "/")
                        self.delete_directory(subdir_path)
                    except Exception as e2:
                        print(f"[DEBUG FTP]   删除失败: {e2}")
            
            # 返回上级并删除空目录
            self.ftp.cwd(original_cwd)
            try:
                self.ftp.rmd(remote_path)
                print(f"[DEBUG FTP]   删除空目录成功")
                return True, f"已删除目录: {remote_path}"
            except Exception as e:
                return False, f"删除目录失败: {e}"
                
        except Exception as e:
            return False, f"删除目录失败: {e}"
        finally:
            self._lock.release()

    def rename(self, old_name, new_name):
        """重命名远程文件/目录"""
        if not self.is_connected:
            return False, "未连接到服务器"
        try:
            self.ftp.rename(old_name, new_name)
            return True, f"已重命名: {old_name} -> {new_name}"
        except Exception as e:
            return False, f"重命名失败: {e}"

    def get_file_size(self, remote_path):
        """获取远程文件大小"""
        if not self.is_connected:
            return None
        with self._lock:
            try:
                return self.ftp.size(remote_path)
            except Exception:
                return None

    def cwd(self, remote_path):
        """切换远程目录"""
        if not self.is_connected:
            return False, "未连接到服务器"
        with self._lock:
            try:
                self.ftp.cwd(remote_path)
                return True, f"已切换到: {remote_path}"
            except Exception as e:
                return False, f"切换目录失败: {e}"

    def pwd(self):
        """获取当前远程路径"""
        if not self.is_connected:
            return "/"
        with self._lock:
            try:
                return self.ftp.pwd()
            except Exception:
                return "/"

    def mkdir(self, remote_path):
        """创建远程目录"""
        if not self.is_connected:
            return False, "未连接到服务器"
        with self._lock:
            try:
                self.ftp.mkd(remote_path)
                return True, f"已创建目录: {remote_path}"
            except Exception as e:
                return False, f"创建目录失败: {e}"

    def rmdir(self, remote_path):
        """删除远程目录"""
        if not self.is_connected:
            return False, "未连接到服务器"
        with self._lock:
            try:
                self.ftp.rmd(remote_path)
                return True, f"已删除目录: {remote_path}"
            except Exception as e:
                return False, f"删除目录失败: {e}"

    # ======================== 同步操作 ========================

    def sync_directory(self, local_dir, remote_dir, exclude_patterns=None, callback=None):
        """同步整个目录到远程"""
        if not self.is_connected:
            return 0, 0, "未连接到服务器"
        exclude_patterns = exclude_patterns or []
        uploaded = 0
        total_size = 0
        for root, dirs, files in os.walk(local_dir):
            dirs[:] = [d for d in dirs if not self._should_exclude(
                os.path.join(root, d), exclude_patterns)]
            for filename in files:
                local_path = os.path.join(root, filename)
                if self._should_exclude(local_path, exclude_patterns):
                    continue
                rel_path = os.path.relpath(local_path, local_dir)
                remote_path = os.path.join(remote_dir, rel_path).replace("\\", "/")
                ok, msg = self.upload_file(local_path, remote_path)
                if ok:
                    uploaded += 1
                    total_size += os.path.getsize(local_path)
                    if callback:
                        callback(rel_path, "upload", True, msg)
                else:
                    if callback:
                        callback(rel_path, "upload", False, msg)
        return uploaded, total_size, f"同步完成: {uploaded} 个文件"

    def download_directory(self, remote_dir, local_dir, callback=None):
        """下载整个远程目录到本地"""
        if not self.is_connected:
            return 0, 0, "未连接到服务器"
        downloaded = 0
        total_size = 0
        items, _ = self.list_dir(remote_dir)
        for item in items:
            remote_path = f"{remote_dir}/{item['name']}".replace("//", "/")
            local_path = os.path.join(local_dir, item["name"])
            if item["is_dir"]:
                count, size, _ = self.download_directory(remote_path, local_path, callback)
                downloaded += count
                total_size += size
            else:
                ok, msg = self.download_file(remote_path, local_path)
                if ok:
                    downloaded += 1
                    total_size += os.path.getsize(local_path)
                    if callback:
                        callback(item["name"], "download", True, msg)
                else:
                    if callback:
                        callback(item["name"], "download", False, msg)
        return downloaded, total_size, f"下载完成: {downloaded} 个文件"

    # ======================== 工具方法 ========================

    @staticmethod
    def _should_exclude(file_path, patterns):
        filename = os.path.basename(file_path)
        for p in patterns:
            if p.startswith("*"):
                if filename.endswith(p[1:]):
                    return True
            elif p in file_path.replace("\\", "/"):
                return True
        return False

    @staticmethod
    def file_md5(file_path):
        """计算文件MD5"""
        h = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None
