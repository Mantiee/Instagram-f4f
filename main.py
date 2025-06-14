import os
import time
import random
import sys
import json
import re
import datetime
import subprocess
from pathlib import Path
import threading

# Importy Appium i Selenium
from appium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchDriverException
from appium.options.android import UiAutomator2Options
from colorama import init, Fore, Style

init(autoreset=True)

# GLOBALNE
global_last_index = 0
global_followers_start_wait = None
last_action_time = time.time()  # Kiedy ostatnio bot coś faktycznie zrobił
stop_bot = False  # Flaga przerwania sesji (poza dozwolonym zakresem)
downtime_start = None  # Czas rozpoczęcia przerwy

bot_mode = None           # "followers" lub "waiting"
last_wait_mode = None     # "feed" albo "reels" – jeśli bot czeka między sesjami
last_wait_remaining = 0   # Pozostały czas oczekiwania, jeśli był tryb "waiting"

# Dla zachowania stanu sesji – te zmienne nie są resetowane przy restarcie
session_start_time = None
current_target = None
current_hour_followed = 0

# Flaga informująca, że program wykonuje "wymuszony sleep" – wówczas monitor nie liczy czasu oczekiwania
forced_sleep = False

appium_error_time = None

# Definicja własnego wyjątku
class RateLimitException(Exception):
    pass

# ==================== KONFIGURACJA STRINGOWA ====================
BASE_DIR = os.path.join(os.getcwd(), "osobne_konta_insta")
# Pliki użytkownika będą tworzone tylko wewnątrz folderu użytkownika – nie tworzymy zbędnych folderów
CONFIG_FILE = "config.json"

# ------------------- SELEKTORY DLA NATYWNEJ APLIKACJI -------------------
MOBILE_LOGIN_USERNAME_SELECTOR = "//*[@resource-id='com.instagram.android:id/login_username']"
MOBILE_LOGIN_PASSWORD_SELECTOR = "//*[@resource-id='com.instagram.android:id/login_password']"
MOBILE_LOGIN_BUTTON_SELECTOR = "//*[@resource-id='com.instagram.android:id/button_login']"
MOBILE_NOT_NOW_BUTTON_SELECTOR = "//*[@text='Not Now' or @text='Nie teraz']"
INSTAGRAM_DEEP_LINK_PROFILE = "instagram://user?username={}"
MOBILE_FOLLOWERS_BUTTON_SELECTOR = "//*[@text='followers' or @text='Obserwujący']"
MOBILE_FOLLOWERS_LIST_XPATH = "//*[@resource-id='com.instagram.android:id/unified_follow_list_view_pager']"
MOBILE_FOLLOWER_ROW_XPATH = "//*[@resource-id='com.instagram.android:id/follow_list_container']"
MOBILE_FOLLOW_BUTTON_ROW_XPATH = "//*[@resource-id='com.instagram.android:id/follow_list_row_large_follow_button']"
MOBILE_PROFILE_FOLLOW_BUTTON_SELECTOR = "//*[@resource-id='com.instagram.android:id/profile_header_follow_button']"
MOBILE_BACK_BUTTON_SELECTOR = "//*[@resource-id='com.instagram.android:id/action_bar_button_back']"
MOBILE_PROFILE_POST_BUTTON_SELECTOR = "//*[@resource-id='com.instagram.android:id/image_button']"
MOBILE_PROFILE_LIKE_BUTTON_SELECTOR = "//*[@resource-id='com.instagram.android:id/row_feed_button_like']"
MOBILE_REELS_TAB_SELECTOR = "//*[@resource-id='com.instagram.android:id/clips_tab' and contains(@class, 'FrameLayout')]"
MOBILE_REELS_LIKE_BUTTON_SELECTOR = "//*[@resource-id='com.instagram.android:id/like_button' and contains(@class, 'android.widget.ImageView')]"
SEARCH_TAB_SELECTOR = "//*[@resource-id='com.instagram.android:id/search_tab' and contains(@class, 'FrameLayout')]"
SEARCH_FIELD_SELECTOR = "//*[@resource-id='com.instagram.android:id/action_bar_search_edit_text' and contains(@class, 'EditText')]"
FIRST_RESULT_SELECTOR = "//*[@resource-id='com.instagram.android:id/row_search_user_info_container' and contains(@class, 'LinearLayout')]"
SPAN_USERNAME_XPATH = ".//android.widget.TextView"
SUGGESTED_TEXT = "Suggested for you"


# ==================== KONFIGURACJA LICZBOWA I CZASOWA ====================
def load_config():
    default_config = {
        "STAY_LOGGED_IN": {"value": True, "comment": "Czy pozostac zalogowanym"},
        "USERNAME": {"value": "", "comment": "Nazwa użytkownika na Instagram"},
        "PASSWORD": {"value": "", "comment": "Hasło do konta"},
        "HEADLESS": {"value": False, "comment": "Tryb headless (nie dotyczy mobilnej)"},
        "MAX_TO_FOLLOW": {"value": 1000, "comment": "Maksymalna liczba kont do followowania"},
        "BATCH_SIZE_MIN": {"value": 1, "comment": "Minimalny rozmiar partii"},
        "BATCH_SIZE_MAX": {"value": 4, "comment": "Maksymalny rozmiar partii"},
        "HOURLY_TARGET_RANGE": {"value": [18, 23], "comment": "Docelowa liczba followów na godzinę"},
        "BOT_START_TIME": {"value": 10, "comment": "Godzina rozpoczęcia pracy bota"},
        "BOT_END_TIME": {"value": 21, "comment": "Godzina zakończenia pracy bota"},
        "BOT_ACTIVE_TIME_OFFSET_RANGE": {"value": [-60, 60], "comment": "Offset w minutach"},
        "EMULATOR_NAME": {"value": "Pixel_1", "comment": "Nazwa AVD/emulatora"},
        "EMULATOR_UDID": {"value": "emulator-5554", "comment": "UDID emulatora"},
        "DNS": {"value": "8.8.8.8,4.4.4.4", "comment": "lista DNS dla emulatora, przecinkiem"}
    }
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        print(f"[INFO] Utworzono {CONFIG_FILE} z wartościami domyślnymi.")
        return default_config
    else:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

config = load_config()
STAY_LOGGED_IN = config["STAY_LOGGED_IN"]["value"]
USERNAME = config["USERNAME"]["value"]
PASSWORD = config["PASSWORD"]["value"]
MAX_TO_FOLLOW = config["MAX_TO_FOLLOW"]["value"]
BATCH_SIZE_MIN = config["BATCH_SIZE_MIN"]["value"]
BATCH_SIZE_MAX = config["BATCH_SIZE_MAX"]["value"]
HOURLY_TARGET_RANGE = tuple(config["HOURLY_TARGET_RANGE"]["value"])
BOT_START_TIME = config["BOT_START_TIME"]["value"]
BOT_END_TIME = config["BOT_END_TIME"]["value"]
BOT_ACTIVE_TIME_OFFSET_RANGE = tuple(config["BOT_ACTIVE_TIME_OFFSET_RANGE"]["value"])
START_OFFSET = random.randint(*BOT_ACTIVE_TIME_OFFSET_RANGE)
END_OFFSET = random.randint(*BOT_ACTIVE_TIME_OFFSET_RANGE)
EMULATOR_NAME = config["EMULATOR_NAME"]["value"]
EMULATOR_UDID = config["EMULATOR_UDID"]["value"]
DNS = config["DNS"]["value"]

