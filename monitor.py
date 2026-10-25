"""
monitor.py
==========

ICPPLUS appointment monitor for GitHub Actions.
"""

import json
import os
import random
import smtplib
import sys
import time
import argparse
from datetime import datetime, timezone
from email.mime.text import MIMEText
from urllib.request import Request, urlopen
from urllib.error import URLError

from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BASE_URL = "https://icp.administracionelectronica.gob.es/icpplus/index.html"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
DEBUG_SCREENSHOT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "debug_screenshot.png"
)

DEFAULT_SELECTORS = {
    "cookie_accept_xpath": "//*[@id='cookie_action_close_header']",
    "province_select_id": "form",
    "province_submit_id": "btnAceptar",
    "tramite_select_id": "tramiteGrupo[1]",
    "tramite_submit_id": "btnAceptar",
    "no_cert_id": "btnEntrar",
    "calendar_indicator_id": "calendario",
}

DEFAULT_NO_SLOTS_PHRASES = [
    "no hay citas disponibles",
    "no existen citas disponibles",
    "en este momento no hay citas disponibles",
    "no hay horas disponibles",
]

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("GMAIL_EMAIL", "")
SMTP_PASS = os.environ.get("GMAIL_APP_PASSWORD", "")
ALERT_TO = os.environ.get("ALERT_EMAIL_TO", "") or SMTP_USER
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ICP_NIE = os.environ.get("ICP_NIE", "")
ICP_FULL_NAME = os.environ.get("ICP_FULL_NAME", "")
ICP_NATIONALITY = os.environ.get("ICP_NATIONALITY", "")


class AccessBlockedError(RuntimeError):
    pass


class ApplicantDetailsRequiredError(RuntimeError):
    pass


def valid_nie(value: str) -> bool:
    value = value.strip().upper()
    if len(value) != 9 or value[0] not in "XYZ" or not value[1:8].isascii() or not value[1:8].isdigit():
        return False
    number = str("XYZ".index(value[0])) + value[1:8]
    return value[-1] == "TRWAGMYFPDXBNJZSQVHLCKE"[int(number) % 23]


def human_delay(a: float = 0.4, b: float = 1.0) -> None:
    time.sleep(random.uniform(a, b))


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.page_load_strategy = "eager"
    if os.environ.get("ICP_HEADLESS", "1").lower() not in ("0", "false", "no"):
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--lang=es-ES")
    if os.name != "nt":
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    if os.environ.get("ICP_BROWSER_PROFILE"):
        options.add_argument("--user-data-dir=" + os.path.abspath(os.environ["ICP_BROWSER_PROFILE"]))
    if os.environ.get("CHROME_BINARY"):
        options.binary_location = os.environ["CHROME_BINARY"]
    driver_path = os.environ.get("CHROMEDRIVER_PATH")
    driver = webdriver.Chrome(options=options, service=Service(driver_path) if driver_path else Service())
    driver.set_page_load_timeout(60)
    return driver


def wait_and_click(driver, by, value, timeout=20):
    elem = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
    elem.click()
    return elem


def wait_for(driver, by, value, timeout=20):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


def save_debug_screenshot(driver, log) -> None:
    """Best-effort screenshot + page source dump for debugging failures."""
    if driver is None:
        return
    if ICP_NIE or ICP_FULL_NAME:
        log("Page diagnostics omitted because applicant details are configured.")
        return
    try:
        driver.save_screenshot(DEBUG_SCREENSHOT_FILE)
        log("Saved debug screenshot to debug_screenshot.png")
    except Exception as e:
        log(f"Could not save debug screenshot: {e}")
    try:
        html_path = DEBUG_SCREENSHOT_FILE.replace(".png", ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        log("Saved debug page source to debug_screenshot.html")
    except Exception as e:
        log(f"Could not save debug page source: {e}")


def check_access(driver) -> None:
    text = driver.find_element(By.TAG_NAME, "body").text.lower()
    title = driver.title.lower()
    if "403 forbidden" in title or "you don't have permission to access" in text:
        raise AccessBlockedError("ICPPLUS returned 403 Forbidden; availability could not be checked.")
    if "request rejected" in title or "requested url was rejected" in text:
        raise AccessBlockedError("ICPPLUS rejected the request; availability could not be checked.")
    if "intrusion prevention" in title or "blocked by intrusion prevention" in text:
        raise AccessBlockedError("Network intrusion prevention blocked access; availability could not be checked.")
    if not text.strip():
        raise AccessBlockedError("ICPPLUS returned an empty page; availability could not be checked.")
    challenges = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], input[name='captcha']")
    if any(element.is_displayed() for element in challenges):
        raise AccessBlockedError("Manual CAPTCHA required; availability could not be checked.")


