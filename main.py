import os
import logging
import subprocess
import time
import telebot
import psutil
import pyautogui
import tempfile
import winreg
import getpass
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
    "autostart_enabled": False
}


def log_command(command, output):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open("command_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Command: {command}\n")
        f.write(f"Output: {output}\n\n")


def show_notification(command):
    toaster.show_toast("Telegram Bot Command", f"Executed command:\n{command}", duration=5, threaded=True)


def create_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("🖥️ Выключить ПК", callback_data="shutdown"),
        InlineKeyboardButton("🔄 Перезагрузить ПК", callback_data="reboot"),
        InlineKeyboardButton("📸 Скриншот", callback_data="screenshot"),
        InlineKeyboardButton("📁 Извлечь файл", callback_data="get_file"),
        InlineKeyboardButton("📤 Загрузить файл", callback_data="upload_file"),
        InlineKeyboardButton("📂 Просмотр папки", callback_data="list_dir"),
        InlineKeyboardButton("❌ Завершить процесс", callback_data="kill_menu"),
        InlineKeyboardButton("📝 Лог команд", callback_data="log"),
        InlineKeyboardButton("🚀 Автозапуск", callback_data="autostart_menu"),
        InlineKeyboardButton("ℹ️ CMD команды", callback_data="cmdlist"),
        InlineKeyboardButton("📋 Главное меню", callback_data="main_menu"),
        InlineKeyboardButton("🛑 Выход", callback_data="exit")
    ]
    keyboard.add(*buttons)
    return keyboard


def create_process_keyboard(page=0, show_system=False):
    keyboard = InlineKeyboardMarkup()
    processes = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if not show_system and proc.pid < 1000:
                continue
            processes.append((proc.pid, proc.name()))
        except:
            pass

    if not processes:
        keyboard.add(InlineKeyboardButton("❌ Процессы не найдены", callback_data="noop"))
        keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
        return keyboard

    total_pages = (len(processes) // 5 + (1 if len(processes) % 5 > 0 else 0))
    start_index = page * 5
    end_index = start_index + 5
    current_page = processes[start_index:end_index]

    for pid, name in current_page:
        keyboard.add(InlineKeyboardButton(f"{name} (PID: {pid})", callback_data=f"select_{pid}"))

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"proc_page_{page - 1}"))
    if end_index < len(processes):
        nav_buttons.append(InlineKeyboardButton("▶️ Вперед", callback_data=f"proc_page_{page + 1}"))

    if nav_buttons:
        keyboard.add(*nav_buttons)

    keyboard.add(InlineKeyboardButton(f"Страница {page + 1}/{total_pages}", callback_data="noop"))

    system_text = "✅ Системные" if show_system else "❌ Системные"
    keyboard.add(InlineKeyboardButton(f"{system_text} процессы", callback_data="toggle_system"))

    keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
    return keyboard


def create_confirmation_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да, завершить", callback_data="kill_confirm"),
        InlineKeyboardButton("❌ Нет, отмена", callback_data="kill_cancel")
    )
    return keyboard


def create_exit_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="shutdown_confirm"),
        InlineKeyboardButton("❌ Нет", callback_data="shutdown_cancel")
    )
    return keyboard


def create_reboot_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data="reboot_confirm"),
        InlineKeyboardButton("❌ Нет", callback_data="reboot_cancel")
    )
    return keyboard


def create_autostart_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Включить автозапуск", callback_data="autostart_enable"),
        InlineKeyboardButton("❌ Отключить автозапуск", callback_data="autostart_disable"),
        InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")
    )
    return keyboard


def take_screenshot():
    screenshot = pyautogui.screenshot()
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    screenshot.save(temp_file.name)
    return temp_file.name


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


