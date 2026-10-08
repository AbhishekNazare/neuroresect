// Run against the local app: PLAYWRIGHT_CHANNEL=chrome node scripts/capture-workstation.mjs
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

await mkdir('docs/assets', { recursive: true });
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' });
  await page.goto(process.env.WEB_URL || 'http://localhost:3000');
  await page.getByRole('button', { name: 'Simulate resection', exact: true }).click();
  await page.getByText('Metrics computed by neurocore', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Estimate synthetic outcome', exact: true }).click();
  await page.locator('.prediction-value').waitFor({ timeout: 90000 });
  await page.addStyleTag({ content: 'nextjs-portal { visibility: hidden; }' });
  await page.screenshot({ path: 'docs/assets/workstation.png', fullPage: true });
  await page.getByRole('button', { name: 'How it works', exact: true }).click();
  await page.locator('.matrix-wrap canvas').waitFor();
  await page.screenshot({ path: 'docs/assets/pipeline.png', fullPage: true });
  await page.getByRole('button', { name: 'Experiments', exact: true }).click();
  await page.getByLabel('Synthetic patients', { exact: true }).fill('24');
  await page.getByRole('button', { name: 'Run A/B/C experiment', exact: true }).click();
  await page.locator('.experiment-bars').waitFor({ timeout: 90000 });
  await page.screenshot({ path: 'docs/assets/experiments.png', fullPage: true });
  console.log('Captured workstation, pipeline, and experiment screenshots.');
} finally {
  await browser.close();
}
