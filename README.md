# Instagram Follower Bot

**Automatyczny bot do obserwowania kont na Instagramie, z dodatkową symulacją akcji (reels, feed, likes)**, napisany w Pythonie z wykorzystaniem Appium i Selenium na emulatorze Android.

---

## Co robi ten kod?

1. **Uruchamia emulator Androida** (AVD) z podanymi ustawieniami DNS.
2. **Startuje Appium Server** i łączy się z nim przez `appium-python-client`.
3. **Loguje się** na Twoje konto Instagram (dane w `config.json`).
4. **Wczytuje listę targetów** z pliku `osobne_konta_insta/<Twoje_konto>/target_accounts_for_followers.txt`.
5. **Otwiera losowo target** i analizuje listę obserwujących, filtrując użytkowników po imionach:

   * Przyjmuje tylko te, których login zawiera imię z `names/names_to_look_for.txt`.
   * Pomija konta zawierające imiona z `names/names_to_avoid.txt`.
6. **Followuje** w partiach (batch) o losowej wielkości, z limitem na godzinę zdefiniowanym w `config.json`.
7. Po osiągnięciu godzinnego celu, losowo:

   * Przełącza się na **Reels** (65% szans) lub **Feed** (35% szans) i scrolluje przez pozostały czas godziny.
8. **Powtarza** proces, wybierając nowy target, aż osiągnie globalny limit followów (`MAX_TO_FOLLOW`) lub zakończy pracę bota.

---

## Wymagania

* **Python 3.8+**
* **Java JDK** (w PATH)
* **Node.js & Appium**

  ```bash
  npm install -g appium
  ```
* **Android SDK & AVD**

  * `adb`, `emulator` w PATH
  * Utworzony AVD o nazwie zgodnej z `EMULATOR_NAME` w `config.json`
  * Android SDK Platform-Tools
* (opcjonalnie) **Sterowniki USB** jeśli używasz fizycznego urządzenia

---

## Instalacja

1. Sklonuj repozytorium i przejdź do katalogu projektu.
2. Uruchom `installer.bat` (Windows) lub wykonaj analogiczne kroki:

   ```bat
   installer.bat
   ```

   * Tworzy wirtualne środowisko `venv` i instaluje:

     * `appium-python-client`
     * `selenium`
     * `colorama`
3. Uzupełnij plik `config.json` swoimi danymi:

   * `USERNAME`, `PASSWORD`
   * `EMULATOR_NAME`, `EMULATOR_UDID`, `DNS`
   * Limity i godziny pracy

---

## Konfiguracja

* **`config.json`**

  * Dane do logowania (`USERNAME`, `PASSWORD`)
  * Limity (`MAX_TO_FOLLOW`, `HOURLY_TARGET_RANGE`)
  * Harmonogram pracy (`BOT_START_TIME`, `BOT_END_TIME`, offsety)
  * Ustawienia emulatora (`EMULATOR_NAME`, `EMULATOR_UDID`, `DNS`)
  * Itd.

* **`/names/`**

  * `names_to_look_for.txt` – imiona do wyszukiwania w nicku (jedno na linii)
  * `names_to_avoid.txt` – imiona do pominięcia

* **`/osobne_konta_insta/`**

  * Dla każdego konta (folder o nazwie Twojego loginu) musi istnieć:

    ```text
    target_accounts_for_followers.txt
    ```
  * Bot dopisuje `DONE` do przetworzonych targetów i je pomija.

---

## Uruchomienie

1. Aktywuj środowisko:

   ```bat
   call venv\Scripts\activate
   ```
2. Uruchom skrypt:

   ```bat
   python main.py
   ```

---

## Struktura katalogów

```text
project-root/
├── installer.bat
├── main.py
├── config.json
├── venv/                # utworzone przez installer.bat
├── names/
│   ├── names_to_look_for.txt
│   └── names_to_avoid.txt
└── osobne_konta_insta/
    └── <YOUR_USERNAME(OR MAIL)>/
        ├── target_accounts_for_followers.txt
        ├── already_followed.txt
        └── total_followed.json
```

---

## Troubleshooting

* **Appium nie startuje** → upewnij się, że `appium` jest zainstalowany globalnie i w PATH.
* **AVD nie odnajduje się** → sprawdź, czy nazwa emulatora w `config.json` zgadza się z `avdmanager list avd`.
* **Brak `adb`** → zainstaluj Android SDK Platform-Tools i dodaj do PATH.

---