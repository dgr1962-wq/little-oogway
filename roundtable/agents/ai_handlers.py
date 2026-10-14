import undetected_chromedriver as uc
import os
import time

def launch_agent(name, settings):
    method = settings.get("method")
    profile_path = settings.get("profile")
    target_url = settings.get("url", "https://chat.openai.com")

    if method != "selenium":
        print(f"⚠️ Method '{method}' not supported yet.")
        return

    os.makedirs(profile_path, exist_ok=True)

    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument(f"--user-data-dir={os.path.abspath(profile_path)}")
    chrome_options.add_argument("--profile-directory=Default")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--start-maximized")

    try:
        driver = uc.Chrome(options=chrome_options, headless=False)
        driver.get(target_url)
        time.sleep(3)  # Allow time for page to fully load
    except Exception as e:
        print(f"🚨 Failed to launch {name}: {e}")
