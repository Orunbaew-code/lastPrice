import scrapy
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
import traceback
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException

class CopartonlineSpider(scrapy.Spider):
    name = "copartonline"
    start_urls = ["https://www.copart.com"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-translate")
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--log-level=3")
        chrome_prefs = {
            "profile.default_content_setting_values": {
                "images": 2,
                "stylesheet": 2,
                "fonts": 2
            }
        }
        chrome_options.experimental_options["prefs"] = chrome_prefs
        # recommended server flags:
        chrome_options.add_argument("--remote-debugging-port=0")
        # chrome_options.add_argument("--user-data-dir=/tmp/chrome-user-data")
        chrome_options.add_argument("user-agent=Your-Custom-User-Agent")

        # If you need headless mode (uncomment one of these if desired)
        # chrome_options.add_argument("--headless=new")       # modern headless
        # chrome_options.add_argument("--headless=chrome")    # fallback
        # chrome_options.add_argument("--headless")           # legacy

        # Explicit binary path on your Ubuntu server
        # chrome_options.binary_location = "/usr/bin/google-chrome"

        # use webdriver-manager to get matching chromedriver
        service = Service(ChromeDriverManager().install())

        # Create the driver
        try:
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            # helpful debug - raise with extra info
            raise RuntimeError(f"Failed to start Chrome webdriver: {e}")

        # Keep your anti-detection tweak
        try:
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
            )
        except Exception:
            # Not critical
            pass
        
    def start_requests(self):
        self.driver.get("https://www.copart.com/auctionDashboard/")
        self.joinauction()

    def joinauction(self):
        print("Press enter after you join auction!")
        input()
        self.parse_auction_page()

    def parse_auction_page(self):
        try:
            seen = set()
            old_price = 0
            iframe = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.TAG_NAME, "iframe"))
            )
            self.driver.switch_to.frame(iframe)

            while True:
                # Try to get the price from SVG <text> elements
                price = self.get_price_or_skip()
                if (price == "Sold!") or (price == "Approval!"):
                    # Title & Lot number
                    title_element = self.driver.find_element(By.CSS_SELECTOR, "div.titlelbl.ellipsis[title]")
                    title = title_element.text
                    lot_number = self.driver.find_element(By.CSS_SELECTOR, "a.titlelbl.ellipsis[href*='/lot/']").text
                    if (lot_number not in seen):
                        seen.add(lot_number)
                        with open("auction_results.txt", "a", encoding="utf-8") as f:
                            f.write(f"{title}, {lot_number}, {old_price}, {price}\n")
                else:
                    old_price = price if price else old_price
                
        except Exception as e:
            # Save the current iframe HTML to a file for debugging
            try:
                with open("iframe_error_dump.txt", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                print(f"[ERROR] {e}\nSaved iframe HTML to iframe_error_dump.txt")
            except Exception as inner_e:
                print(f"[ERROR SAVING FRAME] {inner_e}")

        except NoSuchElementException:
            try:
                auction_end = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@class,'sale-end') and text()='Auction Ended']")
                    )
                )
                if auction_end:
                    with open("auction_results.txt", "a", encoding="utf-8") as f:
                        f.write("AUCTION IS ENDED \n\n\n\n\n")
                    
                    print("✅ Auction ended. Leaving auction...")                        
                    self.driver.get("https://www.copart.com/auctionDashboard")
                    self.join_new_auction()
            except:
                pass  # if not found, continue scraping
            
            title = None
            self.logger.warning("No title element found — skipping. selector=%s", "div.titlelbl.ellipsis[title]")
        except StaleElementReferenceException:
            title = None
            self.logger.warning("Stale element while reading title — skipping.")
        except Exception:
            title = None
            # log full traceback but DO NOT raise
            self.logger.exception("Unexpected error while reading title — skipping")
    # continue processing safely

    def get_price_or_skip(self):
        """Extracts price text from inside SVG <text> elements"""
        try:
            # Grab all <text> nodes inside any SVG
            texts = self.driver.find_elements(By.CSS_SELECTOR, "svg text")
            if not texts:
                return self.check_auction_ended()
            for t in texts:
                txt = t.text.strip()
                if (txt == "Sold!") or (txt == "Approval!") or (any(ch.isdigit() for ch in txt)):
                    return txt

        except Exception:
            return None

    def join_new_auction(self):
        try:
            self.close_dialog_via_overlay()
            # 🔹 Find the first visible "Join" button
            WebDriverWait(self.driver, 1800).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "button.bid")) >= 2
            )

            # Get all join buttons
            join_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.bid")

            # Click the second button (index 1, since list is 0-based)
            # try: 
            #     join_buttons[1].click()
            # except Exception as e:
            join_buttons[0].click()
            # After joining, start parsing again
            self.parse_auction_page()

        except Exception as e:
            with open("iframe_error_dump.txt", "a", encoding="utf-8") as f:
                f.write("\n=== ERROR ===\n")
                f.write(f"Exception: {str(e)}\n")
                f.write(traceback.format_exc())

                try:
                    # Save iframe HTML
                    iframe_html = self.driver.page_source
                    f.write("\n=== IFRAME HTML DUMP ===\n")
                    f.write(iframe_html)
                    f.write("\n=== END DUMP ===\n")
                except Exception as inner_e:
                    f.write(f"\n[ERROR] Failed to dump iframe HTML: {inner_e}\n")

            print(f"[ERROR] Could not join new auction: {e}")

    def check_auction_ended(self):
        """Check if auction has ended"""
        try:
            auction_end = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class,'sale-end') and text()='Auction Ended']")
                )
            )
            if auction_end:
                print("✅ Auction ended. Leaving auction...")
                # Your auction end logic here
                self.driver.get("https://www.copart.com/auctionDashboard")
                self.join_new_auction()
                return "AUCTION_ENDED"
        except:
            # If auction end element not found, just continue
            return None

    def close_dialog_via_overlay(self):
        """Click on the overlay/mask to close the Recommended Auctions dialog"""
        try:
            # Wait for the overlay/mask to be present and clickable
            overlay = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.p-dialog-mask"))
            )
            
            # Click on the overlay (anywhere outside the dialog)
            overlay.click()
            print("✅ Closed dialog by clicking overlay")
            return True
            
        except Exception as e:
            print(f"❌ Could not close via overlay: {e}")
            return False