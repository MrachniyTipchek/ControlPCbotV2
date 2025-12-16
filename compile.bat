@echo off

chcp 65001 >nul

echo ========================================

echo ControlPCbotV2 - Компиляция в EXE

echo ========================================

echo.



if not exist "main.py" (

    echo Ошибка: файл main.py не найден!

    pause

    exit /b 1

)



echo Установка зависимостей...

python -m pip install --upgrade pip --no-warn-script-location

echo Установка основных зависимостей...

python -m pip install pyTelegramBotAPI==4.14.0 --no-warn-script-location
if errorlevel 1 (
    echo Ошибка установки pyTelegramBotAPI
    pause
    exit /b 1
)

python -m pip install psutil==5.9.5 --no-warn-script-location
if errorlevel 1 (
    echo Ошибка установки psutil
    pause
    exit /b 1
)

python -m pip install pyautogui==0.9.54 --no-warn-script-location
if errorlevel 1 (
    echo Ошибка установки pyautogui
    pause
    exit /b 1
)

python -m pip install pywin32 --no-warn-script-location
if errorlevel 1 (
    echo Ошибка установки pywin32
    pause
    exit /b 1
)

python -m pip install win10toast==0.9 --no-warn-script-location
if errorlevel 1 (
    echo Ошибка установки win10toast
    pause
    exit /b 1
)

python -m pip install "Pillow>=10.0.0" --no-warn-script-location
if errorlevel 1 (
    echo Ошибка установки Pillow
    pause
    exit /b 1
)

python -m pip install pystray==0.19.5 --no-warn-script-location
if errorlevel 1 (
    echo Ошибка установки pystray
    pause
    exit /b 1
)

python -m pip install pyinstaller --no-warn-script-location
if errorlevel 1 (
    echo Ошибка установки pyinstaller
    pause
    exit /b 1
)



echo.

echo Очистка предыдущих сборок...

if exist "build" rmdir /s /q "build"

if exist "dist" rmdir /s /q "dist"



echo.

echo Компиляция программы...

pyinstaller --onefile --windowed --name="ControlPCbotV2" --clean --icon=icon.ico --add-data "icon.ico;." --hidden-import=pystray --hidden-import=PIL._tkinter_finder --hidden-import=win32com.client --hidden-import=win32timezone main.py



echo.

echo ========================================

echo Компиляция завершена!

echo Файл находится в папке dist\ControlPCbotV2.exe

echo.

echo При первом запуске откроется установщик.

echo После установки программа будет работать из папки установки.

echo ========================================

pause

