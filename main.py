#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import logging
import subprocess
import time
import threading
import base64
import tempfile
import shutil
import atexit
import zipfile
import traceback

import tkinter as tk
from tkinter import messagebox, filedialog

import winreg
import ctypes

try:
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import psutil
import pyautogui
from win10toast import ToastNotifier
import pystray
from PIL import Image, ImageDraw

CONFIG = {
    "PROCESSES_PER_PAGE": 20,
    "FILES_PER_PAGE": 20,
    "DIR_ITEMS_PER_PAGE": 30,
    "SHUTDOWN_DELAY": 60,
    "CMD_TIMEOUT": 30,
    "MESSAGE_MAX_LENGTH": 4000,
    "TELEGRAM_MAX_FILE_SIZE": 2 * 1024 * 1024 * 1024,
    "CALLBACK_DATA_MAX_LENGTH": 64,
    "MAX_FILE_SIZE": 1024 * 1024 * 1024,
    "LOG_MAX_SIZE": 10 * 1024 * 1024,
    "LOG_MAX_LINES": 1000,
    "PROCESS_CACHE_TTL": 5,
    "WINDOW_CACHE_TTL": 10,
    "POLLING_TIMEOUT": 20,
    "POLLING_INTERVAL": 0,
    "ICON_SIZE": 64,
    "ICON_MIN_SIZE": 32,
    "TOAST_DURATION": 3,
    "SHUTDOWN_WAIT": 0.5,
    "PROCESS_WAIT_TIMEOUT": 3,
    "STARTUP_WAIT": 2,
    "ERROR_WAIT": 5,
    "CONFLICT_WAIT": 30,
    "API_ERROR_WAIT": 10,
    "BOT_STOP_TIMEOUT": 2,
    "PROCESS_REFRESH_WAIT": 0.5,
}

def is_frozen():
    return getattr(sys, 'frozen', False)

def get_app_dir():
    """Получение директории приложения"""
    return os.path.dirname(sys.executable) if is_frozen() else os.path.dirname(os.path.abspath(__file__))

def get_data_dir():
    data_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'ControlPCbotV2')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def encode_path(path):
    if not path:
        return ""
    try:
        return base64.b64encode(path.encode("utf-8")).decode("ascii")
    except Exception:
        return ""

def decode_path(encoded):
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        return ""

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def run_as_admin():
    if is_admin():
        return False
    try:
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1) > 32
    except Exception:
        return False

def requires_admin_path(path):
    try:
        path = os.path.abspath(os.path.normpath(path))
        admin_paths = [
            os.environ.get('ProgramFiles', 'C:\\Program Files'),
            os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
            os.environ.get('SystemRoot', 'C:\\Windows'),
            'C:\\Windows\\System32',
            'C:\\Windows\\SysWOW64',
        ]
        for admin_path in admin_paths:
            if admin_path:
                try:
                    admin_abs = os.path.abspath(admin_path)
                    if os.path.commonpath([path, admin_abs]) == admin_abs:
                        return True
                except (ValueError, OSError):
                    continue
        return False
    except (OSError, ValueError):
        return False

def get_temp_file(prefix="", suffix=""):
    return os.path.join(tempfile.gettempdir(), f"{prefix}{int(time.time() * 1000)}{suffix}")

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def safe_remove_file(filepath):
    if filepath and os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass

def safe_edit_or_send(bot, chat_id, message_id, text, reply_markup=None):
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except Exception:
        try:
            bot.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception:
            pass

def safe_answer_callback(bot, callback_id, text="", show_alert=False):
    try:
        bot.answer_callback_query(callback_id, text, show_alert=show_alert)
    except telebot.apihelper.ApiTelegramException:
        pass

def safe_send_message(bot, chat_id, text, **kwargs):
    """Безопасная отправка сообщения"""
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Ошибка отправки сообщения: {e}")
        return None

