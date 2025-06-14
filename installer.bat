@echo off
REM przejdź do katalogu skryptu
cd /d "%~dp0"

REM 1) Utworzenie i aktywacja wirtualnego środowiska
python -m venv venv
call venv\Scripts\activate

REM 2) Aktualizacja pip
python -m pip install --upgrade pip

REM 3) Instalacja wymaganych paczek
pip install appium-python-client selenium colorama

REM 4) Przygotowanie folderów z listami imion (jeśli nie istnieją)
if not exist names (
    mkdir names
    type nul > names\names_to_look_for.txt
    type nul > names\names_to_avoid.txt
)

pause
