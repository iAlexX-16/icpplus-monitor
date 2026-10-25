"""Bounded, anonymous connection checks. Never load or request applicant secrets."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException


URL = "https://icp.administracionelectronica.gob.es/icpplustiem/index.html"


def public_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.split(";")[0], "", ""))


def dns_probe():
    started = time.monotonic()
    try:
        addresses = socket.getaddrinfo(urlsplit(URL).hostname, 443, type=socket.SOCK_STREAM)
        return {"addresses": sorted({entry[4][0] for entry in addresses}),
                "seconds": round(time.monotonic() - started, 3)}
    except OSError as error:
        return {"error": type(error).__name__}


def curl_probe(url, http1=False):
    command = ["curl", "--silent", "--show-error", "--connect-timeout", "12",
               "--max-time", "22", "--output", os.devnull, "--write-out", "%{json}"]
    if http1:
        command.append("--http1.1")
    result = subprocess.run(command + [url], capture_output=True, text=True, timeout=28)
    try:
        metadata = json.loads(result.stdout)
    except ValueError:
        return {"url": url, "curl_exit": result.returncode, "error": "No curl metadata"}
    keys = ("http_code", "http_version", "remote_ip", "time_namelookup", "time_connect",
            "time_appconnect", "time_starttransfer", "time_total", "ssl_verify_result", "errormsg")
    return {"url": url, "http1_only": http1, "curl_exit": result.returncode,
            **{key: metadata.get(key) for key in keys}}


def browser_probe(headless):
    options = Options()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    if os.environ.get("CHROME_BINARY"):
        options.binary_location = os.environ["CHROME_BINARY"]
    driver_path = os.environ.get("CHROMEDRIVER_PATH")
    driver = webdriver.Chrome(options=options, service=Service(driver_path) if driver_path else Service())
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(8)
    result = {"headless": headless, "browser": driver.capabilities.get("browserVersion"),
              "driver": driver.capabilities.get("chrome", {}).get("chromedriverVersion", "").split(" ")[0]}
    started = time.monotonic()
    try:
        driver.get(URL)
        result["navigation"] = "completed"
    except TimeoutException:
        result["navigation"] = "timeout"
    except WebDriverException as error:
        result["navigation"] = type(error).__name__
    finally:
        result["seconds"] = round(time.monotonic() - started, 3)
    try:
        result["title"] = driver.title[:160]
        result["province_select_present"] = bool(driver.find_elements("id", "form"))
        result["url"] = public_url(driver.current_url)
    except WebDriverException:
        result["dom_inspection"] = "unavailable"
    try:
        documents = set()
        events = []
        for entry in driver.get_log("performance"):
            message = json.loads(entry["message"])["message"]
            params = message.get("params", {})
            method = message["method"]
            if method == "Network.requestWillBeSent" and params.get("type") == "Document":
                documents.add(params["requestId"])
            if method == "Network.responseReceived" and params.get("type") == "Document":
                response = params["response"]
                events.append({"event": "document_response", "status": response["status"],
                               "protocol": response.get("protocol"), "url": public_url(response["url"])})
            if method == "Network.loadingFailed" and params.get("requestId") in documents:
                events.append({"event": "document_failure", "error": params.get("errorText"),
                               "blocked_reason": params.get("blockedReason")})
        result["network_events"] = events
    except (WebDriverException, ValueError):
        result["network_events"] = "unavailable"
    driver.quit()
    return result


def main():
    report = {"dns": dns_probe()}
    print("DNS " + json.dumps(report["dns"]), flush=True)
    report["http"] = []
    for url, http1 in (("https://github.com/", False), (URL, False), (URL, True)):
        result = curl_probe(url, http1)
        report["http"].append(result)
        print("HTTP " + json.dumps(result), flush=True)
    report["browsers"] = []
    for headless in (True, False):
        try:
            process = subprocess.run(
                [sys.executable, __file__, "--browser", "headless" if headless else "headed"],
                capture_output=True, text=True, timeout=70,
            )
            result = json.loads(process.stdout)
        except subprocess.TimeoutExpired:
            result = {"headless": headless, "error": "Browser process exceeded 70 seconds"}
        except (ValueError, OSError) as error:
            result = {"headless": headless, "error": type(error).__name__}
        report["browsers"].append(result)
        print("BROWSER " + json.dumps(result), flush=True)
    destination = Path("_diagnostics")
    destination.mkdir(exist_ok=True)
    (destination / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--browser":
        print(json.dumps(browser_probe(sys.argv[2] == "headless")))
    else:
        main()
