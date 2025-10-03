import os
import logging
import subprocess
import time
import telebot
import psutil
import pyautogui
import tempfile
import winreg
import ctypes
import zipfile
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from win10toast import ToastNotifier
import config

bot = telebot.TeleBot(config.TOKEN)
logger = telebot.logger
logger.setLevel(logging.INFO)
toaster = ToastNotifier()

user_state = {
    "process_page": 0,
    "selected_process": None,
    "waiting_for_path": None,
    "upload_path": None,
    "show_system_processes": False,
    "current_directory": os.path.expanduser("~"),
    "waiting_for_emulation_text": False,
    "waiting_for_process_kill": False,
    "process_list": []
}


def log_command(command, output):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open("command_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Command: {command}\n")
        f.write(f"Output: {output}\n\n")


def show_notification(command):
    toaster.show_toast("ControlPCbotV2", f"Executed command:\n{command}", duration=5, threaded=True)


def get_drives():
    drives = []
    for drive in psutil.disk_partitions():
        if 'cdrom' not in drive.opts:
            drives.append(drive.device)
    return drives


def get_special_folders():
    folders = {
        "Desktop": os.path.join(os.path.expanduser("~"), "Desktop"),
        "Downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
        "Documents": os.path.join(os.path.expanduser("~"), "Documents"),
        "Pictures": os.path.join(os.path.expanduser("~"), "Pictures"),
        "Music": os.path.join(os.path.expanduser("~"), "Music"),
        "Videos": os.path.join(os.path.expanduser("~"), "Videos")
    }
    return folders


def create_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    autostart_status = "✅ Автозапуск" if check_autostart() else "❌ Автозапуск"
    buttons = [
        InlineKeyboardButton("🖥️ Выключить ПК", callback_data="shutdown"),
        InlineKeyboardButton("🔄 Перезагрузить ПК", callback_data="reboot"),
        InlineKeyboardButton("📸 Скриншот", callback_data="screenshot"),
        InlineKeyboardButton("📁 Управление файлами", callback_data="file_manager"),
        InlineKeyboardButton("❌ Завершить процесс", callback_data="kill_menu"),
        InlineKeyboardButton("🔊 Управление громкостью", callback_data="volume_control"),
        InlineKeyboardButton("⌨️ Эмуляция клавиш", callback_data="key_emulation"),
        InlineKeyboardButton("🖱 Эмуляция мыши", callback_data="mouse_emulation"),
        InlineKeyboardButton("🔒 Блокировка экрана", callback_data="lock_screen"),
        InlineKeyboardButton(autostart_status, callback_data="autostart")
    ]
    keyboard.add(*buttons)
    return keyboard


def create_file_manager_keyboard(current_path=None):
    keyboard = InlineKeyboardMarkup()

    if current_path is None:
        current_path = user_state["current_directory"]

    folders = get_special_folders()
    for name, path in folders.items():
        keyboard.add(InlineKeyboardButton(f"📁 {name}", callback_data=f"folder_{path}"))

    drives = get_drives()
    for drive in drives:
        keyboard.add(InlineKeyboardButton(f"💾 Диск {drive}", callback_data=f"folder_{drive}"))

    keyboard.add(InlineKeyboardButton("📤 Загрузить файл сюда", callback_data="upload_here"))
    keyboard.add(InlineKeyboardButton("📥 Извлечь файл", callback_data="get_file_here"))
    keyboard.add(InlineKeyboardButton("⌨️ Ввести путь вручную", callback_data="enter_path"))
    keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))

    return keyboard


def create_directory_keyboard(path):
    keyboard = InlineKeyboardMarkup()

    try:
        items = os.listdir(path)
        for item in items[:10]:
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                keyboard.add(InlineKeyboardButton(f"📁 {item}", callback_data=f"folder_{full_path}"))
            else:
                size = os.path.getsize(full_path) // 1024
                keyboard.add(InlineKeyboardButton(f"📄 {item} ({size} KB)", callback_data=f"file_{full_path}"))

        parent_dir = os.path.dirname(path)
        if parent_dir and os.path.exists(parent_dir):
            keyboard.add(InlineKeyboardButton("↩️ Назад", callback_data=f"folder_{parent_dir}"))

        keyboard.add(InlineKeyboardButton("📤 Загрузить файл сюда", callback_data="upload_here"))
        keyboard.add(InlineKeyboardButton("📦 Скачать папку архивом", callback_data="archive_folder"))
        keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))

    except Exception as e:
        keyboard.add(InlineKeyboardButton("❌ Ошибка доступа", callback_data="noop"))
        keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))

    return keyboard