def read_availability(driver, profile: dict, log) -> tuple[bool, str]:
    check_access(driver)
    page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    for phrase in profile.get("no_slots_phrases") or DEFAULT_NO_SLOTS_PHRASES:
        if phrase.lower() in page_text:
            log("An explicit no-appointments message was found.")
            return False, BASE_URL
    sel = {**DEFAULT_SELECTORS, **(profile.get("selectors") or {})}
    try:
        wait_for(driver, By.ID, sel["calendar_indicator_id"], timeout=8)
        log("Calendar/slot-selection element found - slots may be available!")
        return True, BASE_URL
    except TimeoutException:
        raise RuntimeError("No availability message or calendar found. Availability could not be determined.")


def check_appointments(driver, profile: dict, log) -> tuple[bool, str]:
    if ICP_NIE and not valid_nie(ICP_NIE):
        raise ApplicantDetailsRequiredError("The configured NIE has an invalid check digit. Correct the private ICP_NIE secret.")
    sel = {**DEFAULT_SELECTORS, **(profile.get("selectors") or {})}

    log("Opening ICPPLUS home page...")
    driver.get(BASE_URL)
    human_delay(2, 4)
    check_access(driver)

    for cookie_xpath in [
        sel["cookie_accept_xpath"],
        "//button[contains(text(),'Aceptar cookies')]",
    ]:
        try:
            wait_and_click(driver, By.XPATH, cookie_xpath, timeout=5)
            log(f"Closed cookie banner using: {cookie_xpath}")
            human_delay()
            break
        except TimeoutException:
            continue

    # Render the form again after its initial cookie has been established.
    # Old URL-rewritten session IDs can otherwise be carried into a different app context.
    if driver.find_elements(By.CSS_SELECTOR, "form[action*=';jsessionid=']"):
        log("Refreshing the initialized session before selecting a province...")
        driver.refresh()
        human_delay(2, 4)
        check_access(driver)

    log(f"Selecting province '{profile['province']}'...")
    try:
        province_select = Select(wait_for(driver, By.ID, sel["province_select_id"]))
        province_select.select_by_visible_text(profile["province"])
    except Exception as e:
        log("Province selection failed.")
        save_debug_screenshot(driver, log)
        raise
    human_delay()
    wait_and_click(driver, By.ID, sel["province_submit_id"])
    human_delay(2, 4)

    check_access(driver)

    log(f"Selecting procedure '{profile['procedure_name']}'...")
    tramite_select = Select(wait_for(driver, By.ID, sel["tramite_select_id"]))
    tramite_select.select_by_visible_text(profile["procedure_name"])
    human_delay()
    wait_and_click(driver, By.ID, sel["tramite_submit_id"])
    human_delay(2, 4)
    check_access(driver)

    log("Opening presentation without Cl@ve...")
    wait_and_click(driver, By.ID, sel["no_cert_id"])
    human_delay(1, 2)
    check_access(driver)

    if driver.find_elements(By.ID, "txtIdCitado"):
        if not all((ICP_NIE, ICP_FULL_NAME, ICP_NATIONALITY)):
            raise ApplicantDetailsRequiredError("Applicant details required: configure ICP_NIE, ICP_FULL_NAME and ICP_NATIONALITY as secrets.")
        log("Identifying the applicant using private configuration...")
        wait_for(driver, By.ID, "txtIdCitado").send_keys(ICP_NIE)
        wait_for(driver, By.ID, "txtDesCitado").send_keys(ICP_FULL_NAME)
        Select(wait_for(driver, By.ID, "txtPaisNac")).select_by_visible_text(ICP_NATIONALITY)
        wait_and_click(driver, By.ID, "btnEnviar")
        human_delay(1, 2)
        check_access(driver)

    # This button only opens availability; no date, office or reservation is submitted.
    request_buttons = driver.find_elements(By.XPATH, "//input[@value='Solicitar Cita' or @value='Solicitar cita'] | //button[normalize-space()='Solicitar Cita' or normalize-space()='Solicitar cita']")
    for button in request_buttons:
        if button.is_displayed():
            button.click()
            human_delay(1, 2)
            break
    result = read_availability(driver, profile, log)
    if os.environ.get("ICP_BROWSER_PROFILE"):
        exit_buttons = driver.find_elements(By.XPATH, "//input[@value='Salir'] | //button[normalize-space()='Salir']")
        for button in exit_buttons:
            if button.is_displayed():
                try:
                    button.click()
                    log("Ended the checking session.")
                except WebDriverException:
                    log("Could not close the session; the check result was retained.")
                break
    return result


