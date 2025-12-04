import { test, expect, Page } from '@playwright/test';

interface PerformanceMetrics {
  firstContentfulPaint: number | null;
  largestContentfulPaint: number | null;
  timeToInteractive: number;
}

test.describe('Frontend Performance Tests', () => {
  test('Homepage Load and Dashboard Navigation Performance', async ({ page }) => {
    // --- Step 1: Navigate to the homepage and measure initial load performance ---
    console.log('Navigating to homepage...');
    const homepageLoadStart = Date.now();
    await page.goto('http://localhost:3060');

    // Wait for network to be idle, or a specific element to be visible, to ensure page is loaded
    await page.waitForLoadState('networkidle');

    const homepageLoadEnd = Date.now();
    const homepageLoadTime = homepageLoadEnd - homepageLoadStart;
    console.log(`Homepage Load Time: ${homepageLoadTime} ms`);

    // Collect performance metrics using PerformanceObserver
    const metrics: PerformanceMetrics = await page.evaluate(() => {
      return new Promise<PerformanceMetrics>(resolve => {
        const observer = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          const fcpEntry = entries.find(entry => entry.name === 'first-contentful-paint');
          const lcpEntry = entries.find(entry => entry.name === 'largest-contentful-paint');

          // Approximate TTI: wait for 2 seconds of network and CPU idle after LCP (simplified)
          // For more accurate TTI, consider using specific libraries or more complex heuristics
          const tti = performance.timing.domInteractive + (performance.timing.loadEventEnd - performance.timing.domInteractive);

          resolve({
            firstContentfulPaint: fcpEntry ? fcpEntry.startTime : null,
            largestContentfulPaint: lcpEntry ? lcpEntry.startTime : null,
            timeToInteractive: tti // Simplified TTI
          });
          observer.disconnect();
        });
        observer.observe({ entryTypes: ['paint', 'largest-contentful-paint'], buffered: true });

        // Fallback for cases where observer might not catch everything instantly or for basic TTI
        setTimeout(() => {
          resolve({
            firstContentfulPaint: performance.getEntriesByName('first-contentful-paint')[0]?.startTime || null,
            largestContentfulPaint: performance.getEntriesByType('largest-contentful-paint')[0]?.startTime || null,
            timeToInteractive: performance.timing.domInteractive + (performance.timing.loadEventEnd - performance.timing.domInteractive)
          });
        }, 3000); // Give some time for entries to be observed
      });
    });

    console.log('Homepage Performance Metrics:', metrics);

    // Assert that core metrics are within acceptable limits (example thresholds)
    expect(homepageLoadTime).toBeLessThan(5000); // Homepage should load in under 5 seconds
    if (metrics.firstContentfulPaint) {
      expect(metrics.firstContentfulPaint).toBeLessThan(2000); // FCP under 2 seconds
    }
    if (metrics.largestContentfulPaint) {
      expect(metrics.largestContentfulPaint).toBeLessThan(3000); // LCP under 3 seconds
    }
    // Consider adding a more robust TTI check

    // --- Step 2: Navigate to Dashboard and measure performance ---
    console.log('Navigating to dashboard...');
    const dashboardLoadStart = Date.now();
    
    // Find and click the dashboard link/button
    // You might need to adjust this selector based on your actual HTML structure
    const dashboardLink = page.locator('a[href="/dashboard"]');
    await expect(dashboardLink).toBeVisible(); // Ensure the link is visible before clicking
    await dashboardLink.click();

    // Wait for the dashboard page to load (e.g., wait for a specific element on the dashboard)
    await page.waitForURL('http://localhost:3060/dashboard'); // Wait for URL change
    await page.waitForLoadState('networkidle'); // Wait for network to be idle after navigation

    const dashboardLoadEnd = Date.now();
    const dashboardLoadTime = dashboardLoadEnd - dashboardLoadStart;
    console.log(`Dashboard Navigation Load Time: ${dashboardLoadTime} ms`);

    // Assert that dashboard load time is within acceptable limits
    expect(dashboardLoadTime).toBeLessThan(3000); // Dashboard should load in under 3 seconds

    // Add more assertions or metrics collection for the dashboard page if needed

    // Example of collecting network requests for a page
    const networkRequests = await page.evaluate(() => {
        return performance.getEntriesByType('resource').map(entry => {
          const resourceEntry = entry as PerformanceResourceTiming; // Cast to PerformanceResourceTiming
          return {
            name: resourceEntry.name,
            duration: resourceEntry.duration,
            transferSize: resourceEntry.transferSize
          };
        });
    });
    console.log(`Number of network requests on dashboard: ${networkRequests.length}`);
    // console.log('Network Requests:', networkRequests); // Uncomment for full details
  });
});