def create_volume_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔇 Mute", callback_data="volume_mute"))
    keyboard.add(InlineKeyboardButton("🔊 Volume Up", callback_data="volume_up"))
    keyboard.add(InlineKeyboardButton("🔈 Volume Down", callback_data="volume_down"))
    keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
    return keyboard


def create_key_emulation_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Ввести текст", callback_data="emulate_text"))
    keyboard.add(InlineKeyboardButton("Специальные клавиши", callback_data="special_keys"))
    keyboard.add(InlineKeyboardButton("Сочетания клавиш", callback_data="key_combinations"))
    keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
    return keyboard


def create_special_keys_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=3)
    keys = [
        "Win", "Ctrl", "Alt", "Tab", "Enter", "Space",
        "Up", "Down", "Left", "Right", "Esc", "Delete"
    ]
    buttons = [InlineKeyboardButton(key, callback_data=f"key_{key}") for key in keys]
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="key_emulation"))
    return keyboard


def create_key_combinations_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    combinations = {
        "Win+L": "lock",
        "Alt+Tab": "alt_tab",
        "Ctrl+C": "ctrl_c",
        "Ctrl+V": "ctrl_v",
        "Ctrl+Z": "ctrl_z",
        "Ctrl+A": "ctrl_a",
        "Ctrl+S": "ctrl_s",
        "Win+E": "win_e",
        "Win+R": "win_r",
        "Win+D": "win_d",
        "Ctrl+Shift+Esc": "ctrl_shift_esc",
        "Alt+F4": "alt_f4"
    }
    buttons = []
    for name, data in combinations.items():
        buttons.append(InlineKeyboardButton(name, callback_data=f"comb_{data}"))
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="key_emulation"))
    return keyboard


def create_mouse_emulation_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=3)

    keyboard.add(
        InlineKeyboardButton(" ", callback_data="noop"),
        InlineKeyboardButton("⬆️", callback_data="mouse_up"),
        InlineKeyboardButton(" ", callback_data="noop")
    )

    keyboard.add(
        InlineKeyboardButton("⬅️", callback_data="mouse_left"),
        InlineKeyboardButton("🖱", callback_data="noop"),
        InlineKeyboardButton("➡️", callback_data="mouse_right")
    )

    keyboard.add(
        InlineKeyboardButton(" ", callback_data="noop"),
        InlineKeyboardButton("⬇️", callback_data="mouse_down"),
        InlineKeyboardButton(" ", callback_data="noop")
    )

    keyboard.add(
        InlineKeyboardButton("ЛКМ", callback_data="mouse_left_click"),
        InlineKeyboardButton("ПКМ", callback_data="mouse_right_click"),
        InlineKeyboardButton("СКМ", callback_data="mouse_middle_click")
    )

    keyboard.add(
        InlineKeyboardButton("Скролл ▲", callback_data="mouse_scroll_up"),
        InlineKeyboardButton("Скролл ▼", callback_data="mouse_scroll_down")
    )

    keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
    return keyboard


def create_process_list_message():
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            if not user_state["show_system_processes"] and proc.pid < 1000:
                continue
            processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not processes:
        return "❌ Процессы не найдены", []

    processes.sort(key=lambda x: x.info['memory_info'].rss if x.info['memory_info'] else 0, reverse=True)

    result = "📋 Список процессов:\n\n"
    process_list = []

    for i, proc in enumerate(processes[:20], 1):
        try:
            memory_mb = proc.info['memory_info'].rss // 1024 // 1024 if proc.info['memory_info'] else 0
            result += f"{i}. {proc.info['name']} (PID: {proc.pid}) - {memory_mb} MB\n"
            process_list.append(proc.pid)
        except:
            continue

    result += f"\n📊 Всего процессов: {len(process_list)}"
    result += "\n\n💡 Введите номер процесса для завершения:"

    return result, process_list