# Zakresy oczekiwań
LOGIN_LOAD_WAIT_RANGE = (5, 8)
AFTER_LOGIN_WAIT_RANGE = (5, 9)
FOLLOWERS_CLICK_WAIT_RANGE = (5, 8)
WAIT_AFTER_SCROLL_RANGE = (2, 4)
SCROLL_PAUSE_RANGE = (0.3, 1.4)
FOLLOW_ACTION_WAIT_RANGE = (8, 10)
LOAD_PROFILE_WAIT_RANGE = (5, 8)
OPEN_POST_WAIT_RANGE = (4.0, 6.0)
LIKE_POST_WAIT_RANGE = (2, 3.5)
AFTER_CLOSE_POST_WAIT_RANGE = (1.0, 2.0)
MAIN_PAGE_AFTER_OPEN_WAIT_RANGE = (3, 5)
MAIN_PAGE_SCROLL_DELAY_BASE = 30
MAIN_PAGE_SCROLL_DELAY_OFFSET_RANGE = (-9, 9)
MAIN_PAGE_BETWEEN_SCROLLS_WAIT_RANGE = (0.35, 0.7)
SESSION_OFFSET_RANGE_SHORT = (-200, 500)
SESSION_OFFSET_RANGE_LONG = (420, 800)
DYNAMIC_WAIT_OFFSET_RANGE = (-220, 220)

# Kolory ANSI
GREEN = Fore.GREEN
RED = Fore.RED
YELLOW = Fore.YELLOW
WHITE = Fore.WHITE
BLUE = Fore.BLUE
RESET = Style.RESET_ALL

avg_hourly_target = (HOURLY_TARGET_RANGE[0] + HOURLY_TARGET_RANGE[1]) / 2.0
avg_batch_size = (BATCH_SIZE_MIN + BATCH_SIZE_MAX) / 2.0
avg_followers_click = (FOLLOWERS_CLICK_WAIT_RANGE[0] + FOLLOWERS_CLICK_WAIT_RANGE[1]) / 2.0
avg_wait_after_scroll = (WAIT_AFTER_SCROLL_RANGE[0] + WAIT_AFTER_SCROLL_RANGE[1]) / 2.0
avg_scroll_pause = (SCROLL_PAUSE_RANGE[0] + SCROLL_PAUSE_RANGE[1]) / 2.0
avg_follow_action = (FOLLOW_ACTION_WAIT_RANGE[0] + FOLLOW_ACTION_WAIT_RANGE[1]) / 2.0
avg_scrolling_time = avg_scroll_pause + avg_wait_after_scroll
avg_load_profile_wait = (LOAD_PROFILE_WAIT_RANGE[0] + LOAD_PROFILE_WAIT_RANGE[1]) / 2.0
avg_open_post_wait = (OPEN_POST_WAIT_RANGE[0] + OPEN_POST_WAIT_RANGE[0]) / 2.0
avg_like_post_wait = (LIKE_POST_WAIT_RANGE[0] + LIKE_POST_WAIT_RANGE[1]) / 2.0
avg_after_close_post_wait = (AFTER_CLOSE_POST_WAIT_RANGE[0] + AFTER_CLOSE_POST_WAIT_RANGE[1]) / 2.0
avg_batch_time = (2 * avg_follow_action * avg_batch_size) + (avg_wait_after_scroll * 2) + (0.4 * (
            avg_load_profile_wait + (
                1.5 * 0.5 * (avg_open_post_wait + avg_like_post_wait + avg_after_close_post_wait))))
base_dynamic_wait = (3600 / (avg_hourly_target / avg_batch_size)) - avg_batch_time
print(f"[DEBUG] Base dynamic wait: {base_dynamic_wait:.2f} sekund.")

# ==================== WCZYTYWANIE POLSKICH IMION ====================
names_file = os.path.join(os.getcwd(), "names", "names_to_look_for.txt")
try:
    with open(names_file, "r", encoding="utf-8") as f:
        polish_firstnames = [line.strip().lower() for line in f if line.strip()]
    print(f"{GREEN}[INFO] Wczytano {len(polish_firstnames)} imion z {names_file}.{RESET}")
except Exception as e:
    print(f"{RED}[BŁĄD] Nie udało się wczytać imion: {e}{RESET}")
    polish_firstnames = []

polish_female_names_file = os.path.join(os.getcwd(), "names", "names_to_avoid.txt")
try:
    with open(polish_female_names_file, "r", encoding="utf-8") as f:
        polish_female_firstnames = [line.strip().lower() for line in f if line.strip()]
    print(f"{GREEN}[INFO] Wczytano {len(polish_female_firstnames)} imion z {polish_female_names_file}.{RESET}")
except Exception as e:
    print(f"{RED}[BŁĄD] Nie udało się wczytać imion: {e}{RESET}")
    polish_female_firstnames = []

# ==================== FUNKCJE POMOCNICZE DO FORMATOWANIA I OCZEKIWANIA ====================
def format_duration(seconds):
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        sec = seconds % 60
        return f"{hours}h {minutes}m {sec}s"

def dynamic_sleep(duration, message):
    global forced_sleep, appium_error_time
    forced_sleep = True
    start_time_system = datetime.datetime.now()
    print(f"[DEBUG] Start time: {start_time_system.strftime('%Y-%m-%d %H:%M:%S')}")
    end_time = time.time() + duration
    while True:
        if stop_bot:
            break
        remaining = end_time - time.time()
        if remaining < 0:
            remaining = 0
        sys.stdout.write("\r" + message + f" (pozostało: {format_duration(remaining)})")
        sys.stdout.flush()
        if remaining <= 0:
            break
        time.sleep(1 if remaining >= 1 else remaining)
    sys.stdout.write("\n")
    forced_sleep = False

def sleep_random(range_tuple, description=""):
    wait_time = random.uniform(*range_tuple)
    if wait_time > 10:
        dynamic_sleep(wait_time, f"[INFO] Czekam {wait_time:.2f} sekund {description}.")
    else:
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[DEBUG] Current system time: {current_time}")
        print(f"[INFO] Czekam {wait_time:.2f} sekund {description}")
        time.sleep(wait_time)

# ==================== FUNKCJE POMOCNICZE DO SWIPE'ÓW I TAPÓW ====================
def tap_element(element):
    loc = element.location
    size = element.size
    center_x = int(loc['x'] + size['width'] / 2)
    center_y = int(loc['y'] + size['height'] / 2)
    actions = ActionChains(driver)
    actions.w3c_actions.pointer_action.move_to_location(center_x, center_y)
    actions.w3c_actions.pointer_action.pointer_down()
    actions.w3c_actions.pointer_action.pointer_up()
    actions.perform()

def swipe_up():
    size = driver.get_window_size()
    screen_height = size['height']
    screen_width = size['width']
    swipe_distance = int(screen_height * 0.32)
    start_x = screen_width // 2
    start_y = int(screen_height * 0.8)
    end_y = start_y - swipe_distance
    actions = ActionChains(driver)
    actions.w3c_actions.pointer_action.move_to_location(start_x, start_y)
    actions.w3c_actions.pointer_action.pointer_down()
    actions.w3c_actions.pointer_action.move_to_location(start_x, end_y)
    actions.w3c_actions.pointer_action.pointer_up()
    actions.perform()

def small_swipe():
    size = driver.get_window_size()
    screen_height = size['height']
    screen_width = size['width']
    standard_distance = int(screen_height * 0.25)
    small_distance = int(standard_distance / 3)
    start_x = screen_width // 2
    start_y = int(screen_height * 0.8)
    end_y = start_y - small_distance
    actions = ActionChains(driver)
    actions.w3c_actions.pointer_action.move_to_location(start_x, start_y)
    actions.w3c_actions.pointer_action.pointer_down()
    actions.w3c_actions.pointer_action.move_to_location(start_x, end_y)
    actions.w3c_actions.pointer_action.pointer_up()
    actions.perform()

def get_screen_size_adb():
    """
    Pobiera rozmiar ekranu przez ADB
    """
    try:
        result = subprocess.run(['adb', 'shell', 'wm', 'size'],
                              capture_output=True, text=True, check=True)
        # Output: Physical size: 1080x2340
        size_line = result.stdout.strip()
        if 'Physical size:' in size_line:
            dimensions = size_line.split(':')[1].strip()
            width, height = map(int, dimensions.split('x'))
            return width, height
        return 1080, 2340  # fallback
    except:
        return 1080, 2340  # fallback

