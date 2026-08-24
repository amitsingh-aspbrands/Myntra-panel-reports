"""
MCP Server for Myntra Seller Panel (MDirect) Scraping.

Uses undetected-chromedriver to bypass anti-bot detection.

Tools:
- login: Authenticate to Myntra seller panel via email/password
- schedule_report: Go to Selfserve page, select JIT INVENTORY DOWNLOAD, submit
- download_report: Go to Airflow page, search, find completed report, download SUCCESS FILE
"""

import asyncio
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()

# --- Configuration ---
LOGIN_URL = (
    "https://accounts.myntra.com/emaillogin"
    "?cidx=partners_mdirect-bb952a4d-38dd-4e69-91c1-90be8e98ff29"
    "&pageRequested=https%3A%2F%2Fpartnersapi.myntrainfo.com%2Fapi%2Fuser%2Flogin%2Fmdirect"
    "%3Fback%3Dhttps%253A%252F%252Fmdirect.myntrainfo.com%252F%253Fstate%253Dmdirect-login"
)
SELFSERVE_URL = "https://mdirect.myntrainfo.com/Selfserve"
AIRFLOW_URL = "https://mdirect.myntrainfo.com/Airflow"

MYNTRA_EMAIL = os.getenv("MYNTRA_EMAIL", "")
MYNTRA_PASSWORD = os.getenv("MYNTRA_PASSWORD", "")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./reports")

# --- Global browser state ---
_driver: uc.Chrome | None = None


def get_driver() -> uc.Chrome:
    """Get or create an undetected Chrome driver."""
    global _driver

    if _driver is not None:
        try:
            _ = _driver.current_url  # Check if still alive
            return _driver
        except Exception:
            try:
                _driver.quit()
            except Exception:
                pass
            _driver = None

    download_path = Path(DOWNLOAD_DIR).resolve()
    download_path.mkdir(parents=True, exist_ok=True)

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Set download directory
    prefs = {
        "download.default_directory": str(download_path),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    options.add_experimental_option("prefs", prefs)

    _driver = uc.Chrome(options=options, use_subprocess=True, version_main=151)
    _driver.implicitly_wait(5)

    return _driver


def human_type(driver, element, text: str):
    """Type text with random delays between keystrokes."""
    # Clear the field using JavaScript (safer for React inputs)
    driver.execute_script("arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', {bubbles: true}));", element)
    time.sleep(0.3)
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.03, 0.08))


# --- MCP Server Setup ---
server = MCPServer("myntra-scraper-mcp")


@server.tool()
async def login(email: str = "", password: str = "") -> str:
    """Log in to Myntra seller panel (MDirect) using email and password.
    Saves session state so subsequent calls skip re-login.
    """
    email = email or MYNTRA_EMAIL
    password = password or MYNTRA_PASSWORD

    if not email or not password:
        return "Error: Email and password required. Provide as arguments or set MYNTRA_EMAIL/MYNTRA_PASSWORD in .env"

    try:
        driver = await asyncio.to_thread(_login_sync, email, password)
        return driver
    except Exception as e:
        return f"Login failed with error: {str(e)}"


def _login_sync(email: str, password: str) -> str:
    """Synchronous login logic (runs in thread)."""
    driver = get_driver()

    driver.get(LOGIN_URL)
    time.sleep(random.uniform(2, 4))

    # Check if already logged in
    if "mdirect.myntrainfo.com" in driver.current_url and "emaillogin" not in driver.current_url:
        return "Already logged in. Session is active."

    # Enter email
    try:
        email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "input[type='email'], input[name='email'], input[id*='email'], input[placeholder*='mail']"
            ))
        )
        email_input.click()
        time.sleep(random.uniform(0.3, 0.7))
        human_type(driver, email_input, email)
    except Exception:
        return "Error: Could not find email input field."

    time.sleep(random.uniform(0.8, 1.5))

    # Enter password
    try:
        password_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "input[type='password'], input[name='password'], input[id*='password']"
            ))
        )
        password_input.click()
        time.sleep(random.uniform(0.3, 0.7))
        human_type(driver, password_input, password)
    except Exception:
        return "Error: Could not find password input field."

    time.sleep(random.uniform(0.8, 1.5))

    # Click login button
    try:
        login_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "button[type='submit'], button:has(span:contains('Login')), input[type='submit']"
            ))
        )
        login_button.click()
    except Exception:
        # Try broader selector
        buttons = driver.find_elements(By.TAG_NAME, "button")
        clicked = False
        for btn in buttons:
            text = btn.text.strip().lower()
            if text in ("login", "log in", "sign in", "submit"):
                btn.click()
                clicked = True
                break
        if not clicked:
            return "Error: Could not find login button."

    # Wait for navigation
    time.sleep(random.uniform(4, 6))

    current_url = driver.current_url
    if "emaillogin" in current_url or "accounts.myntra.com" in current_url:
        # Check for error message
        try:
            error_el = driver.find_element(By.CSS_SELECTOR, "[class*='error'], [class*='Error'], [role='alert']")
            return f"Login failed. Error on page: {error_el.text}"
        except Exception:
            return "Login may have failed. Still on login page. Check the browser window."

    return f"Login successful!\nCurrent page: {current_url}"


