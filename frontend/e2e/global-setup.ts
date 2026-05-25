import { chromium } from '@playwright/test';

async function globalSetup() {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  
  const SECRET = "GRAXIA_E2E_FINAL_VERIFICATION";
  
  try {
    console.log('⏳ Global Setup: Requesting high-speed test session...');
    
    // Call the test-session backdoor
    const response = await page.request.post('http://127.0.0.1:8000/api/v1/auth/test-session', {
      headers: {
        'X-E2E-Secret': SECRET
      }
    });
    
    if (response.status() !== 200) {
      throw new Error(`Failed to get test session: ${response.status()} ${await response.text()}`);
    }

    // Storage state is automatically captured if we navigate once after cookies are set
    await page.goto('http://127.0.0.1:41730/');
    await page.waitForTimeout(2000);
    
    await context.storageState({ path: 'storageState.json' });
    console.log('✅ Global Setup: Session synchronized and saved.');
  } catch (err) {
    console.error('❌ Global Setup Failed:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

export default globalSetup;