def enable_autostart():
    try:
        script_path = os.path.abspath(__file__)
        bat_path = os.path.join(os.path.dirname(script_path), "start.bat")

        with open(bat_path, "w") as bat_file:
            bat_file.write(f'@echo off\n')
            bat_file.write(f'cd /d "{os.path.dirname(script_path)}"\n')
            bat_file.write(f'python "{script_path}"\n')

        username = getpass.getuser()
        task_name = "TelegramBotAutoStart"
        cmd = f'schtasks /create /tn "{task_name}" /tr "{bat_path}" /sc onlogon /ru {username} /f'
        subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception as e:
        print(f"Error enabling autostart: {e}")
        return False


def disable_autostart():
    try:
        task_name = "TelegramBotAutoStart"
        cmd = f'schtasks /delete /tn "{task_name}" /f'
        subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        script_path = os.path.abspath(__file__)
        bat_path = os.path.join(os.path.dirname(script_path), "start.bat")
        if os.path.exists(bat_path):
            os.remove(bat_path)
        return True
    except Exception as e:
        print(f"Error disabling autostart: {e}")
        return False


def check_autostart():
    try:
        task_name = "TelegramBotAutoStart"
        cmd = f'schtasks /query /tn "{task_name}"'
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode == 0
    except:
        return False


@bot.message_handler(func=lambda message: message.chat.id != config.CHAT_ID)
def handle_unauthorized(message):
    bot.reply_to(message, "⛔ Доступ запрещен")


@bot.message_handler(commands=['start', 'help', 'menu'])
def send_welcome(message):
    if message.chat.id != config.CHAT_ID:
        return
    help_text = (
        "🤖 Бот управления компьютером\n\n"
        "Доступные команды:\n"
        "/menu - Главное меню\n"
        "/cmd [команда] - Выполнить команду в CMD\n"
        "/cmdlist - Список полезных CMD команд\n"
        "/kill - Завершить процесс\n"
        "/log - Получить лог команд\n"
        "/autostart - Управление автозапуском\n\n"
        "⚠️ Для выполнения команд требуются права администратора"
    )
    bot.send_message(message.chat.id, help_text, reply_markup=create_main_menu())


@bot.message_handler(commands=['control'])
def show_control_menu(message):
    if message.chat.id != config.CHAT_ID:
        return
    bot.send_message(message.chat.id, "📱 Главное меню управления:", reply_markup=create_main_menu())


@bot.message_handler(commands=['kill'])
def show_kill_menu(message):
    if message.chat.id != config.CHAT_ID:
        return
    user_state["process_page"] = 0
    bot.send_message(message.chat.id, "🛑 Выберите процесс для завершения:",
                     reply_markup=create_process_keyboard(0, user_state["show_system_processes"]))


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
            timeout=60,
            encoding='cp866'
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
        "• `curl` - Загрузка файлов из интернета\n"
        "• `netsh wlan show profiles` - Показать Wi-Fi сети\n"
        "• `netsh wlan show profile name=\"NETWORK\" key=clear` - Показать пароль Wi-Fi\n\n"
        "Для выполнения команд используйте /cmd [команда]"
    )
    bot.send_message(message.chat.id, cmd_help, parse_mode="Markdown")


@bot.message_handler(
    func=lambda message: user_state.get("waiting_for_path") and message.chat.id == config.CHAT_ID and user_state[
        "waiting_for_path"] != "upload_file")
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
            bot.send_message(message.chat.id, "📱 Возврат в главное меню:", reply_markup=create_main_menu())
    elif action == "list_dir":
        result = list_directory(path)
        if len(result) > 4000:
            with open("dir_list.txt", "w", encoding="utf-8") as f:
                f.write(result)
            with open("dir_list.txt", "rb") as f:
                bot.send_document(message.chat.id, f)
            os.remove("dir_list.txt")
        else:
            bot.reply_to(message, result)
        bot.send_message(message.chat.id, "📱 Возврат в главное меню:", reply_markup=create_main_menu())
    elif action == "upload_file":
        user_state["upload_path"] = path
        bot.reply_to(message, "📤 Теперь отправьте файл для загрузки")


@bot.message_handler(content_types=['document'],
                     func=lambda message: message.chat.id == config.CHAT_ID and user_state.get("upload_path"))
