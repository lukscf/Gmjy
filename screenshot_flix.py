from playwright.sync_api import sync_playwright

def take_screenshot(url, output_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        )
        
        try:
            print(f"Navigating to {url}")
            page.goto(url, wait_until="networkidle")
            
            # Set zoom to 80%
            page.evaluate("document.body.style.zoom = '80%'")
            print("Zoom set to 80%")
            
            # Click the "Accept All" button with retries
            accept_button_found = False
            for attempt in range(3):
                try:
                    page.wait_for_selector("[data-testid='uc-accept-all-button']", timeout=10000)
                    page.click("[data-testid='uc-accept-all-button']")
                    print("Clicked 'Accept All' button")
                    accept_button_found = True
                    page.wait_for_timeout(2000)  # Wait for popup dismissal
                    break
                except Exception as e:
                    print(f"Attempt {attempt + 1} failed to find 'Accept All' button: {e}")
                    page.wait_for_timeout(2000)
            
            if not accept_button_found:
                # Fallback: Try locating by text
                try:
                    page.wait_for_selector("button:has-text('Accept All')", timeout=10000)
                    page.click("button:has-text('Accept All')")
                    print("Clicked 'Accept All' button (fallback method)")
                    page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"Error with fallback method: {e}")
            
            # Wait for map content (adjust selector based on inspection)
            try:
                page.wait_for_selector(".map-container", timeout=15000)  # Example; adjust as needed
                print("Map element detected")
            except Exception as e:
                print(f"Error waiting for map element: {e}. Trying to proceed anyway.")
            
            # Wait for dynamic content
            page.wait_for_timeout(5000)
            
            # Scroll to trigger map loading
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(2000)
            
            # Check page content
            content = page.content()
            if len(content) < 1000 or "<body" not in content.lower():
                print("Warning: Page content seems empty.")
                print(f"Page source snippet: {content[:500]}...")
            
            # Take screenshot
            page.screenshot(path=output_path, full_page=False)
            print(f"Screenshot saved to {output_path}")
            
        except Exception as e:
            print(f"Error during screenshot process: {e}")
            
        finally:
            browser.close()

# Example usage
url = "https://www.flixbus.com.br/track/ride/85ccb0b6-8cfd-4cbf-bb78-be96331b389b"
output_path = "screenshot.png"
take_screenshot(url, output_path)
