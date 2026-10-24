import { chromium, Page } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

export async function auditPage(url: string): Promise<any> {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page: Page = await context.newPage();

  await page.goto(url, { waitUntil: 'networkidle' });

  const accessibilityScanResults = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22a', 'wcag22aa'])
    .analyze();

  await browser.close();

  return accessibilityScanResults;
}