def create_zip_archive(folder_path, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, folder_path)
                zipf.write(file_path, arcname)


def enable_autostart():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        bat_path = os.path.join(script_dir, "start.bat")

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ControlPCbotV2", 0, winreg.REG_SZ, f'"{bat_path}"')

        return True
    except Exception as e:
        return False


def disable_autostart():
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "ControlPCbotV2")

        return True
    except Exception as e:
        return False


def check_autostart():
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            try:
                winreg.QueryValueEx(key, "ControlPCbotV2")
                return True
            except FileNotFoundError:
                return False
    except:
        return False


def toggle_autostart():
    if check_autostart():
        return disable_autostart()
    else:
        return enable_autostart()


def check_system_uptime():
    uptime_seconds = time.time() - psutil.boot_time()
    return uptime_seconds < 300


def take_screenshot():
    try:
        screenshot = pyautogui.screenshot()
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        screenshot.save(temp_file.name, 'PNG')
        return temp_file.name
    except Exception as e:
        return None


def list_directory(path):
    try:
        if not os.path.exists(path):
            return "❌ Путь не существует"
        if not os.path.isdir(path):
            return "❌ Указанный путь не является папкой"
        result = "📂 Содержимое папки:\n\n"
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                result += f"📁 {item}/\n"
            else:
                size = os.path.getsize(full_path)
                result += f"📄 {item} ({size // 1024} KB)\n"
        return result
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"


@bot.message_handler(func=lambda message: message.chat.id != config.CHAT_ID)
def handle_unauthorized(message):
    bot.reply_to(message, "⛔ Доступ запрещен")


@bot.message_handler(commands=['start', 'help', 'menu'])
def send_welcome(message):
    if message.chat.id != config.CHAT_ID:
        return

    if check_system_uptime():
        bot.send_message(message.chat.id, "🖥️ Компьютер был запущен недавно")

    help_text = (
        "🤖 ControlPCbotV2 - Бот управления компьютером\n\n"
        "Доступные команды:\n"
        "/menu - Главное меню\n"
        "/cmd [команда] - Выполнить команду в CMD\n\n"
        "⚠️ Для выполнения команд требуются права администратора\n\n"
        "Автор: https://github.com/MrachniyTipchek"
    )
    keyboard = create_main_menu()
    bot.send_message(message.chat.id, help_text, reply_markup=keyboard)


@bot.message_handler(commands=['control'])
def show_control_menu(message):
    if message.chat.id != config.CHAT_ID:
        return
    keyboard = create_main_menu()
    bot.send_message(message.chat.id, "📱 Главное меню управления ControlPCbotV2:", reply_markup=keyboard)


@bot.message_handler(commands=['log'])
def send_log(message):
    if message.chat.id != config.CHAT_ID:
        return
    try:
        with open("command_log.txt", "rb") as f:
            bot.send_document(message.chat.id, f, caption="📝 Лог команд")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка: {str(e)}")


@bot.message_handler(commands=['cmd'])
def handle_cmd_command(message):
    if message.chat.id != config.CHAT_ID:
        return
    command = message.text.replace('/cmd', '', 1).strip()
    if not command:
        bot.reply_to(message, "ℹ️ Использование: /cmd [команда]")
        return
    show_notification(f"CMD: {command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            encoding='cp866',
            cwd=os.path.expanduser("~")
        )
        output = result.stdout or result.stderr or "Команда выполнена"
        log_command(command, output)

        if len(output) > 4000:
            with open("output.txt", "w", encoding="utf-8") as f:
                f.write(output)
            with open("output.txt", "rb") as f:
                bot.send_document(message.chat.id, f)
            os.remove("output.txt")
        else:
            bot.reply_to(message, f"```\n{output}\n```", parse_mode="Markdown")
    except Exception as e:
        log_command(command, f"Error: {str(e)}")
        bot.reply_to(message, f"⚠️ Ошибка: {str(e)}")