def handle_file_upload(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        directory = os.path.dirname(user_state["upload_path"])
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        with open(user_state["upload_path"], 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.reply_to(message, f"✅ Файл успешно загружен по пути:\n{user_state['upload_path']}")
        log_command("File Upload", f"Uploaded to: {user_state['upload_path']}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка загрузки файла: {str(e)}")
        log_command("File Upload Error", str(e))
    finally:
        user_state["upload_path"] = None
        bot.send_message(message.chat.id, "📱 Возврат в главное меню:", reply_markup=create_main_menu())


@bot.callback_query_handler(func=lambda call: call.message.chat.id != config.CHAT_ID)
def handle_unauthorized_callback(call):
    bot.answer_callback_query(call.id, "⛔ Доступ запрещен")


@bot.callback_query_handler(func=lambda call: call.message.chat.id == config.CHAT_ID)
def handle_control_buttons(call):
    bot.answer_callback_query(call.id)
    action = call.data
    if action == "main_menu":
        bot.edit_message_text("📱 Главное меню управления:", call.message.chat.id, call.message.message_id,
                              reply_markup=create_main_menu())
    elif action == "shutdown":
        bot.edit_message_text("⚠️ Вы уверены, что хотите выключить компьютер?", call.message.chat.id,
                              call.message.message_id, reply_markup=create_exit_keyboard())
    elif action == "shutdown_confirm":
        bot.edit_message_text("🖥️ Компьютер будет выключен через 1 минуту!", call.message.chat.id,
                              call.message.message_id)
        log_command("System Shutdown", "Initiated by bot")
        os.system("shutdown /s /t 60")
    elif action == "shutdown_cancel":
        bot.edit_message_text("❌ Выключение отменено", call.message.chat.id, call.message.message_id,
                              reply_markup=create_main_menu())
    elif action == "reboot":
        bot.edit_message_text("⚠️ Вы уверены, что хотите перезагрузить компьютер?", call.message.chat.id,
                              call.message.message_id, reply_markup=create_reboot_keyboard())
    elif action == "reboot_confirm":
        bot.edit_message_text("🖥️ Компьютер будет перезагружен через 1 минуту!", call.message.chat.id,
                              call.message.message_id)
        log_command("System Reboot", "Initiated by bot")
        os.system("shutdown /r /t 60")
    elif action == "reboot_cancel":
        bot.edit_message_text("❌ Перезагрузка отменена", call.message.chat.id, call.message.message_id,
                              reply_markup=create_main_menu())
    elif action == "screenshot":
        try:
            screenshot_path = take_screenshot()
            with open(screenshot_path, 'rb') as photo:
                bot.send_photo(call.message.chat.id, photo)
            os.unlink(screenshot_path)
            log_command("Screenshot", "Taken")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")
    elif action == "get_file":
        bot.edit_message_text("📤 Введите полный путь к файлу:", call.message.chat.id, call.message.message_id)
        user_state["waiting_for_path"] = "get_file"
    elif action == "list_dir":
        bot.edit_message_text("📂 Введите путь к папке:", call.message.chat.id, call.message.message_id)
        user_state["waiting_for_path"] = "list_dir"
    elif action == "upload_file":
        bot.edit_message_text("📤 Введите полный путь для сохранения файла:", call.message.chat.id,
                              call.message.message_id)
        user_state["waiting_for_path"] = "upload_file"
    elif action == "log":
        try:
            with open("command_log.txt", "rb") as f:
                bot.send_document(call.message.chat.id, f, caption="📝 Лог команд")
        except Exception as e:
            bot.answer_callback_query(call.id, f"⚠️ Ошибка: {str(e)}")
    elif action == "kill_menu":
        user_state["process_page"] = 0
        bot.edit_message_text("🛑 Выберите процесс для завершения:", call.message.chat.id, call.message.message_id,
                              reply_markup=create_process_keyboard(0, user_state["show_system_processes"]))
    elif action == "toggle_system":
        user_state["show_system_processes"] = not user_state["show_system_processes"]
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=create_process_keyboard(user_state["process_page"],
                                                                           user_state["show_system_processes"]))
    elif action.startswith("proc_page_"):
        page = int(action.split("_")[2])
        user_state["process_page"] = page
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=create_process_keyboard(page, user_state["show_system_processes"]))
    elif action.startswith("select_"):
        pid = int(action.split("_")[1])
        try:
            process = psutil.Process(pid)
            user_state["selected_process"] = pid
            bot.edit_message_text(
                f"⚠️ Завершить процесс?\n\nИмя: {process.name()}\nPID: {pid}\nСтатус: {process.status()}",
                call.message.chat.id, call.message.message_id, reply_markup=create_confirmation_keyboard())
        except psutil.NoSuchProcess:
            bot.answer_callback_query(call.id, "❌ Процесс не найден")
    elif action == "kill_confirm":
        if user_state["selected_process"]:
            try:
                p = psutil.Process(user_state["selected_process"])
                p.terminate()
                bot.edit_message_text(f"✅ Процесс {p.name()} (PID: {user_state['selected_process']}) завершен",
                                      call.message.chat.id, call.message.message_id, reply_markup=create_main_menu())
                log_command("Kill Process", f"Terminated {p.name()} (PID: {user_state['selected_process']})")
            except Exception as e:
                bot.edit_message_text(f"❌ Ошибка завершения процесса: {str(e)}", call.message.chat.id,
                                      call.message.message_id, reply_markup=create_main_menu())
            finally:
                user_state["selected_process"] = None
    elif action == "kill_cancel":
        user_state["selected_process"] = None
        bot.edit_message_text("❌ Завершение процесса отменено", call.message.chat.id, call.message.message_id,
                              reply_markup=create_main_menu())
    elif action == "autostart_menu":
        status = "✅ Включен" if check_autostart() else "❌ Выключен"
        bot.edit_message_text(f"🚀 Управление автозапуском\n\nТекущий статус: {status}", call.message.chat.id,
                              call.message.message_id, reply_markup=create_autostart_keyboard())
    elif action == "autostart_enable":
        if enable_autostart():
            bot.answer_callback_query(call.id, "✅ Автозапуск включен")
            bot.edit_message_text("🚀 Управление автозапуском\n\nТекущий статус: ✅ Включен", call.message.chat.id,
                                  call.message.message_id, reply_markup=create_autostart_keyboard())
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка включения автозапуска")
    elif action == "autostart_disable":
        if disable_autostart():
            bot.answer_callback_query(call.id, "✅ Автозапуск отключен")
            bot.edit_message_text("🚀 Управление автозапуском\n\nТекущий статус: ❌ Выключен", call.message.chat.id,
                                  call.message.message_id, reply_markup=create_autostart_keyboard())
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка отключения автозапуска")
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
            "• `curl` - Загрузка файлов из интернета\n"
            "• `netsh wlan show profiles` - Показать Wi-Fi сети\n"
            "• `netsh wlan show profile name=\"NETWORK\" key=clear` - Показать пароль Wi-Fi\n\n"
            "Для выполнения команд используйте /cmd [команда]"
        )
        bot.send_message(call.message.chat.id, cmd_help, parse_mode="Markdown")
    elif action == "exit":
        bot.edit_message_text("👋 Бот завершает работу. Для возобновления отправьте /start", call.message.chat.id,
                              call.message.message_id)


if __name__ == "__main__":
    user_state["autostart_enabled"] = check_autostart()

    if not os.path.exists("command_log.txt"):
        open("command_log.txt", 'w').close()

    print("=" * 50)
    print("Windows Telegram Control Bot")
    print("=" * 50)
    print(f"Токен: {config.TOKEN}")
    print(f"Chat ID: {config.CHAT_ID}")
    print(f"Автозапуск: {'✅ Включен' if user_state['autostart_enabled'] else '❌ Выключен'}")
    print("\nБот запущен. Ожидание сообщений...")
    print("Для остановки нажмите Ctrl+C")

    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"\nОшибка: {str(e)}")
        print("Перезапустите бот")