def swipe_up_reels():
    try:
        width, height = get_screen_size_adb()

        # Środek ekranu jako punkt startowy
        start_x = width // 2
        start_y = int(height * 0.8)  # 80% wysokości ekranu (dół)

        # Punkt końcowy (góra)
        end_x = width // 2
        end_y = int(height * 0.2)  # 20% wysokości ekranu (góra)

        # Czas trwania swipe w ms
        duration = 300

        # Komenda ADB swipe
        cmd = ['adb', 'shell', 'input', 'swipe',
               str(start_x), str(start_y), str(end_x), str(end_y), str(duration)]

        print(f"ADB swipe: {start_x},{start_y} -> {end_x},{end_y}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("✓ ADB swipe wykonany pomyślnie")
            time.sleep(0.5)
            return True
        else:
            print(f"✗ ADB swipe błąd: {result.stderr}")
            return False

    except Exception as e:
        print(f"ADB swipe nie zadziałał: {e}")
        return False

def swipe_up_home_page():
    try:
        width, height = get_screen_size_adb()

        # Środek ekranu jako punkt startowy
        start_x = width // 2
        start_y = int(height * 0.8)  # 80% wysokości ekranu (dół)

        # Punkt końcowy (góra)
        end_x = width // 2
        end_y = int(height * 0.3)  # 20% wysokości ekranu (góra)

        # Czas trwania swipe w ms
        duration = 300

        # Komenda ADB swipe
        cmd = ['adb', 'shell', 'input', 'swipe',
               str(start_x), str(start_y), str(end_x), str(end_y), str(duration)]

        print(f"ADB swipe: {start_x},{start_y} -> {end_x},{end_y}")

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("✓ ADB swipe wykonany pomyślnie")
            time.sleep(0.5)
            return True
        else:
            print(f"✗ ADB swipe błąd: {result.stderr}")
            return False

    except Exception as e:
        print(f"ADB swipe nie zadziałał: {e}")
        return False

# ==================== FUNKCJE DOTYCZĄCE INICJALIZACJI I NAWIGACJI ====================
def get_username_from_profile():
    try:
        profile_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@resource-id='com.instagram.android:id/tab_avatar']"))
        )
        profile_button.click()
        time.sleep(random.uniform(0.35, 0.5))
        profile_button.click()
        print(f"{BLUE}[INFO] Kliknięto przycisk profilu.{RESET}")
        username_elem = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[@resource-id='com.instagram.android:id/action_bar_large_title_auto_size']"))
        )
        username_text = username_elem.text.strip()
        print(f"{BLUE}[INFO] Wczytano username z profilu: {username_text}{RESET}")
        return username_text
    except Exception as e:
        print(f"{RED}[ERROR] Nie udało się pobrać username z profilu: {e}{RESET}")
        return None

def initialize_username():
    username_text = get_username_from_profile()
    if username_text:
        global USERNAME, TARGET_USERS_FILE
        USERNAME = username_text
        init_account_directories(USERNAME)
        TARGET_USERS_FILE = os.path.join(BASE_DIR, USERNAME, "target_accounts_for_followers.txt")
        if not os.path.exists(TARGET_USERS_FILE):
            open(TARGET_USERS_FILE, "w", encoding="utf-8").close()
        return USERNAME
    return None

def open_profile(username):
    try:
        search_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, SEARCH_TAB_SELECTOR))
        )
        search_tab.click()
        time.sleep(random.uniform(0.35, 0.5))
        search_tab.click()
        print(f"{BLUE}[INFO] Kliknięto przycisk wyszukiwania.{RESET}")
        time.sleep(random.uniform(10, 12))
        search_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, SEARCH_FIELD_SELECTOR))
        )
        search_field.click()
        search_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, SEARCH_FIELD_SELECTOR))
        )
        search_field.send_keys(username)
        time.sleep(random.uniform(0.05, 0.1))
        print(f"{BLUE}[INFO] Wpisano username: {username}.{RESET}")
        time.sleep(random.uniform(4, 6))
        first_result = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, FIRST_RESULT_SELECTOR))
        )
        first_result.click()
        print(f"{BLUE}[INFO] Kliknięto pierwszy wynik wyszukiwania dla {username}.{RESET}")
        sleep_random(LOAD_PROFILE_WAIT_RANGE, f"(po otwarciu profilu {username} przez wyszukiwanie)")
    except Exception as e:
        print(f"{RED}[ERROR] Nie udało się otworzyć profilu {username} przez wyszukiwanie: {e}{RESET}")

def open_followers_popup(target):
    open_profile(target)
    try:
        followers_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, MOBILE_FOLLOWERS_BUTTON_SELECTOR))
        )
        followers_button.click()
        sleep_random(FOLLOWERS_CLICK_WAIT_RANGE, "(po kliknięciu followers)")
        followers_list = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, MOBILE_FOLLOWERS_LIST_XPATH))
        )
        return followers_list
    except Exception as e:
        # spróbuj ponownie po krótkim odczekaniu
        print(f"[WARN] open_followers_popup: {e}, ponawiam...")
        driver.activate_app("com.instagram.android")
        sleep_random((2,4), "(ponowne uruchomienie Instagrama przed followers)")
        return open_followers_popup(target)


def init_account_directories(username):
    account_dir = os.path.join(BASE_DIR, username)
    Path(account_dir).mkdir(parents=True, exist_ok=True)
    global TARGET_USERS_FILE
    TARGET_USERS_FILE = os.path.join(account_dir, "target_accounts_for_followers.txt")
    if not os.path.exists(TARGET_USERS_FILE):
        open(TARGET_USERS_FILE, "w", encoding="utf-8").close()
    global ALREADY_FOLLOWED_FILE, followed_file_set, already_followed
    ALREADY_FOLLOWED_FILE = os.path.join(account_dir, "already_followed.txt")
    if not os.path.exists(ALREADY_FOLLOWED_FILE):
        open(ALREADY_FOLLOWED_FILE, "w", encoding="utf-8").close()
    with open(ALREADY_FOLLOWED_FILE, "r", encoding="utf-8") as f:
        followed_file_set = set(line.strip() for line in f if line.strip())
    already_followed = set()
    account_file = os.path.join(account_dir, "total_followed.json")
    if not os.path.exists(account_file):
        with open(account_file, "w", encoding="utf-8") as f:
            json.dump({"total_followed": 0}, f)
        print(f"{BLUE}[INFO] Utworzono plik {account_file} z total_followed = 0.{RESET}")

def get_already_followed_filename(username):
    account_dir = os.path.join(BASE_DIR, username)
    Path(account_dir).mkdir(parents=True, exist_ok=True)
    return os.path.join(account_dir, "already_followed.txt")

def get_account_filename(username):
    account_dir = os.path.join(BASE_DIR, username)
    return os.path.join(account_dir, "total_followed.json")

def load_account_variables(username):
    filename = get_account_filename(username)
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            total_followed = data.get("total_followed", 0)
            print(f"[INFO] Wczytano total_followed = {total_followed} z pliku {filename}.")
            return total_followed
        except Exception as e:
            print(f"{RED}[BŁĄD] Problem przy wczytywaniu pliku {filename}: {e}{RESET}")
    return 0

def update_account_variables(username, total_followed):
    filename = get_account_filename(username)
    data = {"total_followed": total_followed}
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f)
        print(f"[INFO] Zaktualizowano total_followed = {total_followed} w pliku {filename}.")
    except Exception as e:
        print(f"{RED}[BŁĄD] Nie udało się zapisać pliku {filename}: {e}{RESET}")

def convert_polish_to_english(s):
    mapping = {'ą': 'a', 'ę': 'e', 'ó': 'o', 'ś': 's', 'ż': 'z', 'ź': 'z', 'ć': 'c', 'ń': 'n'}
    return "".join(mapping.get(char.lower(), char) for char in s)

def clean_nick(nick):
    return re.sub(r'[^A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]', '', nick).lower()

def has_polish_firstname_in_nick(nick):
    cleaned = clean_nick(nick)
    english_nick = convert_polish_to_english(cleaned)
    return any(name in english_nick for name in polish_firstnames)

def get_polish_firstname(nick):
    cleaned = clean_nick(nick)
    english_nick = convert_polish_to_english(cleaned)
    for name in polish_firstnames:
        if name in english_nick:
            return name
    return None

