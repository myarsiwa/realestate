from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1100, "height": 1400})
    page.goto("file:///C:/temp/AIProjects/realestate/rentcast_data/dashboard_final.html")
    page.wait_for_timeout(500)
    page.screenshot(path="preview.png", full_page=True)
    browser.close()