def send_telegram(body: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured - skipping notification.")
        return False
    request = Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": body}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            ok = json.load(response).get("ok", False)
        print("Telegram notification sent." if ok else "Telegram rejected the notification.")
        return ok
    except (URLError, ValueError):
        # Do not log the exception: request URLs contain the secret bot token.
        print("Telegram notification failed; check the token, chat ID and network.")
        return False


def send_email(subject: str, body: str) -> None:
    if not SMTP_USER or not SMTP_PASS or not ALERT_TO:
        print("Email not configured - skipping notification.")
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_TO

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [ALERT_TO], msg.as_string())
    except Exception as e:
        print(f"Email send error: {e}")


def load_profiles() -> list:
    with open(PROFILES_FILE, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    if not isinstance(profiles, list):
        raise ValueError("data/profiles.json must contain a list.")
    ids = set()
    for profile in profiles:
        for key in ("id", "name", "province", "procedure_name"):
            if not isinstance(profile.get(key), str) or not profile[key].strip():
                raise ValueError(f"Each profile needs a nonempty {key}.")
        if profile["id"] in ids:
            raise ValueError(f"Duplicate profile ID: {profile['id']}")
        ids.add(profile["id"])
    return profiles


def load_status() -> dict:
    if not os.path.exists(STATUS_FILE):
        return {"profiles": {}, "last_run": None}
    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_status(status: dict) -> None:
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


def run_profile(profile: dict) -> dict:
    logs = []

    def log(msg):
        for secret in (ICP_NIE, ICP_FULL_NAME, ICP_NATIONALITY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SMTP_PASS):
            if secret:
                msg = msg.replace(secret, "[redacted]")
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        logs.append(line)
        print(f"[{profile['name']}] {line}")

    driver = None
    try:
        driver = build_driver()
        browser_version = driver.capabilities.get("browserVersion", "unknown")
        driver_version = driver.capabilities.get("chrome", {}).get("chromedriverVersion", "unknown").split(" ")[0]
        log(f"Chrome {browser_version}; ChromeDriver {driver_version}.")
        available, url = check_appointments(driver, profile, log)
        return {
            "name": profile["name"],
            "province": profile["province"],
            "procedure_name": profile["procedure_name"],
            "status": "available" if available else "unavailable",
            "url": url,
            "last_check": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "logs": logs[-20:],
        }
    except (AccessBlockedError, ApplicantDetailsRequiredError) as e:
        log(str(e))
        save_debug_screenshot(driver, log)
        return {
            "name": profile["name"],
            "province": profile["province"],
            "procedure_name": profile["procedure_name"],
            "status": "requires_input" if isinstance(e, ApplicantDetailsRequiredError) else "blocked",
            "url": BASE_URL,
            "last_check": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "logs": logs[-20:],
        }
    except WebDriverException as e:
        log(f"Browser/WebDriver error: {e}")
        save_debug_screenshot(driver, log)
        return {
            "name": profile["name"],
            "province": profile["province"],
            "procedure_name": profile["procedure_name"],
            "status": "error",
            "url": None,
            "last_check": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "logs": logs[-20:],
        }
    except Exception as e:
        log(f"Unexpected error: {e}")
        save_debug_screenshot(driver, log)
        return {
            "name": profile["name"],
            "province": profile["province"],
            "procedure_name": profile["procedure_name"],
            "status": "error",
            "url": None,
            "last_check": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "logs": logs[-20:],
        }
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def main():
    profiles = load_profiles()
    status = load_status()
    status.setdefault("profiles", {})
    active_ids = {profile["id"] for profile in profiles}
    status["profiles"] = {key: value for key, value in status["profiles"].items() if key in active_ids}

    if not profiles:
        print("No profiles configured in data/profiles.json - nothing to do.")
        status["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_status(status)
        return

    any_available = False

    for profile in profiles:
        if not profile.get("enabled", True):
            print(f"Skipping disabled profile: {profile['name']}")
            continue

        print(f"=== Checking profile: {profile['name']} ===")
        result = run_profile(profile)
        status["profiles"][profile["id"]] = result

        if result["status"] == "available":
            any_available = True
            subject = f"🔔 ICPPLUS slot may be available: {result['name']}"
            body = (
                f"SLOT MAY BE AVAILABLE\n\n"
                f"Client: {result['name']}\n"
                f"Province: {result['province']}\n"
                f"Procedure: {result['procedure_name']}\n\n"
                f"Link: {result['url']}\n\n"
                f"Open this link, redo province/procedure selection if "
                f"needed, use Autofill (Tampermonkey), solve CAPTCHA + SMS, "
                f"and submit FAST - slots disappear in seconds!"
            )
            send_email(subject, body)
            send_telegram(body)

        human_delay(1.5, 3)

    status["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_status(status)

    if any_available:
        print("\n*** AT LEAST ONE PROFILE HAS POSSIBLE SLOTS ***")
    else:
        print("\nNo confirmed availability in this run. Check each profile's status for access errors.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check ICPPLUS and send configured alerts.")
    parser.add_argument("--headed", action="store_true", help="Show Chrome for local checks.")
    parser.add_argument("--probe-browser", action="store_true", help="Test the initial public page without submitting applicant details.")
    parser.add_argument("--test-telegram", action="store_true", help="Send a Telegram connection test, without checking appointments.")
    args = parser.parse_args()
    if args.headed:
        os.environ["ICP_HEADLESS"] = "0"
    if args.probe_browser:
        probe_driver = build_driver()
        try:
            probe_driver.get(BASE_URL)
            WebDriverWait(probe_driver, 20).until(
                lambda driver: driver.find_elements(By.ID, DEFAULT_SELECTORS["province_select_id"])
                or driver.find_element(By.TAG_NAME, "body").text.strip()
            )
            check_access(probe_driver)
            found = bool(probe_driver.find_elements(By.ID, DEFAULT_SELECTORS["province_select_id"]))
            print(json.dumps({"page_title": probe_driver.title, "province_select_present": found}))
            sys.exit(0 if found else 1)
        except Exception as error:
            print(json.dumps({"probe_error": type(error).__name__, "message": str(error).split("\n")[0]}))
            sys.exit(1)
        finally:
            probe_driver.quit()
    if args.test_telegram:
        sys.exit(0 if send_telegram("ICPPLUS Monitor: conexión con Telegram verificada.") else 1)
    main()