def get_polish_female_firstname(nick):
    cleaned = clean_nick(nick)
    english_nick = convert_polish_to_english(cleaned)
    for name in polish_female_firstnames:
        if name in english_nick:
            return name
    return None

def update_last_action_time():
    global last_action_time
    last_action_time = time.time()

# ==================== FUNKCJE OBSŁUGUJĄCE APLIKACJĘ INSTAGRAM ====================
def login_instagram():
    try:
        driver.activate_app("com.instagram.android")
        if STAY_LOGGED_IN:
            print("[INFO] Używam zapisanej sesji – pomijam procedurę logowania.")
            init_account_directories(USERNAME)
            return
        print("[INFO] Rozpoczynam procedurę logowania...")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, MOBILE_LOGIN_USERNAME_SELECTOR))
        )
        driver.find_element(By.XPATH, MOBILE_LOGIN_USERNAME_SELECTOR).send_keys(USERNAME)
        driver.find_element(By.XPATH, MOBILE_LOGIN_PASSWORD_SELECTOR).send_keys(PASSWORD)
        login_button = driver.find_element(By.XPATH, MOBILE_LOGIN_BUTTON_SELECTOR)
        login_button.click()
        sleep_random(LOGIN_LOAD_WAIT_RANGE, "(po kliknięciu przycisku logowania)")
        try:
            not_now = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, MOBILE_NOT_NOW_BUTTON_SELECTOR))
            )
            not_now.click()
            print("[INFO] Kliknięto 'Not Now'.")
        except Exception as e:
            print(f"{YELLOW}[INFO] Popup 'Not Now' nie został znaleziony: {e}{RESET}")
        sleep_random(AFTER_LOGIN_WAIT_RANGE, "(po zalogowaniu)")
        print("[INFO] Zalogowano pomyślnie.")
        init_account_directories(USERNAME)
    except Exception as e:
        print(f"{RED}[BŁĄD] Problem podczas logowania: {e}{RESET}")
        driver.save_screenshot("login_error.png")
        sys.exit(1)

def get_next_candidate(scroll_container, skip_initial_refresh=False):
    candidates, finished = get_followers_from_open_popup(
        scroll_container,
        needed_count=1,
        skip_initial_refresh=skip_initial_refresh
    )
    if candidates:
        return candidates[0], finished
    return None, finished

def ensure_active_session():
    global driver
    try:
        _ = driver.current_activity
    except Exception as e:
        print(f"{YELLOW}[INFO] Driver session nieaktywna: {e}. Re-inicjalizuję drivera...{RESET}")
        driver = initialize_driver(EMULATOR_NAME, EMULATOR_UDID)

def refresh_scroll_container():
    global driver, global_last_index, appium_error_time
    try:
        if not hasattr(driver, "session_id") or not driver.session_id:
            print(f"{YELLOW}[INFO] Sesja została zakończona – ponowna inicjalizacja drivera...{RESET}")
            driver = initialize_driver(EMULATOR_NAME, EMULATOR_UDID)
        _ = driver.current_activity
        new_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, MOBILE_FOLLOWERS_LIST_XPATH))
        )
        global_last_index = 0
        sleep_random((1.5, 2.2), "na odświeżenie kontenera")
        print(f"{BLUE}[INFO] Odświeżono kontener followersów.{RESET}")
        appium_error_time = None
        return new_container
    except (NoSuchDriverException, Exception) as e:
        print(f"{RED}[ERROR] Nie udało się odświeżyć kontenera followersów: {e}{RESET}")
        try:
            driver = initialize_driver(EMULATOR_NAME, EMULATOR_UDID)
            new_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, MOBILE_FOLLOWERS_LIST_XPATH))
            )
            global_last_index = 0
            appium_error_time = None
            return new_container
        except Exception as ex:
            print(f"{RED}[ERROR] Re-inicjalizacja drivera nie powiodła się: {ex}{RESET}")
            sys.exit(1)

def force_refresh_container():
    try:
        main_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@resource-id='com.instagram.android:id/wrapper' and contains(@class, 'android.view.ViewGroup')]"))
        )
        main_tab.click()
        time.sleep(random.uniform(1, 2))
        search_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, SEARCH_TAB_SELECTOR))
        )
        search_tab.click()
        time.sleep(random.uniform(1, 2))
        new_container = refresh_scroll_container()
        print(f"{BLUE}[INFO] Wymuszone odświeżenie kontenera wykonane.{RESET}")
        return new_container
    except Exception as e:
        print(f"{RED}[ERROR] Force refresh container failed: {e}{RESET}")
        return refresh_scroll_container()

def get_followers_from_open_popup(scroll_container, needed_count, skip_initial_refresh=False):
    global global_last_index, current_target, driver, global_followers_start_wait
    xpath_selector = ("//*[@resource-id='com.instagram.android:id/follow_list_container' or "
                      "@resource-id='com.instagram.android:id/see_more_button' or "
                      "@resource-id='com.instagram.android:id/row_header_textview']")
    if global_followers_start_wait is None:
        global_followers_start_wait = time.time()
    start_wait_local = global_followers_start_wait
    was_refreshed = False
    try:
        rows = scroll_container.find_elements(By.XPATH, xpath_selector)
    except StaleElementReferenceException:
        print(f"{YELLOW}[INFO] Kontener followersów jest nieaktualny – odświeżam go...{RESET}")
        scroll_container = refresh_scroll_container()
        was_refreshed = True
        rows = scroll_container.find_elements(By.XPATH, xpath_selector)
    if not was_refreshed and not skip_initial_refresh:
        scroll_container = refresh_scroll_container()
        rows = scroll_container.find_elements(By.XPATH, xpath_selector)
    
    if (time.time() - global_followers_start_wait) > 15:
        print(f"{YELLOW}[INFO] Oczekiwanie na nowe elementy trwa ponad 15 sekund. Wymuszam odświeżenie kontenera...{RESET}")
        scroll_container = force_refresh_container()
        global_followers_start_wait = time.time()
        rows = scroll_container.find_elements(By.XPATH, xpath_selector)
        
    if len(rows) <= global_last_index and (time.time() - global_followers_start_wait) > 30:
        print(f"{YELLOW}[INFO] Odczekano ponad 30 sekund na nowy element. Wykonuję czyszczenie logcat i restart ADB/Appium...{RESET}")
        clear_logcat_buffer(EMULATOR_UDID)
        driver, _ = restart_adb_appium(EMULATOR_NAME, EMULATOR_UDID)
        global_last_index = 0
        global_followers_start_wait = time.time()
        rows = scroll_container.find_elements(By.XPATH, xpath_selector)
        
    if len(rows) <= global_last_index and (time.time() - global_followers_start_wait) > 10:
        print(f"{YELLOW}[INFO] Przez 10 sekund nie było nowych elementów. Wykonuję mały swipe...{RESET}")
        small_swipe()
        time.sleep(3)
        scroll_container = refresh_scroll_container()
        rows = scroll_container.find_elements(By.XPATH, xpath_selector)
        if len(rows) <= global_last_index:
            print(f"{YELLOW}[INFO] Po małym swipie nadal brak nowych kont. Oznaczam target jako DONE.{RESET}")
            mark_target_done(current_target)
            global_followers_start_wait = None
            return ([], True)
        global_followers_start_wait = time.time()
    batch_users = []
    for i in range(global_last_index, len(rows)):
        row = rows[i]
        if not row.is_displayed():
            continue
        try:
            resource_id = row.get_attribute("resource-id")
            if resource_id == "com.instagram.android:id/see_more_button":
                print(f"{YELLOW}[INFO] Wiersz zawiera przycisk 'See more'. Klikam go...{RESET}")
                row.click()
                sleep_random((2, 4), "(czekam po kliknięciu See more)")
                scroll_container = refresh_scroll_container()
                rows = scroll_container.find_elements(By.XPATH, xpath_selector)
                global_followers_start_wait = time.time()
                global_last_index = 0
                return get_followers_from_open_popup(scroll_container, needed_count, skip_initial_refresh=True)
            elif resource_id == "com.instagram.android:id/row_header_textview":
                text = row.text.strip()
                if text == "Suggested for you":
                    print(f"{YELLOW}[INFO] Wiersz zawiera etykietę 'Suggested for you'. Oznaczam target jako DONE.{RESET}")
                    mark_target_done(current_target)
                    return (batch_users, True)
                continue
            else:
                primary_elements = row.find_elements(By.XPATH, ".//*[@resource-id='com.instagram.android:id/follow_list_username']")
                secondary_elements = row.find_elements(By.XPATH, ".//*[@resource-id='com.instagram.android:id/follow_list_subtitle']")
                if not primary_elements:
                    continue
                primary_nick = primary_elements[0].text.strip()
                secondary_nick = secondary_elements[0].text.strip() if secondary_elements else ""
                button = row.find_element(By.XPATH, MOBILE_FOLLOW_BUTTON_ROW_XPATH)
                btn_text = button.text.strip().lower()
                if any(x in btn_text for x in ["following", "requested"]):
                    print(f"{RED}[INFO] Pomijam {primary_nick}, status: \"{btn_text}\"{RESET}")
                    continue
                if primary_nick in followed_file_set:
                    print(f"{RED}[INFO] Pomijam {primary_nick}, już wcześniej zafollowowane (plik){RESET}")
                    continue
                if any(x in btn_text for x in ["follow", "obserwuj"]):
                    male_name = get_polish_firstname(primary_nick)
                    source = "primary"
                    if male_name is None:
                        male_name = get_polish_firstname(secondary_nick)
                        source = "secondary" if male_name else None
                    if male_name is not None:
                        female_name = None
                        if source == "primary":
                            female_name = get_polish_female_firstname(primary_nick)
                        elif source == "secondary":
                            female_name = get_polish_female_firstname(secondary_nick)
                        if female_name is not None:
                            print(f"{YELLOW}[INFO] W {source} nicku {primary_nick} znaleziono żeńskie imię '{female_name}'. Pomijam.{RESET}")
                        else:
                            batch_users.append((primary_nick, row))
                            print(f"{GREEN}[INFO] Dodano {primary_nick} do batcha. Znaleziono męskie imię '{male_name}' w {source} nicku.{RESET}")
                    else:
                        print(f"{YELLOW}[INFO] Nie znaleziono męskiego imienia w nicku {primary_nick}.{RESET}")
        except Exception as e:
            print(f"{YELLOW}[INFO] Błąd przy przetwarzaniu wiersza: {e}{RESET}")
            continue
    global_last_index = len(rows)
    return (batch_users, False)