class InstallerWindow:
    def __init__(self):
        self.result = None
        self.root = None
        self._drag_data = {"x": 0, "y": 0}
        self._create_window()
    
    def _create_window(self):
        self.root = tk.Tk()
        self.root.title("ControlPCbotV2 - Установка")
        self.root.geometry("540x460")
        self.root.configure(bg="#1a1a1a")
        self.root.resizable(False, False)
        
        icon_path = os.path.join(get_app_dir(), 'icon.ico')
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass
        
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (self.root.winfo_width() // 2)
        y = (self.root.winfo_screenheight() // 2) - (self.root.winfo_height() // 2)
        self.root.geometry(f"+{x}+{y}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._setup_ui()
        self.root.after(100, self._fix_admin_clipboard)
    
    def _fix_admin_clipboard(self):
        try:
            self.root.update()
            hwnd = self.root.winfo_id()
            
            MSGFLT_ALLOW = 1
            messages = [
                0x0049,
                0x004A,
                0x0233,
                0x0031,
                0x0302,
                0x0303,
                0x0304,
                0x0305,
                0x0306,
                0x0307,
                0x0308,
                0x0309,
                0x030A,
                0x030B,
                0x030C,
                0x030D,
                0x030E,
                0x030F,
            ]
            
            for msg in messages:
                try:
                    ctypes.windll.user32.ChangeWindowMessageFilter(msg, MSGFLT_ALLOW)
                except Exception:
                    pass
            
            try:
                ChangeWindowMessageFilterEx = ctypes.windll.user32.ChangeWindowMessageFilterEx
                ChangeWindowMessageFilterEx.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
                ChangeWindowMessageFilterEx.restype = ctypes.c_bool
                
                MSGFLT_ALLOW = 1
                for msg in messages:
                    try:
                        ChangeWindowMessageFilterEx(hwnd, msg, MSGFLT_ALLOW, None)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
    
    def _enable_clipboard(self, entry):
        entry.bind('<Control-v>', lambda e: entry.event_generate('<<Paste>>'))
        entry.bind('<Control-V>', lambda e: entry.event_generate('<<Paste>>'))
        entry.bind('<Control-c>', lambda e: entry.event_generate('<<Copy>>'))
        entry.bind('<Control-C>', lambda e: entry.event_generate('<<Copy>>'))
        entry.bind('<Control-x>', lambda e: entry.event_generate('<<Cut>>'))
        entry.bind('<Control-X>', lambda e: entry.event_generate('<<Cut>>'))
        entry.bind('<Control-a>', lambda e: entry.select_range(0, tk.END))
        entry.bind('<Control-A>', lambda e: entry.select_range(0, tk.END))
    
    def _setup_ui(self):
        content = tk.Frame(self.root, bg="#1a1a1a")
        content.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        default_path = os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'ControlPCbotV2')
        self.add_start = tk.BooleanVar(value=True)
        self.add_desktop = tk.BooleanVar(value=True)
        
        tk.Label(content, text="Telegram Bot Token:", bg="#1a1a1a",
                fg="#e0e0e0", font=("Segoe UI", 10)).grid(row=0, column=0, sticky=tk.W, padx=25, pady=(25, 5))
        self.entry_token = tk.Entry(content, width=50, bg="#2d2d2d", fg="white",
                                   insertbackground="white", font=("Segoe UI", 9),
                                   relief=tk.FLAT, borderwidth=1,
                                   highlightthickness=1, highlightbackground="#3c3c3c",
                                   highlightcolor="#0078d4", exportselection=0)
        self.entry_token.grid(row=1, column=0, padx=25, pady=(0, 15), sticky=tk.EW)
        self._enable_clipboard(self.entry_token)
        
        tk.Label(content, text="Chat ID:", bg="#1a1a1a",
                fg="#e0e0e0", font=("Segoe UI", 10)).grid(row=2, column=0, sticky=tk.W, padx=25, pady=(0, 5))
        self.entry_chat = tk.Entry(content, width=50, bg="#2d2d2d", fg="white",
                                  insertbackground="white", font=("Segoe UI", 9),
                                  relief=tk.FLAT, borderwidth=1,
                                  highlightthickness=1, highlightbackground="#3c3c3c",
                                  highlightcolor="#0078d4", exportselection=0)
        self.entry_chat.grid(row=3, column=0, padx=25, pady=(0, 15), sticky=tk.EW)
        self._enable_clipboard(self.entry_chat)
        
        tk.Label(content, text="Путь установки:", bg="#1a1a1a",
                fg="#e0e0e0", font=("Segoe UI", 10)).grid(row=4, column=0, sticky=tk.W, padx=25, pady=(0, 5))
        path_frame = tk.Frame(content, bg="#1a1a1a")
        path_frame.grid(row=5, column=0, padx=25, pady=(0, 15), sticky=tk.EW)
        self.entry_path = tk.Entry(path_frame, width=38, bg="#2d2d2d", fg="white",
                                   insertbackground="white", font=("Segoe UI", 9),
                                   relief=tk.FLAT, borderwidth=1,
                                   highlightthickness=1, highlightbackground="#3c3c3c",
                                   highlightcolor="#0078d4", exportselection=0)
        self.entry_path.insert(0, default_path)
        self.entry_path.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._enable_clipboard(self.entry_path)
        tk.Button(path_frame, text="Обзор...", command=self._browse,
                 bg="#0078d4", fg="white", font=("Segoe UI", 9),
                 relief=tk.FLAT, width=10, cursor="hand2",
                 activebackground="#106ebe").pack(side=tk.LEFT, padx=(10, 0))
        
        tk.Checkbutton(content, text="Добавить в список приложений",
                      variable=self.add_start, bg="#1a1a1a", fg="#e0e0e0",
                      selectcolor="#0078d4", activebackground="#1a1a1a",
                      activeforeground="#e0e0e0", font=("Segoe UI", 9),
                      cursor="hand2").grid(row=6, column=0, sticky=tk.W, padx=25, pady=(0, 8))
        tk.Checkbutton(content, text="Добавить ярлык на рабочий стол",
                      variable=self.add_desktop, bg="#1a1a1a", fg="#e0e0e0",
                      selectcolor="#0078d4", activebackground="#1a1a1a",
                      activeforeground="#e0e0e0", font=("Segoe UI", 9),
                      cursor="hand2").grid(row=7, column=0, sticky=tk.W, padx=25, pady=(0, 15))
        
        btn_frame = tk.Frame(content, bg="#1a1a1a")
        btn_frame.grid(row=8, column=0, padx=25, pady=(10, 25), sticky=tk.E)
        tk.Button(btn_frame, text="Отмена", command=self._on_close,
                 bg="#3c3c3c", fg="white", font=("Segoe UI", 10),
                 relief=tk.FLAT, width=12, height=1, cursor="hand2",
                 activebackground="#4c4c4c").pack(side=tk.RIGHT, padx=(10, 0))
        tk.Button(btn_frame, text="Установить", command=self._install,
                 bg="#0078d4", fg="white", font=("Segoe UI", 10, "bold"),
                 relief=tk.FLAT, width=12, height=1, cursor="hand2",
                 activebackground="#106ebe").pack(side=tk.RIGHT)
        content.columnconfigure(0, weight=1)
        path_frame.columnconfigure(0, weight=1)
    
    def _browse(self):
        folder = filedialog.askdirectory(title="Выберите папку для установки")
        if folder:
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, os.path.join(folder, "ControlPCbotV2"))
    
    def _install(self):
        token = self.entry_token.get().strip()
        chat_id = self.entry_chat.get().strip()
        path = self.entry_path.get().strip()
        if not token:
            messagebox.showerror("Ошибка", "Введите Telegram Bot Token")
            return
        if not chat_id or not chat_id.isdigit():
            messagebox.showerror("Ошибка", "Введите корректный Chat ID")
            return
        self.result = {"token": token, "chat_id": chat_id, "path": path,
                      "start": self.add_start.get(), "desktop": self.add_desktop.get()}
        self._close()
    
    def _on_close(self):
        self.result = None
        self._close()
    
    def _close(self):
        if self.root:
            try:
                self.root.quit()
            except Exception:
                pass
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
    
    def show(self):
        if not self.root:
            self._create_window()
        try:
            self.root.mainloop()
        except Exception:
            pass
        return self.result

def needs_admin_for_install(install_path):
    abs_path = os.path.abspath(install_path)
    program_files = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)")
    ]
    
    for pf in program_files:
        if pf:
            try:
                pf_abs = os.path.abspath(pf)
                if os.path.commonpath([abs_path, pf_abs]) == pf_abs:
                    return True
            except (ValueError, OSError):
                continue
    return False

def create_shortcuts(main_exe, add_start, add_desktop):
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcuts = []
        
        if add_start:
            shortcuts.append(os.path.join(
                os.environ.get('APPDATA', ''),
                'Microsoft', 'Windows', 'Start Menu', 'Programs', 'ControlPCbotV2.lnk'
            ))
        
        if add_desktop:
            shortcuts.append(os.path.join(
                os.environ.get('USERPROFILE', ''), 'Desktop', 'ControlPCbotV2.lnk'
            ))
        
        for shortcut_path in shortcuts:
            sc = shell.CreateShortCut(shortcut_path)
            sc.Targetpath = main_exe
            sc.WorkingDirectory = os.path.dirname(main_exe)
            sc.IconLocation = main_exe
            sc.save()
    except Exception:
        pass