@server.tool()
async def schedule_report() -> str:
    """Navigate to MDirect Selfserve page, select 'JIT INVENTORY DOWNLOAD'
    report type, and click SUBMIT to schedule the report.
    """
    try:
        result = await asyncio.to_thread(_schedule_report_sync)
        return result
    except Exception as e:
        return f"Failed to schedule report: {str(e)}"


def _schedule_report_sync() -> str:
    """Synchronous schedule report logic."""
    driver = get_driver()

    driver.get(SELFSERVE_URL)
    time.sleep(random.uniform(2, 4))

    # Check if redirected to login
    if "emaillogin" in driver.current_url or "accounts.myntra.com" in driver.current_url:
        return "Session expired. Please run the 'login' tool first."

    # Select report type "JIT INVENTORY DOWNLOAD"
    try:
        # The dropdown has a combobox input overlaying the placeholder input
        # Target the combobox role element which is the clickable one
        task_dropdown = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "input[role='combobox'][aria-controls*='select']"
            ))
        )
        task_dropdown.click()
        time.sleep(random.uniform(1, 2))

        # Now find and click "JIT INVENTORY DOWNLOAD" from the opened options
        jit_option = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'JIT INVENTORY DOWNLOAD')]"
            ))
        )
        jit_option.click()
    except Exception as e:
        # Fallback: try clicking via JavaScript
        try:
            combobox = driver.find_element(By.CSS_SELECTOR, "input[role='combobox']")
            driver.execute_script("arguments[0].click();", combobox)
            time.sleep(1)
            jit_options = driver.find_elements(By.XPATH, "//*[contains(text(), 'JIT INVENTORY DOWNLOAD') or contains(text(), 'Jit Inventory Download') or contains(text(), 'jit inventory download')]")
            if jit_options:
                jit_options[0].click()
            else:
                # List all visible options for debugging
                options = driver.find_elements(By.CSS_SELECTOR, "[id*='option'], [role='option'], li")
                option_texts = [o.text for o in options if o.text.strip()][:20]
                return f"Opened dropdown but could not find JIT option. Visible options: {option_texts}"
        except Exception as e2:
            return f"Could not interact with Task dropdown: {str(e2)}"

    time.sleep(random.uniform(1, 2))

    # Click SUBMIT
    try:
        submit_button = None
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            if "SUBMIT" in btn.text.upper():
                submit_button = btn
                break

        if not submit_button:
            inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='submit']")
            for inp in inputs:
                if "SUBMIT" in inp.get_attribute("value").upper():
                    submit_button = inp
                    break

        if submit_button:
            submit_button.click()
            time.sleep(random.uniform(3, 5))

            page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if any(word in page_text for word in ["success", "scheduled", "submitted", "request"]):
                return (
                    "Report scheduled successfully!\n"
                    "Report type: JIT INVENTORY DOWNLOAD\n"
                    "Check the Airflow page in a few minutes using 'download_report' tool."
                )
            else:
                return (
                    f"SUBMIT clicked.\n"
                    f"Current URL: {driver.current_url}\n"
                    "Report may be processing. Try download_report in a few minutes."
                )
        else:
            return "Could not find SUBMIT button on the Selfserve page."
    except Exception as e:
        return f"Error clicking SUBMIT: {str(e)}"


@server.tool()
async def download_report(filename: str = "", max_wait_minutes: int = 15) -> str:
    """Navigate to MDirect Airflow page, click SEARCH, find the latest completed
    'ims_jit_inventory_download' report, click DOWNLOAD FILES, then click
    SUCCESS FILE to download the report as CSV.

    Polls every 60 seconds until the report is ready, up to max_wait_minutes.
    Files are saved with date prefix for audit: reports/YYYY-MM-DD/jit_inventory_report.csv
    """
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    if not filename:
        filename = f"jit_inventory_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    if not filename.endswith(".csv"):
        filename += ".csv"

    try:
        result = await asyncio.to_thread(_download_report_sync, filename, today, max_wait_minutes)
        return result
    except Exception as e:
        return f"Download failed: {str(e)}"