def like_posts_in_profile():
    try:
        sleep_random(LOAD_PROFILE_WAIT_RANGE, "(po otwarciu profilu przed likeowaniem)")
        posts = driver.find_elements(By.XPATH, MOBILE_PROFILE_POST_BUTTON_SELECTOR)
        num_posts = len(posts)
        print(f"{BLUE}[INFO] Znaleziono {num_posts} postów na profilu.{RESET}")
        if num_posts == 0:
            print(f"{YELLOW}[INFO] Brak postów do polubienia.{RESET}")
            return
        if num_posts > 1:
            num_to_like = random.randint(1, min(2, num_posts))
        else:
            num_to_like = 1
        print(f"{BLUE}[INFO] Wybrano {num_to_like} post(y) do like'owania.{RESET}")
        available_indices = list(range(num_posts))
        chosen_indices = random.sample(available_indices, num_to_like)
        for idx in chosen_indices:
            try:
                posts = driver.find_elements(By.XPATH, MOBILE_PROFILE_POST_BUTTON_SELECTOR)
                if idx >= len(posts):
                    print(f"{YELLOW}[INFO] Indeks {idx} jest poza zakresem dostępnych postów po odświeżeniu.{RESET}")
                    continue
                post = posts[idx]
                post.click()
                print(f"{BLUE}[INFO] Kliknięto post o indeksie {idx}.{RESET}")
                sleep_random(OPEN_POST_WAIT_RANGE, "(po otwarciu posta)")
                like_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, MOBILE_PROFILE_LIKE_BUTTON_SELECTOR))
                )
                tap_element(like_btn)
                print(f"{BLUE}[INFO] Polubiono post o indeksie {idx}.{RESET}")
                sleep_random(LIKE_POST_WAIT_RANGE, "(po likeowaniu)")
                back_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, MOBILE_BACK_BUTTON_SELECTOR))
                )
                back_btn.click()
                print(f"{BLUE}[INFO] Wrócono z posta o indeksie {idx}.{RESET}")
                sleep_random((2, 3), "(po powrocie z posta i odświeżeniu elementów)")
                posts = driver.find_elements(By.XPATH, MOBILE_PROFILE_POST_BUTTON_SELECTOR)
                print(f"{BLUE}[INFO] Odświeżono listę postów po powrocie z posta.{RESET}")
            except Exception as e:
                print(f"{YELLOW}[INFO] Błąd przy próbie like'owania posta o indeksie {idx}: {e}{RESET}")
                try:
                    back_btn = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, MOBILE_BACK_BUTTON_SELECTOR))
                    )
                    back_btn.click()
                    sleep_random((2, 3), "(po powrocie z błędu)")
                except Exception:
                    pass
    except Exception as e:
        print(f"{RED}[BŁĄD] Problem podczas like'owania postów: {e}{RESET}")

def follow_user(candidate):
    allowed = is_current_time_allowed()
    if not allowed:
        wait = seconds_until_next_start()
        dynamic_sleep(wait, "[INFO] Czekam do godzinnego okna")

    # Pierwsze losowanie: Direct vs New Activity
    random_value = random.random()
    use_new_activity = (random_value < 0.4)  # 60% Direct, 40% New Activity
    username, row = candidate
    print(f"[DEBUG] Losowanie dla {username}: random_value={random_value:.3f}, use_new_activity={use_new_activity}")

    if use_new_activity:  # Tryb "New Activity"
        try:
            row.click()
            sleep_random(LOAD_PROFILE_WAIT_RANGE, "(po wejściu w profil)")
            
            # Drugie losowanie: od razu follow czy polubić posty
            follow_immediately = (random.random() < 0.5)  # 50% na od razu follow, 50% na polubienie postów
            print(f"[DEBUG] New Activity dla {username}: follow_immediately={follow_immediately}")
            
            if not follow_immediately:  # Najpierw polub posty
                like_posts_in_profile()
            
            # Follow z profilu
            profile_follow = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, MOBILE_PROFILE_FOLLOW_BUTTON_SELECTOR))
            )
            btn_text = profile_follow.text.strip().lower()
            if any(x in btn_text for x in ["following", "requested"]):
                print(f"{RED}[INFO] (New Activity) Pomijam {username}, status: \"{btn_text}\"{RESET}")
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, MOBILE_BACK_BUTTON_SELECTOR))
                ).click()
                return False
            if any(x in btn_text for x in ["follow", "obserwuj"]):
                profile_follow.click()
                print(f"{BLUE}[INFO] (New Activity) Kliknięto Follow dla {username}.{RESET}")
                sleep_random(FOLLOW_ACTION_WAIT_RANGE, "(po follow)")
                try:
                    new_text = profile_follow.text.strip().lower()
                except Exception:
                    new_text = ""
                if new_text in ["follow", "obserwuj"]:
                    print(f"{RED}[BŁĄD] (New Activity) Follow nie powiódł się – prawdopodobnie rate limit{RESET}")
                    WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, MOBILE_BACK_BUTTON_SELECTOR))
                    ).click()
                    sys.exit(1)
                else:
                    print(f"{BLUE}[INFO] (New Activity) Zaobserwowano {username}.{RESET}")
                    already_followed.add(username)
                    with open(get_already_followed_filename(USERNAME), "a", encoding="utf-8") as f:
                        f.write(username + "\n")
                    followed_file_set.add(username)
                    WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, MOBILE_BACK_BUTTON_SELECTOR))
                    ).click()
                    return True
            print(f"[INFO] (New Activity) Nieobsługiwany przycisk '{btn_text}' dla {username}")
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, MOBILE_BACK_BUTTON_SELECTOR))
            ).click()
            return False
        except TimeoutException:
            print(f"{YELLOW}[INFO] (New Activity) Brak przycisku Follow dla {username}{RESET}")
            try:
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, MOBILE_BACK_BUTTON_SELECTOR))
                ).click()
            except Exception:
                pass
            return False
        except Exception as e:
            print(f"{RED}[BŁĄD] (New Activity) Problem przy follow dla {username}: {e}{RESET}")
            try:
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, MOBILE_BACK_BUTTON_SELECTOR))
                ).click()
            except Exception:
                pass
            return False
    else:  # Tryb "Direct"
        try:
            follow_button = row.find_element(By.XPATH, MOBILE_FOLLOW_BUTTON_ROW_XPATH)
            btn_text = follow_button.text.strip().lower()
            if any(x in btn_text for x in ["following", "requested"]):
                print(f"{RED}[INFO] (Direct) Pomijam {username}, status: \"{btn_text}\"{RESET}")
                return False
            if any(x in btn_text for x in ["follow", "obserwuj"]):
                follow_button.click()
                print(f"{BLUE}[INFO] (Direct) Kliknięto Follow dla {username}.{RESET}")
                sleep_random(FOLLOW_ACTION_WAIT_RANGE, "(po follow)")
                try:
                    new_text = follow_button.text.strip().lower()
                except Exception:
                    new_text = ""
                if new_text in ["follow", "obserwuj"]:
                    print(f"{RED}[BŁĄD] (Direct) Follow nie powiódł się – prawdopodobnie rate limit{RESET}")
                    sys.exit(1)
                else:
                    print(f"{BLUE}[INFO] (Direct) Zaobserwowano {username}.{RESET}")
                    already_followed.add(username)
                    with open(get_already_followed_filename(USERNAME), "a", encoding="utf-8") as f:
                        f.write(username + "\n")
                    followed_file_set.add(username)
                    return True
            print(f"{RED}[INFO] (Direct) Nieobsługiwany przycisk '{btn_text}' dla {username}{RESET}")
            sys.exit(1)
        except TimeoutException:
            print(f"{YELLOW}[INFO] (Direct) Brak przycisku Follow dla {username}{RESET}")
            return False
        except Exception as e:
            print(f"{RED}[BŁĄD] (Direct) Problem przy follow dla {username}: {e}{RESET}")
            return False

