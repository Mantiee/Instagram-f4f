@echo off
REM Przejdź do katalogu, w którym znajduje się ten skrypt
cd /d "%~dp0"

REM Uruchom main.py za pomocą Pythona. Jeżeli masz wirtualne środowisko,
REM odkomentuj i dostosuj poniższą linię:
REM call venv\Scripts\activate

python main.py %*

REM Jeśli chcesz, aby okno zostało otwarte po zakończeniu skryptu, odkomentuj:
REM pause