def add_to_autostart(main_exe):
    """Добавление программы в автозапуск"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "ControlPCbotV2", 0, winreg.REG_SZ, f'"{main_exe}"')
    except Exception:
        pass

def run_installer():
    if not is_frozen():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Ошибка",
            "Установка возможна только из скомпилированного exe файла.\n"
            "Сначала скомпилируйте программу через compile.bat")
        root.destroy()
        return
    
    installer = InstallerWindow()
    result = installer.show()
    if not result:
        return
    
    install_path = result["path"]
    token = result["token"]
    chat_id = result["chat_id"]
    add_start = result["start"]
    add_desktop = result["desktop"]
    
    if needs_admin_for_install(install_path) and not is_admin():
        root = tk.Tk()
        root.withdraw()
        if messagebox.askyesno("Требуются права администратора",
                              "Для установки в Program Files требуются права администратора.\n"
                              "Перезапустить установщик от имени администратора?"):
            root.destroy()
            if run_as_admin():
                sys.exit(0)
        root.destroy()
        return
    
    if os.path.exists(install_path):
        root = tk.Tk()
        root.withdraw()
        if not messagebox.askyesno("Папка существует",
                                  f"Папка {install_path} уже существует.\nПерезаписать?"):
            root.destroy()
            return
        root.destroy()
        try:
            shutil.rmtree(install_path)
        except Exception as e:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Ошибка", f"Не удалось удалить папку:\n{str(e)}")
            root.destroy()
            return
    
    try:
        os.makedirs(install_path, exist_ok=True)
        main_exe = os.path.join(install_path, 'ControlPCbotV2.exe')
        shutil.copy(sys.executable, main_exe)
        
        with open(os.path.join(install_path, 'config.json'), 'w', encoding='utf-8') as f:
            json.dump({'TOKEN': token, 'CHAT_ID': int(chat_id)}, f, indent=2)
        
        icon_source = os.path.join(get_app_dir(), 'icon.ico')
        if os.path.exists(icon_source):
            try:
                shutil.copy(icon_source, os.path.join(install_path, 'icon.ico'))
            except Exception:
                pass
        
        if add_start:
            add_to_autostart(main_exe)
        
        create_shortcuts(main_exe, add_start, add_desktop)
        
        root = tk.Tk()
        root.withdraw()
        if messagebox.askyesno("Успех",
                              "Установка завершена успешно!\n\n"
                              "Программа будет запущена автоматически при следующем входе в систему.\n\n"
                              "Запустить программу сейчас?"):
            root.destroy()
            time.sleep(CONFIG["SHUTDOWN_WAIT"])
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                subprocess.Popen([main_exe], cwd=install_path, shell=False, startupinfo=startupinfo)
            except Exception:
                pass
        else:
            root.destroy()
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Ошибка установки", f"Произошла ошибка при установке:\n{str(e)}")
        root.destroy()

class BotApp:
    """Основной класс приложения Telegram-бота"""
    def __init__(self):
        self.app_dir = get_app_dir()
        self.data_dir = get_data_dir()
        self.config_path = os.path.join(self.app_dir, 'config.json')
        self.log_file = os.path.join(self.data_dir, 'command_log.txt')
        self.bot = None
        self.bot_thread = None
        self.running = False
        self.icon = None
        self.user_state = {}
        self.process_cache = {}
        self.process_cache_time = 0
        self.visible_windows_cache = None
        self.visible_windows_cache_time = 0
        self.token = ""
        self.chat_id = 0
        self.notifications_enabled = False
        self._is_frozen = is_frozen()
        self._setup_logging()
        self._load_config()
    
    def _setup_logging(self):
        try:
            log_path = os.path.join(self.data_dir, 'app.log')
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[logging.FileHandler(log_path, encoding='utf-8')]
            )
        except (OSError, IOError) as e:
            print(f"Ошибка настройки логирования: {e}")
    
    def _load_config(self):
        """Загрузка конфигурации из файла"""
        if not os.path.exists(self.config_path):
            logging.warning(f"Файл конфигурации не найден: {self.config_path}")
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.token = config.get('TOKEN', '')
                self.chat_id = config.get('CHAT_ID', 0)
        except (OSError, IOError) as e:
            logging.error(f"Ошибка чтения конфигурации: {e}")
        except json.JSONDecodeError as e:
            logging.error(f"Ошибка парсинга конфигурации: {e}")
    
    def _log_command(self, command, output):
        try:
            if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > CONFIG["LOG_MAX_SIZE"]:
                try:
                    with open(self.log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    if len(lines) > CONFIG["LOG_MAX_LINES"]:
                        with open(self.log_file, 'w', encoding='utf-8') as f:
                            f.writelines(lines[-CONFIG["LOG_MAX_LINES"]:])
                except (OSError, IOError):
                    safe_remove_file(self.log_file)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Command: {command}\nOutput: {output[:5000]}\n\n")
        except (OSError, IOError) as e:
            logging.error(f"Ошибка записи в лог: {e}")
    
    def _show_notification(self, message, force=False):
        try:
            if force or self.notifications_enabled:
                ToastNotifier().show_toast("ControlPCbotV2", message, duration=CONFIG["TOAST_DURATION"], threaded=True)
        except Exception:
            pass
    
    def _get_icon_paths(self):
        """Получение списка возможных путей к иконке"""
        return [
            os.path.join(self.app_dir, 'icon.ico'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)) if not self._is_frozen else os.path.dirname(sys.executable), 'icon.ico'),
            os.path.join(sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(os.path.abspath(__file__)), 'icon.ico'),
        ]
    
    def _load_icon_from_file(self, icon_path):
        try:
            ico_image = Image.open(icon_path)
            current_size = max(ico_image.size[0], ico_image.size[1])
            
            if current_size > CONFIG["ICON_SIZE"]:
                ico_image = ico_image.resize((CONFIG["ICON_SIZE"], CONFIG["ICON_SIZE"]), Image.Resampling.LANCZOS)
            elif current_size < CONFIG["ICON_MIN_SIZE"]:
                ico_image = ico_image.resize((CONFIG["ICON_MIN_SIZE"], CONFIG["ICON_MIN_SIZE"]), Image.Resampling.LANCZOS)
            
            if ico_image.mode != 'RGBA':
                ico_image = ico_image.convert('RGBA')
            
            return ico_image
        except Exception as e:
            logging.error(f"Ошибка загрузки иконки из {icon_path}: {e}")
            return None
    
    def _create_default_icon(self):
        """Создание иконки по умолчанию"""
        size = CONFIG["ICON_SIZE"]
        image = Image.new('RGBA', (size, size), color=(0, 120, 212, 255))
        draw = ImageDraw.Draw(image)
        margin = size // 4
        draw.ellipse([margin, margin, size - margin, size - margin], fill='white')
        return image
    
    def _create_icon(self):
        for icon_path in self._get_icon_paths():
            if os.path.exists(icon_path):
                icon = self._load_icon_from_file(icon_path)
                if icon:
                    return icon
        
        return self._create_default_icon()
    
    def start_bot(self):
        if not self.token or not self.chat_id:
            self._show_notification("Ошибка: Не настроены токен или Chat ID", force=True)
            return
        if self.running:
            return
        self.running = True
        try:
            self.bot_thread = threading.Thread(target=self._run_bot, daemon=True)
            self.bot_thread.start()
            self._show_notification("Бот запущен", force=True)
        except Exception as e:
            self.running = False
            self._show_notification(f"Ошибка запуска: {str(e)[:50]}", force=True)
            logging.error(f"Ошибка запуска бота: {e}")
    
    def stop_bot(self):
        if not self.running:
            return
        self.running = False
        if self.bot:
            try:
                self.bot.stop_polling()
            except Exception:
                pass
        if self.bot_thread:
            self.bot_thread.join(timeout=CONFIG["BOT_STOP_TIMEOUT"])
        self._show_notification("Бот остановлен", force=True)
    
    def _clear_process_cache(self):
        self.process_cache.clear()
        self.process_cache_time = 0
        self.visible_windows_cache = None
        self.visible_windows_cache_time = 0
    
    def _is_cache_valid(self, cache_time, ttl):
        """Проверка валидности кэша"""
        return (time.time() - cache_time) < ttl
    
    def _decode_cmd_output(self, stdout, stderr):
        output = None
        error_output = None
        encodings = ['utf-8', 'cp866', 'cp1251', 'latin-1']
        
        for encoding in encodings:
            try:
                if stdout:
                    output = stdout.decode(encoding, errors='replace')
                if stderr:
                    error_output = stderr.decode(encoding, errors='replace')
                if output or error_output:
                    break
            except (UnicodeDecodeError, AttributeError):
                continue
        
        if not output and error_output:
            return error_output
        elif output and error_output:
            return f"{output}\n\nОшибки:\n{error_output}"
        return output
    
    def _check_and_notify_reboot(self):
        try:
            first_run_flag = os.path.join(self.data_dir, 'first_run.flag')
            if os.path.exists(first_run_flag):
                try:
                    self.bot.send_message(self.chat_id, "🔄 Компьютер был перезагружен, система вновь доступна!")
                except Exception as e:
                    logging.error(f"Ошибка отправки сообщения о перезагрузке: {e}")
            else:
                try:
                    with open(first_run_flag, 'w', encoding='utf-8') as f:
                        f.write('')
                except Exception:
                    pass
        except Exception:
            pass
    
    def _run_bot(self):
        try:
            self.bot = telebot.TeleBot(self.token)
            self._setup_bot_handlers()
            time.sleep(CONFIG["STARTUP_WAIT"])
            self._check_and_notify_reboot()
            while self.running:
                try:
                    self.bot.polling(none_stop=True, interval=CONFIG["POLLING_INTERVAL"], timeout=CONFIG["POLLING_TIMEOUT"])
                except telebot.apihelper.ApiTelegramException as e:
                    if not self.running:
                        break
                    error_str = str(e)
                    if "Unauthorized" in error_str or "invalid token" in error_str.lower():
                        logging.error("Неверный токен бота")
                        self._show_notification("Ошибка: Неверный токен бота", force=True)
                        self.running = False
                        break
                    elif "Conflict" in error_str:
                        time.sleep(CONFIG["CONFLICT_WAIT"])
                    else:
                        logging.error(f"Telegram API ошибка: {e}")
                        time.sleep(CONFIG["API_ERROR_WAIT"])
                except Exception as e:
                    if not self.running:
                        break
                    logging.error(f"Ошибка бота: {e}")
                    time.sleep(CONFIG["ERROR_WAIT"])
        except Exception as e:
            logging.error(f"Критическая ошибка в _run_bot: {e}")
            self.running = False
            self._show_notification(f"Ошибка запуска: {str(e)[:50]}", force=True)
    
    def _setup_bot_handlers(self):
        @self.bot.message_handler(func=lambda m: m.chat.id != self.chat_id)
        def handle_unauthorized(message):
            self.bot.reply_to(message, "⛔ Доступ запрещен")
        
        @self.bot.message_handler(commands=['start', 'menu'])
        def send_welcome(message):
            if message.chat.id != self.chat_id:
                return
            help_text = ("📱 Главное меню управления ControlPCbotV2:\n\n"
                        "Доступные команды:\n"
                        "/menu - Главное меню\n"
                        "/cmd [команда] - Выполнить команду в CMD\n"
                        "/dir \"путь к директории\" - Просмотр содержимого директории\n"
                        "/dfile \"путь к файлу\" - Скачать файл (макс. 1ГБ)\n"
                        "/lfile \"путь до папки\" - Загрузить файл по пути (макс. 1ГБ)")
            self.bot.send_message(message.chat.id, help_text, reply_markup=self._create_main_menu())
        
        @self.bot.message_handler(commands=['dfile'])
        def handle_dfile(message):
            if message.chat.id != self.chat_id:
                return
            command = message.text.replace('/dfile', '', 1).strip()
            if not command:
                self.bot.reply_to(message, "ℹ️ Использование: /dfile \"путь к файлу\"")
                return
            if command.startswith('"') and command.endswith('"'):
                command = command[1:-1]
            elif command.startswith("'") and command.endswith("'"):
                command = command[1:-1]
            self._handle_download_file(message, command)
        
        @self.bot.message_handler(commands=['dir'])
        def handle_dir(message):
            if message.chat.id != self.chat_id:
                return
            command = message.text.replace('/dir', '', 1).strip()
            if not command:
                self.bot.reply_to(message, "ℹ️ Использование: /dir \"путь до папки\"")
                return
            if command.startswith('"') and command.endswith('"'):
                command = command[1:-1]
            elif command.startswith("'") and command.endswith("'"):
                command = command[1:-1]
            self._handle_dir_command(message, command)
        
        @self.bot.message_handler(commands=['lfile'])
        def handle_lfile(message):
            if message.chat.id != self.chat_id:
                return
            command = message.text.replace('/lfile', '', 1).strip()
            if not command:
                self.bot.reply_to(message, "ℹ️ Использование: /lfile путь к папке\n\nОтправьте файл в ответ на это сообщение")
                return
            try:
                if requires_admin_path(command):
                    self.bot.reply_to(message, "❌ Работа с этим путем требует прав администратора")
                    return
                abs_path = os.path.abspath(command)
                if os.path.isdir(abs_path):
                    pass
                elif os.path.isfile(abs_path):
                    self.bot.reply_to(message, "❌ Указан путь к файлу, требуется путь к папке")
                    return
                else:
                    parent_dir = os.path.dirname(abs_path)
                    if not os.path.exists(parent_dir):
                        self.bot.reply_to(message, "❌ Указанный путь не существует или недоступен")
                        return
            except (OSError, ValueError) as e:
                self.bot.reply_to(message, f"❌ Ошибка проверки пути: {str(e)[:50]}")
                return
            self.user_state[f"upload_path_{message.chat.id}"] = command
            self.bot.reply_to(message, f"📤 Путь сохранен: {command}\n\nОтправьте файл в ответ на это сообщение")
        
        @self.bot.message_handler(content_types=['document', 'photo', 'video', 'audio', 'voice', 'video_note'])
        def handle_file_upload(message):
            if message.chat.id != self.chat_id:
                return
            upload_path_key = f"upload_path_{message.chat.id}"
            if upload_path_key not in self.user_state:
                return
            
            upload_path = self.user_state[upload_path_key]
            del self.user_state[upload_path_key]
            
            file_id = None
            file_name = None
            file_size = 0
            
            if message.document:
                file_id = message.document.file_id
                file_name = message.document.file_name
                file_size = message.document.file_size or 0
            elif message.photo:
                file_id = message.photo[-1].file_id
                file_name = f"photo_{message.photo[-1].file_id}.jpg"
                file_size = message.photo[-1].file_size or 0
            elif message.video:
                file_id = message.video.file_id
                file_name = message.video.file_name or f"video_{message.video.file_id}.mp4"
                file_size = message.video.file_size or 0
            elif message.audio:
                file_id = message.audio.file_id
                file_name = message.audio.file_name or f"audio_{message.audio.file_id}.mp3"
                file_size = message.audio.file_size or 0
            elif message.voice:
                file_id = message.voice.file_id
                file_name = f"voice_{message.voice.file_id}.ogg"
                file_size = message.voice.file_size or 0
            elif message.video_note:
                file_id = message.video_note.file_id
                file_name = f"video_note_{message.video_note.file_id}.mp4"
                file_size = message.video_note.file_size or 0
            
            if not file_id:
                self.bot.reply_to(message, "❌ Не удалось получить информацию о файле")
                return
            
            if file_size > CONFIG["MAX_FILE_SIZE"]:
                self.bot.reply_to(message, f"❌ Файл слишком большой ({format_size(file_size)}). Макс: {format_size(CONFIG['MAX_FILE_SIZE'])}")
                return
            
            if requires_admin_path(upload_path):
                self.bot.reply_to(message, "❌ Работа с этим путем требует прав администратора")
                return
            
            encoded_path = encode_path(upload_path)
            encoded_file_id = encode_path(f"{file_id}|{file_name}")
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("✅ Подтвердить", callback_data=f"upload_confirm_{encoded_path}|||{encoded_file_id}"))
            keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="main_menu"))
            self.bot.reply_to(message, f"⚠️ Подтверждение загрузки файла\n\n📄 {file_name}\nРазмер: {format_size(file_size)}\nПуть: {upload_path}\n\nПодтвердите загрузку:", reply_markup=keyboard)
        
        @self.bot.message_handler(commands=['cmd'])
        def handle_cmd(message):
            if message.chat.id != self.chat_id:
                return
            command = message.text.replace('/cmd', '', 1).strip()
            if not command:
                self.bot.reply_to(message, "ℹ️ Использование: /cmd [команда]")
                return
            dangerous_commands = ['format', 'del /f /s /q', 'rmdir /s /q']
            if any(danger in command.lower() for danger in dangerous_commands):
                self.bot.reply_to(message, "⚠️ Выполнение опасных команд ограничено")
                self._log_command(command, "Blocked: dangerous command")
                return
            
            temp_file = None
            try:
                result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      timeout=CONFIG["CMD_TIMEOUT"], cwd=os.path.expanduser("~"))
                
                output = self._decode_cmd_output(result.stdout, result.stderr)
                if not output:
                    output = "Команда выполнена успешно" if result.returncode == 0 else "Команда завершилась с ошибкой"
                
                self._log_command(command, output)
                self._show_notification(f"Выполнена команда: {command[:40]}")
                
                if len(output) > CONFIG["MESSAGE_MAX_LENGTH"]:
                    temp_file = get_temp_file("controlpcbot_output_", ".txt")
                    try:
                        with open(temp_file, 'w', encoding="utf-8") as f:
                            f.write(output)
                        with open(temp_file, "rb") as f:
                            self.bot.send_document(message.chat.id, f, caption="Результат выполнения команды")
                    except (OSError, IOError) as e:
                        logging.error(f"Ошибка отправки файла: {e}")
                        self.bot.reply_to(message, f"⚠️ Ошибка: {str(e)}")
                else:
                    try:
                        self.bot.reply_to(message, f"```\n{output}\n```", parse_mode="Markdown")
                    except telebot.apihelper.ApiTelegramException:
                        self.bot.reply_to(message, output)
            except subprocess.TimeoutExpired:
                self._log_command(command, "Timeout")
                self.bot.reply_to(message, "⚠️ Команда превысила время ожидания")
            except (OSError, subprocess.SubprocessError) as e:
                logging.error(f"Ошибка выполнения команды: {e}")
                self._log_command(command, f"Error: {str(e)}")
                self.bot.reply_to(message, f"⚠️ Ошибка: {str(e)}")
            finally:
                safe_remove_file(temp_file)
        
        @self.bot.callback_query_handler(func=lambda call: call.message.chat.id == self.chat_id)
        def handle_callback(call):
            safe_answer_callback(self.bot, call.id)
            
            try:
                action = call.data
                if not action or len(action) > CONFIG["CALLBACK_DATA_MAX_LENGTH"]:
                    return
                
                if action == "main_menu":
                    safe_edit_or_send(self.bot, call.message.chat.id, call.message.message_id,
                                    "📱 Главное меню управления ControlPCbotV2:",
                                    reply_markup=self._create_main_menu())
                elif action == "screenshot":
                    self._handle_screenshot(call)
                elif action == "shutdown":
                    self._handle_shutdown_confirm(call)
                elif action == "shutdown_confirm":
                    self._handle_shutdown_execute(call)
                elif action == "reboot":
                    self._handle_reboot_confirm(call)
                elif action == "reboot_confirm":
                    self._handle_reboot_execute(call)
                elif action == "lock_screen":
                    self._handle_lock_screen(call)
                elif action == "volume_control":
                    self._handle_volume_menu(call)
                elif action == "volume_mute":
                    self._handle_volume_mute(call)
                elif action == "volume_up":
                    self._handle_volume_up(call)
                elif action == "volume_down":
                    self._handle_volume_down(call)
                elif action.startswith("download_confirm_"):
                    self._handle_download_confirm(call, action)
                elif action.startswith("download_execute_"):
                    self._handle_download_execute(call, action)
                elif action.startswith("upload_confirm_"):
                    self._handle_upload_confirm(call, action)
                elif action == "proc_menu":
                    self._handle_process_menu(call)
                elif action == "proc_list_apps":
                    self.user_state["last_process_category"] = "apps"
                    self.user_state["last_process_page"] = 0
                    self._handle_process_list(call, "apps", 0)
                elif action == "proc_list_bg":
                    self.user_state["last_process_category"] = "bg"
                    self.user_state["last_process_page"] = 0
                    self._handle_process_list(call, "bg", 0)
                elif action == "proc_list_sys":
                    self.user_state["last_process_category"] = "sys"
                    self.user_state["last_process_page"] = 0
                    self._handle_process_list(call, "sys", 0)
                elif action.startswith("proc_"):
                    self._handle_process_action(call, action)
                elif action.startswith("dir_pg_"):
                    self._handle_dir_page(call, action)
            except (AttributeError, ValueError, KeyError) as e:
                logging.error(f"Ошибка обработки callback: {e}")
                safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)[:50]}")
    
    def _create_main_menu(self):
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🖥️ Выключить ПК", callback_data="shutdown"),
            InlineKeyboardButton("🔄 Перезагрузить ПК", callback_data="reboot"),
            InlineKeyboardButton("📸 Скриншот", callback_data="screenshot"),
            InlineKeyboardButton("⚙️ Управление процессами", callback_data="proc_menu"),
            InlineKeyboardButton("🔊 Управление громкостью", callback_data="volume_control"),
            InlineKeyboardButton("🔒 Блокировка экрана", callback_data="lock_screen"),
            InlineKeyboardButton("👤 Автор", url="https://github.com/MrachniyTipchek"),
        )
        return keyboard
    
    def _handle_screenshot(self, call):
        temp_file = None
        try:
            screenshot = pyautogui.screenshot()
            temp_file = get_temp_file("controlpcbot_screenshot_", ".png")
            screenshot.save(temp_file, 'PNG')
            with open(temp_file, 'rb') as photo:
                self.bot.send_photo(call.message.chat.id, photo, caption="📸 Скриншот выполнен успешно")
            self._log_command("Screenshot", "Taken")
            self._show_notification("Выполнен скриншот экрана")
        except (OSError, IOError, pyautogui.FailSafeException) as e:
            logging.error(f"Ошибка создания скриншота: {e}")
            safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)[:50]}")
        finally:
            safe_remove_file(temp_file)
    
    def _handle_shutdown_confirm(self, call):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Да, завершить", callback_data="shutdown_confirm"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data="main_menu")
        )
        safe_edit_or_send(self.bot, call.message.chat.id, call.message.message_id,
                         "⚠️ Вы уверены, что хотите выключить компьютер?", reply_markup=keyboard)
    
    def _handle_shutdown_execute(self, call):
        try:
            safe_edit_or_send(self.bot, call.message.chat.id, call.message.message_id,
                           "✅ Компьютер будет выключен через 1 минуту!")
            self._log_command("System Shutdown", "Initiated")
            subprocess.run(['shutdown', '/s', '/t', str(CONFIG["SHUTDOWN_DELAY"])], check=False, timeout=5)
            self._show_notification("Запущено выключение компьютера")
        except (OSError, subprocess.SubprocessError) as e:
            logging.error(f"Ошибка выключения компьютера: {e}")
            try:
                self.bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")
            except telebot.apihelper.ApiTelegramException:
                pass
    
    def _handle_reboot_confirm(self, call):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Да, перезагрузить", callback_data="reboot_confirm"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data="main_menu")
        )
        safe_edit_or_send(self.bot, call.message.chat.id, call.message.message_id,
                         "⚠️ Вы уверены, что хотите перезагрузить компьютер?", reply_markup=keyboard)
    
    def _handle_reboot_execute(self, call):
        try:
            safe_edit_or_send(self.bot, call.message.chat.id, call.message.message_id,
                           "✅ Компьютер будет перезагружен через 1 минуту!")
            self._log_command("System Reboot", "Initiated")
            subprocess.run(['shutdown', '/r', '/t', str(CONFIG["SHUTDOWN_DELAY"])], check=False, timeout=5)
            self._show_notification("Запущена перезагрузка компьютера")
        except (OSError, subprocess.SubprocessError) as e:
            logging.error(f"Ошибка перезагрузки компьютера: {e}")
            safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)}")
    
    def _handle_lock_screen(self, call):
        try:
            ctypes.windll.user32.LockWorkStation()
            self.bot.send_message(call.message.chat.id, "🔒 Экран заблокирован")
            self._log_command("Lock Screen", "Screen locked")
            self._show_notification("Экран заблокирован")
        except (OSError, ctypes.WinError):
            pass
    
    def _handle_volume_menu(self, call):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔇 Mute", callback_data="volume_mute"))
        keyboard.add(InlineKeyboardButton("🔊 Volume Up", callback_data="volume_up"))
        keyboard.add(InlineKeyboardButton("🔈 Volume Down", callback_data="volume_down"))
        keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
        safe_edit_or_send(self.bot, call.message.chat.id, call.message.message_id,
                         "🔊 Управление громкостью - выберите действие:", reply_markup=keyboard)
    
    def _handle_volume_action(self, call, key, message, log_action, notification):
        try:
            pyautogui.press(key)
            safe_answer_callback(self.bot, call.id, message)
            self._log_command("Volume Control", log_action)
            self._show_notification(notification)
        except (pyautogui.FailSafeException, OSError) as e:
            safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)}")
    
    def _handle_volume_mute(self, call):
        self._handle_volume_action(call, 'volumemute', "🔇 Звук отключен", "Mute", "Звук отключен")
    
    def _handle_volume_up(self, call):
        self._handle_volume_action(call, 'volumeup', "🔊 Громкость увеличена", "Volume Up", "Громкость увеличена")
    
    def _handle_volume_down(self, call):
        self._handle_volume_action(call, 'volumedown', "🔈 Громкость уменьшена", "Volume Down", "Громкость уменьшена")
    
    def _handle_download_file(self, message, file_path):
        try:
            if not file_path:
                self.bot.reply_to(message, "❌ Не указан путь к файлу")
                return
            
            if not os.path.isfile(file_path):
                self.bot.reply_to(message, "❌ Файл не найден")
                return
            
            if requires_admin_path(file_path):
                self.bot.reply_to(message, "❌ Работа с этим путем требует прав администратора")
                return
            
            file_size = os.path.getsize(file_path)
            if file_size > CONFIG["MAX_FILE_SIZE"]:
                self.bot.reply_to(message, f"❌ Файл слишком большой ({format_size(file_size)}). Макс: {format_size(CONFIG['MAX_FILE_SIZE'])}")
                return
            
            encoded_file = encode_path(file_path)
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("✅ Подтвердить", callback_data=f"download_execute_{encoded_file}"))
            keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="main_menu"))
            self.bot.reply_to(message, f"⚠️ Подтверждение отправки файла\n\n📄 {os.path.basename(file_path)}\nРазмер: {format_size(file_size)}\n\nПодтвердите отправку:", reply_markup=keyboard)
        except (OSError, ValueError) as e:
            logging.error(f"Ошибка в _handle_download_file: {e}")
            try:
                self.bot.reply_to(message, f"❌ Ошибка: {str(e)[:50]}")
            except telebot.apihelper.ApiTelegramException:
                pass
    
    def _handle_dir_command(self, message, dir_path):
        try:
            if not dir_path:
                self.bot.reply_to(message, "❌ Не указан путь к директории")
                return
            
            if requires_admin_path(dir_path):
                self.bot.reply_to(message, "❌ Работа с этим путем требует прав администратора")
                return
            
            abs_path = os.path.abspath(dir_path)
            
            if not os.path.exists(abs_path):
                self.bot.reply_to(message, "❌ Указанный путь не существует")
                return
            
            if not os.path.isdir(abs_path):
                self.bot.reply_to(message, "❌ Указан путь к файлу, требуется путь к директории")
                return
            
            self.user_state[f"dir_path_{message.chat.id}"] = abs_path
            self._show_notification(f"Просмотр директории: {os.path.basename(abs_path) or abs_path}")
            self._show_dir_page(message.chat.id, abs_path, 0)
        except (OSError, ValueError, PermissionError) as e:
            logging.error(f"Ошибка в _handle_dir_command: {e}")
            try:
                self.bot.reply_to(message, f"❌ Ошибка: {str(e)[:50]}")
            except telebot.apihelper.ApiTelegramException:
                pass
    
    def _show_dir_page(self, chat_id, dir_path, page):
        try:
            items = []
            dirs = []
            files = []
            
            for item in os.listdir(dir_path):
                item_path = os.path.join(dir_path, item)
                try:
                    if os.path.isdir(item_path):
                        dirs.append(item)
                    else:
                        files.append(item)
                except (OSError, PermissionError):
                    continue
            
            dirs.sort(key=lambda x: x.lower())
            files.sort(key=lambda x: x.lower())
            items = dirs + files
            
            if not items:
                self.bot.send_message(chat_id, f"📁 Директория: {dir_path}\n\n❌ Директория пуста")
                return
            
            total_pages = (len(items) + CONFIG["DIR_ITEMS_PER_PAGE"] - 1) // CONFIG["DIR_ITEMS_PER_PAGE"]
            if page >= total_pages:
                page = max(0, total_pages - 1)
            
            start_idx = page * CONFIG["DIR_ITEMS_PER_PAGE"]
            end_idx = start_idx + CONFIG["DIR_ITEMS_PER_PAGE"]
            page_items = items[start_idx:end_idx]
            
            text = f"📁 Директория: {dir_path}\n\n"
            text += f"Всего: {len(dirs)} папок, {len(files)} файлов\n"
            text += f"Страница {page + 1}/{total_pages}\n\n"
            
            for item in page_items:
                if item in dirs:
                    text += f"📁 {item}\n"
                else:
                    text += f"📝 {item}\n"
            
            keyboard = InlineKeyboardMarkup(row_width=2)
            nav_buttons = []
            
            if page > 0:
                encoded_path = encode_path(dir_path)
                callback_data = f"dir_pg_{encoded_path}_{page - 1}"
                if len(callback_data) <= CONFIG["CALLBACK_DATA_MAX_LENGTH"]:
                    nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=callback_data))
            
            if end_idx < len(items):
                encoded_path = encode_path(dir_path)
                callback_data = f"dir_pg_{encoded_path}_{page + 1}"
                if len(callback_data) <= CONFIG["CALLBACK_DATA_MAX_LENGTH"]:
                    nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=callback_data))
            
            if nav_buttons:
                keyboard.add(*nav_buttons)
            
            keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
            
            self.bot.send_message(chat_id, text, reply_markup=keyboard)
        except (OSError, PermissionError) as e:
            logging.error(f"Ошибка в _show_dir_page: {e}")
            try:
                self.bot.send_message(chat_id, f"❌ Ошибка доступа к директории: {str(e)[:50]}")
            except telebot.apihelper.ApiTelegramException:
                pass
    
    def _handle_dir_page(self, call, action):
        try:
            rest = action.replace("dir_pg_", "", 1)
            if "_" not in rest:
                return
            
            parts = rest.rsplit("_", 1)
            if len(parts) != 2:
                return
            
            dir_path = decode_path(parts[0])
            try:
                page = int(parts[1])
            except ValueError:
                return
            
            if not dir_path or not os.path.isdir(dir_path):
                safe_answer_callback(self.bot, call.id, "❌ Директория не найдена")
                return
            
            try:
                self.bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            
            self._show_dir_page(call.message.chat.id, dir_path, page)
        except Exception as e:
            logging.error(f"Ошибка в _handle_dir_page: {e}")
            safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)[:50]}")
    
    def _handle_download_confirm(self, call, action):
        pass
    
    def _handle_download_execute(self, call, action):
        try:
            file_path = decode_path(action.replace("download_execute_", "", 1))
            if not file_path or not os.path.isfile(file_path):
                safe_answer_callback(self.bot, call.id, "❌ Файл не найден")
                return
            
            if requires_admin_path(file_path):
                safe_answer_callback(self.bot, call.id, "❌ Работа с этим путем требует прав администратора")
                return
            
            file_size = os.path.getsize(file_path)
            if file_size > CONFIG["MAX_FILE_SIZE"]:
                safe_answer_callback(self.bot, call.id, f"❌ Файл слишком большой ({format_size(file_size)}). Макс: {format_size(CONFIG['MAX_FILE_SIZE'])}")
                return
            
            safe_answer_callback(self.bot, call.id, "⏳ Отправка файла...")
            
            with open(file_path, 'rb') as f:
                self.bot.send_document(call.message.chat.id, f, caption=f"📄 {os.path.basename(file_path)}")
            
            safe_answer_callback(self.bot, call.id, "✅ Файл отправлен")
            self._log_command("Download File", file_path)
            self._show_notification(f"Отправлен файл: {os.path.basename(file_path)}")
        except (OSError, PermissionError):
            safe_answer_callback(self.bot, call.id, "❌ Ошибка доступа к файлу")
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Ошибка отправки файла: {e}")
            safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)[:50]}")
    
    def _parse_upload_action(self, action):
        rest = action.replace("upload_confirm_", "", 1)
        if "|||" not in rest:
            return None, None, None
        
        parts = rest.split("|||", 1)
        if len(parts) != 2:
            return None, None, None
        
        upload_path = decode_path(parts[0])
        file_info = decode_path(parts[1])
        
        if not file_info or "|" not in file_info:
            return None, None, None
        
        file_id, file_name = file_info.split("|", 1)
        return upload_path, file_id, file_name
    
    def _download_and_save_file(self, file_id, upload_path, file_name):
        file_info_obj = self.bot.get_file(file_id)
        
        if file_info_obj.file_size > CONFIG["MAX_FILE_SIZE"]:
            return False, f"❌ Файл слишком большой ({format_size(file_info_obj.file_size)}). Макс: {format_size(CONFIG['MAX_FILE_SIZE'])}"
        
        downloaded_file = self.bot.download_file(file_info_obj.file_path)
        full_path = os.path.join(upload_path, file_name)
        
        try:
            os.makedirs(upload_path, exist_ok=True)
        except (OSError, PermissionError) as e:
            return False, f"❌ Ошибка доступа к пути: {str(e)[:50]}"
        
        try:
            with open(full_path, 'wb') as f:
                f.write(downloaded_file)
        except (OSError, PermissionError) as e:
            return False, f"❌ Ошибка записи файла: {str(e)[:50]}"
        
        return True, full_path
    
    def _handle_upload_confirm(self, call, action):
        try:
            upload_path, file_id, file_name = self._parse_upload_action(action)
            
            if not upload_path or not file_id:
                safe_answer_callback(self.bot, call.id, "❌ Ошибка: неверный формат")
                return
            
            if requires_admin_path(upload_path):
                safe_answer_callback(self.bot, call.id, "❌ Работа с этим путем требует прав администратора")
                return
            
            try:
                safe_answer_callback(self.bot, call.id, "⏳ Загрузка файла...")
                
                success, result = self._download_and_save_file(file_id, upload_path, file_name)
                
                if success:
                    safe_answer_callback(self.bot, call.id, "✅ Файл загружен")
                    self.bot.send_message(call.message.chat.id, f"✅ Файл успешно загружен:\n📄 {result}")
                    self._log_command("Upload File", result)
                    self._show_notification(f"Загружен файл: {file_name}")
                else:
                    safe_answer_callback(self.bot, call.id, result)
            except (telebot.apihelper.ApiTelegramException, OSError, IOError) as e:
                logging.error(f"Ошибка загрузки файла: {e}")
                safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)[:50]}")
        except (ValueError, OSError) as e:
            logging.error(f"Ошибка в _handle_upload_confirm: {e}")
            safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)[:50]}")
    
    def _handle_process_menu(self, call):
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("📱 Просмотр активных процессов", callback_data="proc_list_apps"))
        keyboard.add(InlineKeyboardButton("🔄 Просмотр фоновых процессов", callback_data="proc_list_bg"))
        keyboard.add(InlineKeyboardButton("⚙️ Просмотр системных процессов", callback_data="proc_list_sys"))
        keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
        safe_edit_or_send(self.bot, call.message.chat.id, call.message.message_id,
                         "⚙️ Управление процессами\n\nВыберите категорию:", reply_markup=keyboard)
    
    def _get_process_category(self, proc):
        try:
            proc_name_orig = proc.name()
            proc_name = proc_name_orig.lower()
            
            system_names = {
                'svchost.exe', 'csrss.exe', 'winlogon.exe', 'services.exe',
                'lsass.exe', 'smss.exe', 'System', 'Registry',
                'wininit.exe', 'lsm.exe'
            }
            
            if proc_name_orig in system_names or proc_name == 'system':
                return 'sys'
            
            if HAS_WIN32:
                try:
                    if not self._is_cache_valid(self.visible_windows_cache_time, CONFIG["WINDOW_CACHE_TTL"]) or self.visible_windows_cache is None:
                        current_time = time.time()
                        windows = set()
                        def enum_window_callback(hwnd, windows):
                            if win32gui.IsWindowVisible(hwnd):
                                window_text = win32gui.GetWindowText(hwnd)
                                if window_text:
                                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                    windows.add(pid)
                            return True
                        win32gui.EnumWindows(enum_window_callback, windows)
                        self.visible_windows_cache = windows
                        self.visible_windows_cache_time = current_time
                    if proc.pid in self.visible_windows_cache:
                        return 'apps'
                except Exception:
                    pass
            
            return 'bg'
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return 'bg'
        except Exception:
            return 'bg'
    
    def _handle_process_list(self, call, category, page):
        try:
            cache_key = "all"
            if self._is_cache_valid(self.process_cache_time, CONFIG["PROCESS_CACHE_TTL"]) and cache_key in self.process_cache:
                apps, bg, sys_procs = self.process_cache[cache_key]
            else:
                apps = []
                bg = []
                sys_procs = []
                for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                    try:
                        pinfo = proc.info
                        mem_mb = pinfo['memory_info'].rss / (1024 * 1024)
                        proc_category = self._get_process_category(proc)
                        if proc_category == 'apps':
                            apps.append((pinfo['pid'], pinfo['name'], mem_mb))
                        elif proc_category == 'sys':
                            sys_procs.append((pinfo['pid'], pinfo['name'], mem_mb))
                        else:
                            bg.append((pinfo['pid'], pinfo['name'], mem_mb))
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                self.process_cache[cache_key] = (apps, bg, sys_procs)
                self.process_cache_time = time.time()
            
            category_map = {
                'apps': (apps, "Активные процессы"),
                'sys': (sys_procs, "Системные процессы"),
            }
            processes, category_name = category_map.get(category, (bg, "Фоновые процессы"))
            processes = sorted(processes, key=lambda x: x[2], reverse=True)
            
            total_pages = (len(processes) + CONFIG["PROCESSES_PER_PAGE"] - 1) // CONFIG["PROCESSES_PER_PAGE"]
            if page >= total_pages:
                page = max(0, total_pages - 1)
            
            self.user_state["last_process_category"] = category
            self.user_state["last_process_page"] = page
            
            keyboard = InlineKeyboardMarkup(row_width=1)
            start_idx = page * CONFIG["PROCESSES_PER_PAGE"]
            end_idx = start_idx + CONFIG["PROCESSES_PER_PAGE"]
            
            for pid, name, mem_mb in processes[start_idx:end_idx]:
                callback_data = f"proc_kill_{pid}"
                if len(callback_data) <= CONFIG["CALLBACK_DATA_MAX_LENGTH"]:
                    keyboard.add(InlineKeyboardButton(
                        f"❌ {name[:30]} (PID: {pid}, {mem_mb:.1f}MB)", callback_data=callback_data))
            
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"proc_pg_{category}_{page - 1}"))
            if end_idx < len(processes):
                nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"proc_pg_{category}_{page + 1}"))
            if nav_buttons:
                keyboard.add(*nav_buttons)
            keyboard.add(InlineKeyboardButton("🔙 Назад к категориям", callback_data="proc_menu"))
            
            safe_edit_or_send(self.bot, call.message.chat.id, call.message.message_id,
                            f"❌ {category_name}\n\nВыберите процесс для завершения:", reply_markup=keyboard)
        except (psutil.Error, OSError, ValueError) as e:
            logging.error(f"Ошибка в _handle_process_list: {e}")
            safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)[:50]}")
    
    def _handle_process_action(self, call, action):
        try:
            if action.startswith("proc_kill_"):
                try:
                    pid = int(action.replace("proc_kill_", "", 1))
                except ValueError:
                    safe_answer_callback(self.bot, call.id, "❌ Неверный ID процесса")
                    return
                
                if pid in [0, 4]:
                    safe_answer_callback(self.bot, call.id, "❌ Нельзя завершить системный процесс")
                    return
                
                try:
                    proc = psutil.Process(pid)
                    proc_name = proc.name()
                    proc_name_lower = proc_name.lower()
                    critical_processes = {'csrss.exe', 'winlogon.exe', 'services.exe', 'lsass.exe', 'smss.exe'}
                    if proc_name_lower in critical_processes:
                        safe_answer_callback(self.bot, call.id, "❌ Нельзя завершить критический системный процесс")
                        return
                    proc.terminate()
                    try:
                        proc.wait(timeout=CONFIG["PROCESS_WAIT_TIMEOUT"])
                    except psutil.TimeoutExpired:
                        proc.kill()
                    safe_answer_callback(self.bot, call.id, f"✅ Процесс {proc_name} завершен")
                    self._log_command("Kill Process", f"PID: {pid}, Name: {proc_name}")
                    self._show_notification(f"Завершен процесс: {proc_name}")
                    self._clear_process_cache()
                    time.sleep(CONFIG["PROCESS_REFRESH_WAIT"])
                    self._handle_process_list(call, self.user_state.get("last_process_category", "apps"),
                                             self.user_state.get("last_process_page", 0))
                except psutil.NoSuchProcess:
                    safe_answer_callback(self.bot, call.id, "❌ Процесс не найден")
                    self._clear_process_cache()
                except psutil.AccessDenied:
                    safe_answer_callback(self.bot, call.id, "❌ Нет прав для завершения процесса")
                except psutil.Error as e:
                    logging.error(f"Ошибка завершения процесса {pid}: {e}")
                    safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)[:50]}")
            elif action.startswith("proc_pg_"):
                rest = action.replace("proc_pg_", "", 1)
                if "_" in rest:
                    parts = rest.split("_", 1)
                    if len(parts) == 2:
                        try:
                            category = parts[0]
                            page = int(parts[1])
                            if category in ['apps', 'bg', 'sys']:
                                self._handle_process_list(call, category, page)
                                return
                        except (ValueError, IndexError):
                            pass
                self._handle_process_menu(call)
        except (ValueError, IndexError, psutil.Error) as e:
            logging.error(f"Ошибка в _handle_process_action: {e}")
            safe_answer_callback(self.bot, call.id, f"❌ Ошибка: {str(e)[:50]}")

    def end_session(self):
        self.stop_bot()
        safe_remove_file(os.path.join(self.data_dir, '.lock'))
        if self.icon:
            try:
                self.icon.stop()
            except Exception as e:
                logging.error(f"Ошибка остановки иконки трея: {e}")
        sys.exit(0)
    
    def _remove_autostart(self):
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            ) as key:
                try:
                    winreg.DeleteValue(key, "ControlPCbotV2")
                except FileNotFoundError:
                    pass
        except Exception as e:
            logging.error(f"Ошибка удаления из автозапуска: {e}")
    
    def _remove_shortcuts(self):
        shortcuts = [
            os.path.join(
                os.environ.get('APPDATA', ''),
                'Microsoft', 'Windows', 'Start Menu', 'Programs', 'ControlPCbotV2.lnk'
            ),
            os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop', 'ControlPCbotV2.lnk'),
        ]
        
        for shortcut in shortcuts:
            safe_remove_file(shortcut)
    
    def uninstall(self, icon=None, item=None):
        """Удаление программы"""
        try:
            root = tk.Tk()
            root.withdraw()
            if not messagebox.askyesno("Подтверждение", "Вы уверены, что хотите удалить программу?"):
                root.destroy()
                return
            root.destroy()
        except Exception:
            return
        
        try:
            self.stop_bot()
            self._remove_autostart()
            self._remove_shortcuts()
            
            try:
                shutil.rmtree(self.data_dir)
            except Exception as e:
                logging.error(f"Ошибка удаления директории данных: {e}")
            
            subprocess.Popen(f'ping 127.0.0.1 -n 2 >nul && rmdir /s /q "{self.app_dir}"', shell=True)
            
            self._show_notification("Программа будет удалена после перезапуска", force=True)
            if self.icon:
                try:
                    self.icon.stop()
                except Exception:
                    pass
            sys.exit(0)
        except Exception as e:
            logging.error(f"Ошибка при удалении программы: {e}")
            try:
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("Ошибка", f"Ошибка при удалении: {str(e)}")
                root.destroy()
            except Exception:
                pass
    
    def _toggle_notifications_on(self, icon=None, item=None):
        self.notifications_enabled = True
        self._show_notification("Уведомления включены", force=True)
        if self.icon:
            self.icon.menu = self._create_tray_menu()
    
    def _toggle_notifications_off(self, icon=None, item=None):
        self.notifications_enabled = False
        self._show_notification("Уведомления отключены", force=True)
        if self.icon:
            self.icon.menu = self._create_tray_menu()
    
    def _create_tray_menu(self):
        if self.notifications_enabled:
            return pystray.Menu(
                pystray.MenuItem("Отключить уведомления", self._toggle_notifications_off),
                pystray.MenuItem("Завершить сеанс", lambda icon, item: self.end_session()),
                pystray.MenuItem("Удалить программу", self.uninstall),
            )
        else:
            return pystray.Menu(
                pystray.MenuItem("Включить уведомления", self._toggle_notifications_on),
                pystray.MenuItem("Завершить сеанс", lambda icon, item: self.end_session()),
                pystray.MenuItem("Удалить программу", self.uninstall),
            )
    
    def run_tray(self):
        """Запуск приложения в системном трее"""
        menu = self._create_tray_menu()
        self.icon = pystray.Icon("ControlPCbotV2", self._create_icon(), "ControlPCbotV2", menu)
        self.start_bot()
        self._show_notification("ControlPCbotV2 запущен", force=True)
        self.icon.run()

def check_running_instance():
    if not is_frozen():
        return False
    try:
        data_dir = get_data_dir()
        lock_file = os.path.join(data_dir, '.lock')
        if os.path.exists(lock_file):
            try:
                with open(lock_file, 'r') as f:
                    old_pid = int(f.read().strip())
                if old_pid != os.getpid():
                    try:
                        os.kill(old_pid, 0)
                        return True
                    except (OSError, ProcessLookupError):
                        safe_remove_file(lock_file)
            except Exception:
                safe_remove_file(lock_file)
        try:
            with open(lock_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception:
            pass
        return False
    except Exception:
        return False

def main():
    try:
        if not is_frozen():
            print("Программа должна быть скомпилирована в exe файл!")
            sys.exit(1)
        app_dir = get_app_dir()
        config_path = os.path.join(app_dir, 'config.json')
        if not os.path.exists(config_path):
            run_installer()
            return
        time.sleep(0.5)
        if check_running_instance():
            try:
                ToastNotifier().show_toast("ControlPCbotV2",
                                         "Программа ControlPCbot уже запущена, используйте трей для взаимодействия",
                                         duration=5, threaded=False)
                time.sleep(5)
            except Exception:
                pass
            return
        
        app = BotApp()
        def cleanup():
            try:
                lock_file = os.path.join(app.data_dir, '.lock')
                if os.path.exists(lock_file):
                    with open(lock_file, 'r') as f:
                        if f.read().strip() == str(os.getpid()):
                            safe_remove_file(lock_file)
            except Exception:
                pass
        atexit.register(cleanup)
        app.run_tray()
    except KeyboardInterrupt:
        if 'app' in locals():
            try:
                app.stop_bot()
            except Exception:
                pass
    except Exception as e:
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Ошибка", f"Критическая ошибка:\n{error_msg}")
            root.destroy()
        except Exception:
            try:
                with open(os.path.join(get_data_dir(), 'error.log'), 'w', encoding='utf-8') as f:
                    f.write(traceback_str)
            except Exception:
                print(f"Критическая ошибка: {error_msg}\n{traceback_str}")

if __name__ == "__main__":
    main()