def mark_target_done(target):
    try:
        with open(TARGET_USERS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(TARGET_USERS_FILE, "w", encoding="utf-8") as f:
            for line in lines:
                parts = line.strip().split()
                if parts and parts[0] == target and "DONE" not in parts:
                    f.write(f"{target} DONE\n")
                else:
                    f.write(line)
        print(f"{YELLOW}[INFO] Oznaczono target '{target}' jako DONE.{RESET}")
    except Exception as e:
        print(f"{RED}[BŁĄD] Nie udało się oznaczyć targetu {target} jako DONE: {e}{RESET}")

def is_current_time_allowed():
    now = datetime.datetime.now()
    # podstawowe daty graniczne z offsetami
    base_start = now.replace(hour=BOT_START_TIME, minute=0, second=0, microsecond=0) \
               + datetime.timedelta(minutes=START_OFFSET)
    base_end   = now.replace(hour=BOT_END_TIME,   minute=0, second=0, microsecond=0) \
               + datetime.timedelta(minutes=END_OFFSET)

    if base_start <= base_end:
        # proste okno w ciągu dnia
        start_dt, end_dt = base_start, base_end
    else:
        # okno przechodzi przez północ
        if now >= base_start:
            # jesteśmy między base_start (dziś) a północą → end = jutro
            start_dt = base_start
            end_dt   = base_end + datetime.timedelta(days=1)
        else:
            # jesteśmy przed base_end (dziś) → start = wczoraj
            start_dt = base_start - datetime.timedelta(days=1)
            end_dt   = base_end

    return start_dt <= now < end_dt


def seconds_until_next_start():
    now = datetime.datetime.now()
    # kiedy przypada najbliższy start z offsetem
    base_start = now.replace(hour=BOT_START_TIME, minute=0, second=0, microsecond=0) \
               + datetime.timedelta(minutes=START_OFFSET)

    if is_current_time_allowed():
        return 0.0

    # jeśli teraz < base_start → czekamy do tej samej daty
    if now < base_start:
        next_start = base_start
    else:
        # inaczej do jutra o tej samej godzinie+offset
        next_start = base_start + datetime.timedelta(days=1)

    return (next_start - now).total_seconds()

def handle_main_feed_page(wait_time):
    # upewnij się, że driver działa
    ensure_active_session()

    try:
        main_feed_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[@resource-id='com.instagram.android:id/wrapper' and contains(@class, 'android.view.ViewGroup')]"
            ))
        )
        main_feed_btn.click()
        time.sleep(1)
        main_feed_btn.click()
    except StaleElementReferenceException:
        print("[INFO] main_feed_btn stale – ponawiam przełączanie na feed")
        return handle_main_feed_page(wait_time)
    except Exception as e:
        print(f"[ERROR] Błąd przełączania na główny feed: {e}")
        return

    sleep_random(MAIN_PAGE_AFTER_OPEN_WAIT_RANGE, "(po otwarciu feedu)")
    start_time = time.time()

    while True:
        if stop_bot:
            break
        if not is_current_time_allowed():
            global bot_mode, last_wait_mode, last_wait_remaining
            bot_mode = "waiting"
            last_wait_mode = "feed"
            elapsed = time.time() - start_time
            last_wait_remaining = max(0, wait_time - elapsed)
            return

        elapsed = time.time() - start_time
        remaining = wait_time - elapsed
        if remaining <= 0:
            break

        swipe_up_home_page()
        update_last_action_time()
        print(f"[INFO] Swipe w feedzie. Pozostało: {format_duration(remaining)}.")
        sleep_random((25, 35), "przed następnym scrollowaniem")

    print("[INFO] Zakończono feed – wracam do wyszukiwania.")


def handle_reels_page(wait_time):
    ensure_active_session()

    try:
        reels_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, MOBILE_REELS_TAB_SELECTOR))
        )
        reels_tab.click()
    except StaleElementReferenceException:
        print("[INFO] reels_tab stale – ponawiam przełączanie na reels")
        return handle_reels_page(wait_time)
    except Exception as e:
        print(f"[ERROR] Błąd przełączania do reels: {e}")
        return

    sleep_random(MAIN_PAGE_AFTER_OPEN_WAIT_RANGE, "(po otwarciu reels)")
    start_time = time.time()

    while True:
        if stop_bot:
            break
        if not is_current_time_allowed():
            global bot_mode, last_wait_mode, last_wait_remaining
            bot_mode = "waiting"
            last_wait_mode = "reels"
            elapsed = time.time() - start_time
            last_wait_remaining = max(0, wait_time - elapsed)
            return

        elapsed = time.time() - start_time
        remaining = wait_time - elapsed
        if remaining <= 0:
            break

        try:
            suggested_elem = driver.find_element(
                By.XPATH,
                "//*[@resource-id='com.instagram.android:id/title' and @text='Suggested for you']"
            )
            if suggested_elem.is_displayed():
                print(f"{YELLOW}[INFO] Wykryto 'Suggested for you'.{RESET}")
                sleep_random((5, 10), "(czekam z powodu 'Suggested for you')")
                swipe_up_reels()
                update_last_action_time()
                continue
        except Exception:
            pass

        cycle_time = random.uniform(20.0, 40.0)
        if cycle_time > remaining:
            cycle_time = remaining
        like_offset = random.uniform(6.0, 12.0)
        if like_offset > cycle_time:
            like_offset = 0.0

        first_sleep = cycle_time - like_offset
        if first_sleep > 0:
            sleep_random((first_sleep, first_sleep), "(przed lajkowaniem reels)")
        if like_offset > 0 and random.random() < 0.07:
            try:
                print(f"{BLUE}[INFO] Próba polubienia reels.{RESET}")
                like_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, MOBILE_REELS_LIKE_BUTTON_SELECTOR))
                )
                tap_element(like_button)
                print(f"{BLUE}[INFO] Polubiono reel.{RESET}")
                update_last_action_time()
            except Exception as e:
                print(f"{YELLOW}[INFO] Błąd przy likeowaniu reels: {e}{RESET}")
        if like_offset > 0:
            sleep_random((like_offset, like_offset), "(po lajkowaniu reels)")

        swipe_up_reels()
        update_last_action_time()
        print(f"{BLUE}[INFO] Swipe w reels. Pozostało: {format_duration(wait_time - (time.time() - start_time))}.{RESET}")

    print(f"{BLUE}[INFO] Zakończono reels – wracam do wyszukiwania.{RESET}")