def _download_report_sync(filename: str, date_folder: str, max_wait_minutes: int = 15) -> str:
    """Synchronous download report logic with polling."""
    driver = get_driver()
    max_attempts = max_wait_minutes  # Check once per minute
    poll_interval = 60  # seconds

    for attempt in range(max_attempts):
        driver.get(AIRFLOW_URL)
        time.sleep(random.uniform(2, 4))

        # Check if redirected to login
        if "emaillogin" in driver.current_url or "accounts.myntra.com" in driver.current_url:
            return "Session expired. Please run the 'login' tool first."

        # Click SEARCH button
        search_clicked = driver.execute_script("""
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                if (buttons[i].textContent.trim().toUpperCase() === 'SEARCH') {
                    buttons[i].click();
                    return true;
                }
            }
            return false;
        """)

        if not search_clicked:
            return "Could not find SEARCH button on Airflow page."

        time.sleep(random.uniform(5, 8))

        # Click "DOWNLOAD FILES" specifically for the latest ims_jit_inventory_download report
        clicked = driver.execute_script("""
            // Find all text nodes containing ims_jit_inventory_download
            var body = document.body.innerHTML;
            // Get all elements that might be report containers
            var all = document.querySelectorAll('*');
            var reportContainers = [];
            
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                var text = el.textContent.trim();
                // Look for a container that has both ims_jit_inventory_download and DOWNLOAD FILES
                if (text.includes('ims_jit_inventory_download') && 
                    text.includes('DOWNLOAD FILES') &&
                    text.includes('COMPLETED')) {
                    // Find the DOWNLOAD FILES element within this container
                    var children = el.querySelectorAll('a, [role="button"], button, span');
                    for (var j = 0; j < children.length; j++) {
                        var childText = children[j].textContent.trim().toUpperCase();
                        if (childText === 'DOWNLOAD FILES') {
                            children[j].click();
                            return 'clicked';
                        }
                    }
                }
            }
            
            // Fallback: just click first DOWNLOAD FILES
            for (var i = 0; i < all.length; i++) {
                var text = all[i].textContent.trim().toUpperCase();
                if (text === 'DOWNLOAD FILES') {
                    all[i].click();
                    return 'clicked_fallback';
                }
            }
            return 'not_found';
        """)

        if clicked == 'not_found':
            if attempt < max_attempts - 1:
                time.sleep(poll_interval)
                continue
            else:
                return f"Report not ready after waiting {max_wait_minutes} minutes. No DOWNLOAD FILES link found."

        # Poll for the SUCCESS FILE CSV link (popup needs time to render)
        download_url = None
        for poll in range(10):
            time.sleep(1)
            download_url = driver.execute_script("""
                var links = document.querySelectorAll('a[href*=".csv"]');
                for (var i = 0; i < links.length; i++) {
                    var text = links[i].textContent.trim().toLowerCase();
                    if (text.includes('success')) {
                        return links[i].href;
                    }
                }
                var dlLinks = document.querySelectorAll('a[download*=".csv"]');
                for (var i = 0; i < dlLinks.length; i++) {
                    var text = dlLinks[i].textContent.trim().toLowerCase();
                    if (text.includes('success')) {
                        return dlLinks[i].href || dlLinks[i].getAttribute('download');
                    }
                }
                return null;
            """)
            if download_url:
                break

        if not download_url:
            # No SUCCESS FILE yet — report might still be processing
            if attempt < max_attempts - 1:
                # Close any open popup by pressing Escape or clicking elsewhere
                try:
                    driver.execute_script("document.body.click();")
                except Exception:
                    pass
                time.sleep(poll_interval)
                continue
            else:
                return f"Report not ready after waiting {max_wait_minutes} minutes. DOWNLOAD FILES found but no SUCCESS FILE available."

        # Download the file directly using the URL
        import urllib.request
        download_path = Path(DOWNLOAD_DIR).resolve() / date_folder
        download_path.mkdir(parents=True, exist_ok=True)
        save_path = download_path / filename

        cookies = driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

        req = urllib.request.Request(download_url)
        req.add_header("Cookie", cookie_str)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read()
            save_path.write_bytes(content)

        file_size = save_path.stat().st_size
        return (
            f"Report downloaded successfully!\n"
            f"File: {save_path}\n"
            f"Size: {file_size / 1024:.1f} KB\n"
            f"Attempts: {attempt + 1}"
        )

    return f"Report not ready after {max_wait_minutes} minutes. Please try again later."


def main():
    """Entry point for the MCP server."""
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