@bot.message_handler(commands=['cmdlist'])
def cmd_list(message):
    if message.chat.id != config.CHAT_ID:
        return

    cmd_help = (
        "📋 Основные CMD команды:\n\n"
        "• `cd` - Сменить директорию\n"
        "• `dir` - Показать содержимое папки\n"
        "• `ipconfig` - Информация о сетевых подключениях\n"
        "• `ping` - Проверить доступность хоста\n"
        "• `shutdown /s /t 0` - Немедленное выключение\n"
        "• `shutdown /r /t 0` - Немедленная перезагрузка\n"
        "• `tasklist` - Список процессов\n"
        "• `taskkill /F /PID <pid>` - Завершить процесс\n"
        "• `systeminfo` - Информация о системе\n"
        "• `curl` - Загрузка файлов из интернета\n\n"
        "Для выполнения команд используйте /cmd [команда]"
    )
    bot.send_message(message.chat.id, cmd_help, parse_mode="Markdown")


@bot.message_handler(commands=['autorun'])
def handle_autorun(message):
    if message.chat.id != config.CHAT_ID:
        return

    try:
        if toggle_autostart():
            status = "добавлен в автозагрузку" if check_autostart() else "удален из автозагрузки"
            bot.reply_to(message, f"✅ Бот {status}")
            log_command("Autorun", f"Toggled, now: {status}")
        else:
            bot.reply_to(message, "❌ Ошибка управления автозагрузкой")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка управления автозагрузкой: {str(e)}")


@bot.message_handler(
    func=lambda message: user_state.get("waiting_for_emulation_text") and message.chat.id == config.CHAT_ID)
def handle_emulation_text(message):
    user_state["waiting_for_emulation_text"] = False
    text = message.text
    try:
        pyautogui.write(text)
        bot.reply_to(message, f"✅ Текст введен: '{text}'")
        log_command("Text Emulation", f"Text: {text}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка ввода текста: {str(e)}")

    keyboard = create_main_menu()
    bot.send_message(message.chat.id, "📱 Возврат в главное меню:", reply_markup=keyboard)


@bot.message_handler(
    func=lambda message: user_state.get("waiting_for_process_kill") and message.chat.id == config.CHAT_ID)