def pause_bot_until_allowed():
    global driver, bot_mode, last_wait_mode, last_wait_remaining, current_target
    global START_OFFSET, END_OFFSET

    # 0) Losujemy nowy offset dla kolejnej przerwy
    START_OFFSET = random.randint(*BOT_ACTIVE_TIME_OFFSET_RANGE)
    END_OFFSET   = random.randint(*BOT_ACTIVE_TIME_OFFSET_RANGE)

    # 1) Zamykamy Instagram
    try:
        driver.terminate_app("com.instagram.android")
        print("[INFO] Bot poza oknem – aplikacja Instagram zamknięta.")
    except Exception as e:
        print(f"[WARN] Nie udało się zamknąć Instagrama: {e}")

    # 2) Czekamy do najbliższego startu z offsetem
    wait_secs = seconds_until_next_start()
    print(f"[INFO] Czekam {format_duration(wait_secs)} do startu okna pracy (offset: {START_OFFSET} min).")
    dynamic_sleep(wait_secs, "[INFO] Oczekiwanie do start time")

    # 3) Po powrocie – wznawiamy Instagrama
    try:
        driver.activate_app("com.instagram.android")
        print("[INFO] Start window – uruchomiono Instagram.")
    except Exception as e:
        print(f"[WARN] Nie udało się uruchomić Instagrama: {e}")

    # 4) Przywracamy stan sprzed pauzy
    if bot_mode == "followers" and current_target:
        print(f"[INFO] Wznawiam follow na profilu {current_target}.")
        # otwiera profil i popup followers
        scroll_container = open_followers_popup(current_target)

    elif bot_mode == "waiting":
        print(f"[INFO] Wznawiam tryb oczekiwania: {last_wait_mode}, pozostało {format_duration(last_wait_remaining)}.")
        if last_wait_mode == "feed":
            handle_main_feed_page(last_wait_remaining)
        else:
            handle_reels_page(last_wait_remaining)

        # po zakończeniu oczekiwania znów wracamy do followersów
        if current_target:
            print(f"[INFO] Po oczekiwaniu wracam do follow profilu {current_target}.")
            scroll_container = open_followers_popup(current_target)



def run_bot():
    global session_start_time, current_target, global_last_index, driver, stop_bot, current_hour_followed, bot_mode, last_wait_mode, last_wait_remaining
    print(f"[INFO] Ustawiony zakres pracy bota: {BOT_START_TIME}:00 - {BOT_END_TIME}:00{' (przez noc)' if BOT_START_TIME > BOT_END_TIME else ''}")
    while True:
        try:
            if not is_current_time_allowed():
                bot_mode = bot_mode or "followers"
                last_wait_mode = None
                print(f"{YELLOW}[INFO] Poza godzinami pracy – pauzuję do {BOT_START_TIME}:00.{RESET}")
                pause_bot_until_allowed()
                continue

            if session_start_time is None or current_target is None:
                bot_mode = "followers"
                login_instagram()
                sleep_random(AFTER_LOGIN_WAIT_RANGE, "(po zalogowaniu)")
                profile_username = get_username_from_profile()
                if profile_username:
                    global USERNAME, TARGET_USERS_FILE
                    USERNAME = profile_username
                    init_account_directories(USERNAME)
                    TARGET_USERS_FILE = os.path.join(BASE_DIR, USERNAME, "target_accounts_for_followers.txt")
                    if not os.path.exists(TARGET_USERS_FILE):
                        open(TARGET_USERS_FILE, "w", encoding="utf-8").close()
                else:
                    print(f"{RED}[ERROR] Nie udało się pobrać username z profilu.{RESET}")
                    sys.exit(1)
                session_start_time = time.time()
                current_hour_followed = 0
                with open(TARGET_USERS_FILE, "r", encoding="utf-8") as f:
                    available_targets = [l.strip() for l in f if l.strip() and not l.strip().endswith("DONE")]
                if not available_targets:
                    print(f"{RED}[BŁĄD] Brak dostępnych targetów.{RESET}")
                    sys.exit(1)
                current_target = random.choice(available_targets)

            bot_mode = "followers"
            print(f"[INFO] Wybrano target: {current_target}")
            scroll_container = open_followers_popup(current_target)
            total_followed = load_account_variables(USERNAME)
            hourly_target = random.randint(*HOURLY_TARGET_RANGE)
            print(f"[INFO] Ustalono hourly target: {hourly_target}")

            # follow loop
            while total_followed < MAX_TO_FOLLOW and current_hour_followed < hourly_target:
                if stop_bot:
                    print(f"{YELLOW}[INFO] Przerwanie sesji follow.{RESET}")
                    break
                if not is_current_time_allowed():
                    print(f"{YELLOW}[INFO] Godziny pracy minęły – pauzuję do {BOT_START_TIME}:00.{RESET}")
                    pause_bot_until_allowed()

                # batch
                batch_candidate = random.randint(BATCH_SIZE_MIN, BATCH_SIZE_MAX)
                remaining = hourly_target - current_hour_followed
                batch_size = min(batch_candidate, remaining)
                print(f"[BATCH] Partia size {batch_size}.")
                processed = 0

                while processed < batch_size and total_followed < MAX_TO_FOLLOW and current_hour_followed < hourly_target:
                    if stop_bot:
                        break
                    if not is_current_time_allowed():
                        bot_mode = "waiting"
                        last_wait_mode = random.choice(["feed", "reels"])
                        last_wait_remaining = 5
                        pause_bot_until_allowed()

                    candidate, finished = get_next_candidate(scroll_container)
                    if finished:
                        print(f"{YELLOW}[INFO] Target {current_target} DONE. Wybieram nowy.{RESET}")
                        with open(TARGET_USERS_FILE, "r", encoding="utf-8") as f:
                            avail = [l.strip() for l in f if l.strip() and not l.strip().endswith("DONE")]
                        if not avail:
                            print(f"{RED}[BŁĄD] Brak targetów.{RESET}")
                            sys.exit(1)
                        current_target = random.choice(avail)
                        scroll_container = open_followers_popup(current_target)
                        candidate, finished = get_next_candidate(scroll_container)
                        if candidate is None:
                            continue

                    if candidate is None:
                        swipe_up(); sleep_random(WAIT_AFTER_SCROLL_RANGE, "(swipe)")
                        continue

                    user = candidate[0]
                    if user in already_followed or user in followed_file_set:
                        processed += 1
                        continue

                    print(f"[INFO] Follow {user}")
                    if follow_user(candidate):
                        total_followed += 1
                        current_hour_followed += 1
                        update_account_variables(USERNAME, total_followed)
                    processed += 1
                    if processed < batch_size:
                        sleep_random(FOLLOW_ACTION_WAIT_RANGE, "(po follow)")
                        scroll_container = refresh_scroll_container()
                        global_last_index = 0

                print(f"[BATCH END] Followed {total_followed} total, this hour {current_hour_followed}/{hourly_target}.")

                # jeśli nadal w godzinie, tylko czekaj na next batch
                if current_hour_followed < hourly_target and total_followed < MAX_TO_FOLLOW:
                    wait_secs = ((base_dynamic_wait + random.uniform(*DYNAMIC_WAIT_OFFSET_RANGE)) / 2.0)
                    dynamic_sleep(wait_secs, "[INFO] Oczekiwanie na next batch")
                    global_last_index = 0

            # jeśli osiągnięto hourly target
            if current_hour_followed >= hourly_target and total_followed < MAX_TO_FOLLOW:
                elapsed = time.time() - session_start_time
                remaining = max(0, 3600 - elapsed)
                mode = random.choices(["reels", "feed"], weights=[0.65,0.35])[0]
                print(f"[INFO] Hourly target osiągnięty – {mode} na {format_duration(remaining)}.")
                if mode == "feed":
                    handle_main_feed_page(remaining)
                else:
                    handle_reels_page(remaining)

                # nowy target
                with open(TARGET_USERS_FILE, "r", encoding="utf-8") as f:
                    avail = [l.strip() for l in f if l.strip() and not l.strip().endswith("DONE")]
                if not avail:
                    print(f"{RED}[BŁĄD] Brak targetów po sesji.{RESET}")
                    sys.exit(1)
                current_target = random.choice(avail)
                print(f"[INFO] Nowy target: {current_target}")
                session_start_time = time.time()
                current_hour_followed = 0
                global_last_index = 0
                continue

            # po godzinie lub max_to_follow
            print(f"[INFO] Sesja zakończona – total follow: {total_followed}.")
            if not is_current_time_allowed():
                print(f"{YELLOW}[INFO] Poza window – pauza do {BOT_START_TIME}:00.{RESET}")
                pause_bot_until_allowed()
            else:
                interval = random.uniform(*SESSION_OFFSET_RANGE_SHORT)
                print(f"{YELLOW}[INFO] Czekam {format_duration(interval)} na next hour.{RESET}")
                dynamic_sleep(interval, "[INFO] Waiting next session")

            # nowy start
            with open(TARGET_USERS_FILE, "r", encoding="utf-8") as f:
                avail = [l.strip() for l in f if l.strip() and not l.strip().endswith("DONE")]
            if avail:
                current_target = random.choice(avail)
                global_last_index = 0
                print(f"{YELLOW}[INFO] Nowy target: {current_target}{RESET}")

            update_account_variables(USERNAME, total_followed)
            session_start_time = None
            current_hour_followed = 0

        except RateLimitException as rle:
            print(f"{RED}[BŁĄD] {rle}{RESET}")
            input("Enter to exit...")
        except Exception as e:
            print(f"{RED}[BŁĄD] Krytyczny: {e}{RESET}")
            input("Enter to exit...")


# ==================== FUNKCJE DOTYCZĄCE RESTARTU ADB (ZAMIAST EMULATORA I APPPIUM) ====================
def clear_logcat_buffer(emulator_udid):
    try:
        os.system(f"adb -s {emulator_udid} logcat -c")
        print(f"[INFO] Wyczyszczono bufor logcat dla urządzenia {emulator_udid}.")
    except Exception as e:
        print(f"[WARNING] Nie udało się wyczyścić logcat dla {emulator_udid}: {e}")

def restart_adb_appium(emulator_name, emulator_udid):
    print(f"[INFO] Wymuszam odświeżenie aktualnego kontenera")
    new_container = refresh_scroll_container()
    time.sleep(2)
    return driver, None

def start_appium_server():
    cmd = 'appium server --log-level error --default-capabilities "{\\"appium:newCommandTimeout\\":864000}"'
    print("[INFO] Uruchamiam Appium Server z ograniczonym logowaniem i newCommandTimeout=864000...")
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    print("[INFO] Serwer Appium powinien być już gotowy.")
    return process

def initialize_driver(emulator_name, emulator_udid):
    options = UiAutomator2Options()
    options.platformName = "Android"
    options.deviceName = emulator_name
    options.udid = emulator_udid
    options.appPackage = "com.instagram.android"
    options.appActivity = "com.instagram.mainactivity.MainActivity"
    options.noReset = STAY_LOGGED_IN
    driver = webdriver.Remote("http://127.0.0.1:4723", options=options)
    return driver

# ==================== NOWY WĄTEK MONITORUJĄCY APPPIUM I ADB LOGCAT ====================
def monitor_appium(emulator_udid):
    global driver, forced_sleep, appium_error_time
    while True:
        time.sleep(20)
        if forced_sleep:
            continue
        if not globals().get("driver"):
            continue
        try:
            _ = driver.current_activity
            proc = subprocess.Popen(["adb", "-s", emulator_udid, "logcat", "-d", "-t", "60"], stdout=subprocess.PIPE)
            output, _ = proc.communicate()
            logs = output.decode("utf-8", errors="ignore")
            if "frozen process" in logs:
                print(f"{YELLOW}[MONITOR] Wykryto potencjalnie krytyczne komunikaty w logach adb dla urządzenia {emulator_udid}.{RESET}")
                if appium_error_time is None:
                    appium_error_time = time.time()
                elif time.time() - appium_error_time > 60:
                    print(f"{RED}[MONITOR] Appium zdaje się być zawieszone. Restartuję serwer ADB dla urządzenia {emulator_udid}...{RESET}")
                    restart_adb_appium(EMULATOR_NAME, EMULATOR_UDID)
                    start_appium_server()
                    appium_error_time = None
            else:
                appium_error_time = None
        except Exception as e:
            print(f"{YELLOW}[MONITOR] Błąd przy pingowaniu Appium dla urządzenia {emulator_udid}: {e}{RESET}")
            if appium_error_time is None:
                appium_error_time = time.time()
            elif time.time() - appium_error_time > 30:
                print(f"{RED}[MONITOR] Brak odpowiedzi od Appium dla urządzenia {emulator_udid} przez 30s. Restartuję serwer ADB...{RESET}")
                restart_adb_appium(EMULATOR_NAME, EMULATOR_UDID)
                start_appium_server()
                appium_error_time = None

def wait_for_home_screen(max_wait=240, emulator_udid=None):
    start = time.time()
    print(f"[INFO] Czekam aż emulator {emulator_udid} przejdzie do ekranu głównego...")
    while time.time() - start < max_wait:
        output = os.popen(f"adb -s {emulator_udid} shell getprop sys.boot_completed").read().strip()
        if output == "1":
            return True
        time.sleep(2)
    return False

def start_emulator(emulator_name, emulator_udid, dns):
    print(f"[INFO] Uruchamiam emulator {emulator_name} (UDID: {emulator_udid})...")
    sdk_root = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if sdk_root:
        emulator_exe = os.path.join(sdk_root, "emulator", "emulator.exe")
    else:
        emulator_exe = "emulator"

    subprocess.Popen(
        [emulator_exe, "-avd", emulator_name, "-port", emulator_udid[-4:], "-dns-server", dns],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if wait_for_home_screen(200, emulator_udid):
        print(f"{GREEN}[INFO] Emulator {emulator_name} uruchomiony na {emulator_udid}.{RESET}")
    else:
        print("[WARNING] Czas oczekiwania na ekran główny przekroczony.")
    return emulator_udid


# ==================== GŁÓWNY BLOK ====================
if __name__ == "__main__":
    monitor_thread = threading.Thread(target=monitor_appium, args=(EMULATOR_UDID,), daemon=True)
    monitor_thread.start()

    while not is_current_time_allowed():
        print(f"{YELLOW}[MAIN] Poza dozwolonym zakresem pracy bota. Czekam...{RESET}")
        time.sleep(30)

    emulator_process = start_emulator(EMULATOR_NAME, EMULATOR_UDID, DNS)
    dynamic_sleep(25, "Na włączenie emulatora")

    server_process = start_appium_server()
    driver = None

    while True:
        try:
            driver = initialize_driver(EMULATOR_NAME, EMULATOR_UDID)
            run_bot()
            break
        except Exception as e:
            print(f"{RED}[BŁĄD] Problem z Appium/emulatorem: {e}{RESET}")
            print("[INFO] Restartuję serwer ADB i wznawiam sesję z zachowaniem stanu...")
            restart_adb_appium(EMULATOR_NAME, EMULATOR_UDID)
            print("[INFO] Ponownie łączę się z ADB... (czekam chwilę)")
            time.sleep(5)
            continue
    input("Naciśnij Enter, aby zakończyć działanie skryptu...")
    server_process.terminate()