def handle_process_kill_input(message):
    user_state["waiting_for_process_kill"] = False
    process_number = message.text.strip()

    try:
        index = int(process_number) - 1
        if 0 <= index < len(user_state["process_list"]):
            pid = user_state["process_list"][index]
            try:
                process = psutil.Process(pid)
                process_name = process.name()
                process.terminate()
                bot.reply_to(message, f"✅ Процесс {process_name} (PID: {pid}) завершен")
                log_command("Kill Process", f"Terminated {process_name} (PID: {pid})")
            except Exception as e:
                bot.reply_to(message, f"❌ Ошибка завершения процесса: {str(e)}")
        else:
            bot.reply_to(message, "❌ Неверный номер процесса")
    except ValueError:
        bot.reply_to(message, "❌ Введите корректный номер")

    keyboard = create_main_menu()
    bot.send_message(message.chat.id, "📱 Возврат в главное меню:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.message.chat.id != config.CHAT_ID)
def handle_unauthorized_callback(call):
    bot.answer_callback_query(call.id, "⛔ Доступ запрещен")


@bot.callback_query_handler(func=lambda call: call.message.chat.id == config.CHAT_ID)
def handle_control_buttons(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    action = call.data

    if action == "main_menu":
        keyboard = create_main_menu()
        try:
            bot.edit_message_text("📱 Главное меню управления ControlPCbotV2:", call.message.chat.id,
                                  call.message.message_id, reply_markup=keyboard)
        except:
            pass

    elif action == "autostart":
        try:
            if toggle_autostart():
                status = "добавлен в автозагрузку" if check_autostart() else "удален из автозагрузки"
                bot.answer_callback_query(call.id, f"✅ Бот {status}")
                log_command("Autorun", f"Toggled, now: {status}")
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка управления автозагрузкой")

            keyboard = create_main_menu()
            bot.edit_message_text("📱 Главное меню управления ControlPCbotV2:", call.message.chat.id,
                                  call.message.message_id, reply_markup=keyboard)
        except:
            pass

    elif action == "shutdown":
        try:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton("✅ Да, завершить", callback_data="shutdown_confirm"),
                InlineKeyboardButton("❌ Нет, отмена", callback_data="shutdown_cancel")
            )
            bot.edit_message_text("⚠️ Вы уверены, что хотите выключить компьютер?", call.message.chat.id,
                                  call.message.message_id, reply_markup=keyboard)
        except:
            pass

    elif action == "shutdown_confirm":
        try:
            bot.edit_message_text("✅ Компьютер будет выключен через 1 минуту!", call.message.chat.id,
                                  call.message.message_id)
            log_command("System Shutdown", "Initiated by bot")
            os.system("shutdown /s /t 60")
        except:
            pass

    elif action == "shutdown_cancel":
        keyboard = create_main_menu()
        try:
            bot.edit_message_text("❌ Выключение отменено", call.message.chat.id,
                                  call.message.message_id, reply_markup=keyboard)
        except:
            pass

    elif action == "reboot":
        try:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton("✅ Да, перезагрузить", callback_data="reboot_confirm"),
                InlineKeyboardButton("❌ Нет, отмена", callback_data="reboot_cancel")
            )
            bot.edit_message_text("⚠️ Вы уверены, что хотите перезагрузить компьютер?", call.message.chat.id,
                                  call.message.message_id, reply_markup=keyboard)
        except:
            pass

    elif action == "reboot_confirm":
        try:
            bot.edit_message_text("✅ Компьютер будет перезагружен через 1 минуту!", call.message.chat.id,
                                  call.message.message_id)
            log_command("System Reboot", "Initiated by bot")
            os.system("shutdown /r /t 60")
        except:
            pass

    elif action == "reboot_cancel":
        keyboard = create_main_menu()
        try:
            bot.edit_message_text("❌ Перезагрузка отменена", call.message.chat.id,
                                  call.message.message_id, reply_markup=keyboard)
        except:
            pass

    elif action == "screenshot":
        try:
            screenshot_path = take_screenshot()
            if screenshot_path:
                with open(screenshot_path, 'rb') as photo:
                    bot.send_photo(call.message.chat.id, photo, caption="📸 Скриншот выполнен успешно")
                os.unlink(screenshot_path)
                log_command("Screenshot", "Taken")
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка создания скриншота")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "file_manager":
        try:
            bot.edit_message_text("📁 Управление файлами - выберите папку:", call.message.chat.id,
                                  call.message.message_id, reply_markup=create_file_manager_keyboard())
        except:
            pass

    elif action.startswith("folder_"):
        path = action[7:]
        user_state["current_directory"] = path
        content = list_directory(path)
        try:
            bot.edit_message_text(f"📂 Содержимое папки: {path}\n\n{content}", call.message.chat.id,
                                  call.message.message_id, reply_markup=create_directory_keyboard(path))
        except:
            pass

    elif action.startswith("file_"):
        file_path = action[5:]
        try:
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    bot.send_document(call.message.chat.id, f, caption=f"📄 {os.path.basename(file_path)}")
            else:
                bot.answer_callback_query(call.id, "❌ Файл не найден")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка отправки файла: {str(e)}")

    elif action == "upload_here":
        current_dir = user_state["current_directory"]
        try:
            bot.edit_message_text(f"📤 Отправьте файл для загрузки в папку:\n{current_dir}", call.message.chat.id,
                                  call.message.message_id)
            user_state["waiting_for_path"] = "upload_file"
            user_state["upload_path"] = current_dir
        except:
            pass

    elif action == "archive_folder":
        current_dir = user_state["current_directory"]
        try:
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            temp_zip.close()
            create_zip_archive(current_dir, temp_zip.name)
            with open(temp_zip.name, 'rb') as zip_file:
                bot.send_document(call.message.chat.id, zip_file,
                                  caption=f"📦 Архив папки: {os.path.basename(current_dir)}")
            os.unlink(temp_zip.name)
            log_command("Archive Folder", f"Archived: {current_dir}")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка архивации: {str(e)}")

    elif action == "get_file_here":
        current_dir = user_state["current_directory"]
        try:
            bot.edit_message_text(f"📥 Введите имя файла для извлечения из папки:\n{current_dir}", call.message.chat.id,
                                  call.message.message_id)
            user_state["waiting_for_path"] = "get_file"
        except:
            pass

    elif action == "enter_path":
        try:
            bot.edit_message_text("⌨️ Введите полный путь к папке:", call.message.chat.id, call.message.message_id)
            user_state["waiting_for_path"] = "enter_folder"
        except:
            pass

    elif action == "log":
        try:
            with open("command_log.txt", "rb") as f:
                bot.send_document(call.message.chat.id, f, caption="📝 Лог команд")
        except Exception as e:
            bot.answer_callback_query(call.id, f"⚠️ Ошибка: {str(e)}")

    elif action == "kill_menu":
        try:
            process_text, process_list = create_process_list_message()
            user_state["process_list"] = process_list
            user_state["waiting_for_process_kill"] = True

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("🔄 Обновить список", callback_data="kill_menu"))
            system_text = "✅ Системные" if user_state["show_system_processes"] else "❌ Системные"
            keyboard.add(InlineKeyboardButton(f"{system_text} процессы", callback_data="toggle_system"))
            keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))

            bot.edit_message_text(process_text, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        except:
            pass

    elif action == "toggle_system":
        user_state["show_system_processes"] = not user_state["show_system_processes"]
        try:
            process_text, process_list = create_process_list_message()
            user_state["process_list"] = process_list

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("🔄 Обновить список", callback_data="kill_menu"))
            system_text = "✅ Системные" if user_state["show_system_processes"] else "❌ Системные"
            keyboard.add(InlineKeyboardButton(f"{system_text} процессы", callback_data="toggle_system"))
            keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))

            bot.edit_message_text(process_text, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        except:
            pass

    elif action == "volume_control":
        try:
            bot.edit_message_text("🔊 Управление громкостью - выберите действие:", call.message.chat.id,
                                  call.message.message_id, reply_markup=create_volume_keyboard())
        except:
            pass

    elif action == "volume_mute":
        try:
            pyautogui.press('volumemute')
            bot.answer_callback_query(call.id, "🔇 Звук отключен")
            log_command("Volume Control", "Mute")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "volume_up":
        try:
            pyautogui.press('volumeup')
            bot.answer_callback_query(call.id, "🔊 Громкость увеличена")
            log_command("Volume Control", "Volume Up")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "volume_down":
        try:
            pyautogui.press('volumedown')
            bot.answer_callback_query(call.id, "🔈 Громкость уменьшена")
            log_command("Volume Control", "Volume Down")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "key_emulation":
        try:
            bot.edit_message_text("⌨️ Выберите тип эмуляции:", call.message.chat.id, call.message.message_id,
                                  reply_markup=create_key_emulation_keyboard())
        except:
            pass

    elif action == "emulate_text":
        try:
            bot.edit_message_text("💬 Введите текст для эмуляции ввода:", call.message.chat.id, call.message.message_id)
            user_state["waiting_for_emulation_text"] = True
        except:
            pass

    elif action == "special_keys":
        try:
            bot.edit_message_text("⌨️ Выберите специальную клавишу:", call.message.chat.id, call.message.message_id,
                                  reply_markup=create_special_keys_keyboard())
        except:
            pass

    elif action == "key_combinations":
        try:
            bot.edit_message_text("⌨️ Выберите сочетание клавиш:", call.message.chat.id, call.message.message_id,
                                  reply_markup=create_key_combinations_keyboard())
        except:
            pass

    elif action.startswith("key_"):
        key = action[4:]
        try:
            if key == 'Win':
                pyautogui.press('win')
            else:
                pyautogui.press(key.lower())
            bot.answer_callback_query(call.id, f"✅ Клавиша {key} нажата")
            log_command("Key Press", f"Key: {key}")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action.startswith("comb_"):
        comb = action[5:]
        try:
            if comb == "lock":
                ctypes.windll.user32.LockWorkStation()
                bot.answer_callback_query(call.id, "🔒 Экран заблокирован")
            elif comb == "alt_tab":
                pyautogui.hotkey('alt', 'tab')
                bot.answer_callback_query(call.id, "✅ Alt+Tab выполнено")
            elif comb == "ctrl_c":
                pyautogui.hotkey('ctrl', 'c')
                bot.answer_callback_query(call.id, "✅ Ctrl+C выполнено")
            elif comb == "ctrl_v":
                pyautogui.hotkey('ctrl', 'v')
                bot.answer_callback_query(call.id, "✅ Ctrl+V выполнено")
            elif comb == "ctrl_z":
                pyautogui.hotkey('ctrl', 'z')
                bot.answer_callback_query(call.id, "✅ Ctrl+Z выполнено")
            elif comb == "ctrl_a":
                pyautogui.hotkey('ctrl', 'a')
                bot.answer_callback_query(call.id, "✅ Ctrl+A выполнено")
            elif comb == "ctrl_s":
                pyautogui.hotkey('ctrl', 's')
                bot.answer_callback_query(call.id, "✅ Ctrl+S выполнено")
            elif comb == "win_e":
                pyautogui.hotkey('win', 'e')
                bot.answer_callback_query(call.id, "✅ Win+E выполнено")
            elif comb == "win_r":
                pyautogui.hotkey('win', 'r')
                bot.answer_callback_query(call.id, "✅ Win+R выполнено")
            elif comb == "win_d":
                pyautogui.hotkey('win', 'd')
                bot.answer_callback_query(call.id, "✅ Win+D выполнено")
            elif comb == "ctrl_shift_esc":
                pyautogui.hotkey('ctrl', 'shift', 'esc')
                bot.answer_callback_query(call.id, "✅ Ctrl+Shift+Esc выполнено")
            elif comb == "alt_f4":
                pyautogui.hotkey('alt', 'f4')
                bot.answer_callback_query(call.id, "✅ Alt+F4 выполнено")
            log_command("Key Combination", f"Combination: {comb}")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "mouse_emulation":
        try:
            bot.edit_message_text("🖱 Управление мышью - выберите действие:", call.message.chat.id,
                                  call.message.message_id,
                                  reply_markup=create_mouse_emulation_keyboard())
        except:
            pass

    elif action == "mouse_up":
        try:
            pyautogui.move(0, -50)
            bot.answer_callback_query(call.id, "✅ Мышь перемещена вверх")
            log_command("Mouse Control", "Move Up")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "mouse_down":
        try:
            pyautogui.move(0, 50)
            bot.answer_callback_query(call.id, "✅ Мышь перемещена вниз")
            log_command("Mouse Control", "Move Down")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "mouse_left":
        try:
            pyautogui.move(-50, 0)
            bot.answer_callback_query(call.id, "✅ Мышь перемещена влево")
            log_command("Mouse Control", "Move Left")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "mouse_right":
        try:
            pyautogui.move(50, 0)
            bot.answer_callback_query(call.id, "✅ Мышь перемещена вправо")
            log_command("Mouse Control", "Move Right")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "mouse_left_click":
        try:
            pyautogui.click()
            bot.answer_callback_query(call.id, "✅ ЛКМ нажата")
            log_command("Mouse Control", "Left Click")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "mouse_right_click":
        try:
            pyautogui.click(button='right')
            bot.answer_callback_query(call.id, "✅ ПКМ нажата")
            log_command("Mouse Control", "Right Click")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "mouse_middle_click":
        try:
            pyautogui.click(button='middle')
            bot.answer_callback_query(call.id, "✅ СКМ нажата")
            log_command("Mouse Control", "Middle Click")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "mouse_scroll_up":
        try:
            pyautogui.scroll(100)
            bot.answer_callback_query(call.id, "✅ Прокрутка вверх")
            log_command("Mouse Control", "Scroll Up")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "mouse_scroll_down":
        try:
            pyautogui.scroll(-100)
            bot.answer_callback_query(call.id, "✅ Прокрутка вниз")
            log_command("Mouse Control", "Scroll Down")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "lock_screen":
        try:
            ctypes.windll.user32.LockWorkStation()
            bot.send_message(call.message.chat.id, "🔒 Экран заблокирован")
            log_command("Lock Screen", "Screen locked")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")

    elif action == "cmdlist":
        cmd_help = (
            "📋 Основные CMD команды:\n\n"
            "• `cd` - Сменить директорию\n"
            "• `dir` - Показать содержимое папки\n"
            "• `ipconfig` - Информация о сетевых подключениях\n"
            "• `ping` - Проверить доступность хоста\n"
            "• `shutdown /s /t 0` - Немедленное выключение\n"
            "• `shutdown /r /t 0` - Немедленная перезагрузка\n"
            "• `tasklist` - Список процессов\n"
            "• `taskkill /F /PID <pid>` - Завершить процесс\n"
            "• `systeminfo` - Информация о системе\n"
            "• `curl` - Загрузка файлов из интернета\n\n"
            "Для выполнения команд используйте /cmd [команда]"
        )
        bot.send_message(call.message.chat.id, cmd_help, parse_mode="Markdown")

    elif action == "noop":
        pass


@bot.message_handler(content_types=['document'],
                     func=lambda message: message.chat.id == config.CHAT_ID and user_state.get("upload_path"))
def handle_file_upload(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        upload_dir = user_state["upload_path"]
        filename = message.document.file_name
        file_path = os.path.join(upload_dir, filename)

        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)

        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.reply_to(message, f"✅ Файл успешно загружен по пути:\n{file_path}")
        log_command("File Upload", f"Uploaded to: {file_path}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка загрузки файла: {str(e)}")
        log_command("File Upload Error", str(e))
    finally:
        user_state["upload_path"] = None
        keyboard = create_main_menu()
        bot.send_message(message.chat.id, "📱 Возврат в главное меню:", reply_markup=keyboard)


@bot.message_handler(func=lambda message: user_state.get("waiting_for_path") and message.chat.id == config.CHAT_ID)
def handle_path_input(message):
    path = message.text.strip()
    action = user_state["waiting_for_path"]
    user_state["waiting_for_path"] = None

    if action == "get_file":
        try:
            if not os.path.exists(path):
                bot.reply_to(message, "❌ Файл не существует")
            elif os.path.isdir(path):
                bot.reply_to(message, "❌ Указанный путь является папкой, а не файлом")
            else:
                with open(path, 'rb') as f:
                    bot.send_document(message.chat.id, f, caption=f"📄 {os.path.basename(path)}")
        except Exception as e:
            bot.reply_to(message, f"⚠️ Ошибка: {str(e)}")
        finally:
            keyboard = create_main_menu()
            bot.send_message(message.chat.id, "📱 Возврат в главное меню:", reply_markup=keyboard)

    elif action == "enter_folder":
        if os.path.exists(path) and os.path.isdir(path):
            user_state["current_directory"] = path
            content = list_directory(path)
            bot.reply_to(message, f"📂 Содержимое папки: {path}\n\n{content}",
                         reply_markup=create_directory_keyboard(path))
        else:
            bot.reply_to(message, "❌ Указанный путь не существует или не является папкой")
            keyboard = create_main_menu()
            bot.send_message(message.chat.id, "📱 Возврат в главное меню:", reply_markup=keyboard)


if __name__ == "__main__":
    if not os.path.exists("command_log.txt"):
        open("command_log.txt", 'w').close()

    if check_system_uptime():
        try:
            bot.send_message(config.CHAT_ID,
                             "🖥️ Компьютер был запущен! ControlPCbotV2 активен\nАвтор: https://github.com/MrachniyTipchek")
        except Exception as e:
            print(f"Не удалось отправить уведомление о запуске: {str(e)}")

    print("=" * 50)
    print("ControlPCbotV2 - Windows Telegram Control Bot")
    print("=" * 50)
    print(f"Токен: {config.TOKEN}")
    print(f"Chat ID: {config.CHAT_ID}")
    print("Автор: https://github.com/MrachniyTipchek")
    print("\nБот запущен. Ожидание сообщений...")
    print("Для остановки нажмите Ctrl+C")

    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        print(f"\nОшибка: {str(e)}")
        print("Перезапустите бот")