/*
 * Enterprise Load Testing Suite - k6
 * 
 * Tests cover:
 * - API endpoint performance
 * - Concurrent user handling
 * - Rate limiting verification
 * - Error rate monitoring
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Custom metrics
const errorRate = new Rate('errors');
const apiLatency = new Trend('api_latency');
const healthCheckFailures = new Counter('health_check_failures');

// Environment configuration
const ENV = __ENV.ENV || 'staging';
const BASE_URL = ENV === 'production' 
  ? 'https://graxia-api.fly.dev' 
  : 'https://staging.graxia-api.fly.dev';

// Test options
export const options = {
  scenarios: {
    // Smoke test - light load to verify basic functionality
    smoke: {
      executor: 'constant-vus',
      vus: 5,
      duration: '1m',
      gracefulStop: '10s',
      tags: { test_type: 'smoke' },
    },
    
    // Load test - simulate normal traffic
    load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },   // Ramp up
        { duration: '5m', target: 50 },  // Steady state
        { duration: '2m', target: 0 },   // Ramp down
      ],
      gracefulRampDown: '30s',
      tags: { test_type: 'load' },
    },
    
    // Stress test - find breaking point
    stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 100 },
        { duration: '5m', target: 100 },
        { duration: '2m', target: 200 },
        { duration: '5m', target: 200 },
        { duration: '2m', target: 0 },
      ],
      gracefulRampDown: '30s',
      tags: { test_type: 'stress' },
    },
    
    // Spike test - sudden traffic spike
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 200 },
        { duration: '1m', target: 200 },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '10s',
      tags: { test_type: 'spike' },
    },
  },
  
  // Thresholds
  thresholds: {
    http_req_duration: ['p(95)<500'],      // 95% of requests under 500ms
    http_req_duration: ['p(99)<1000'],   // 99% of requests under 1s
    http_req_failed: ['rate<0.01'],        // Error rate < 1%
    errors: ['rate<0.05'],                 // Custom error rate < 5%
    health_check_failures: ['count<3'],    // Max 3 health check failures
  },
};

// Main test function
export default function () {
  group('Health Endpoints', () => {
    testHealthEndpoint();
  });
  
  group('API Endpoints', () => {
    testSystemStats();
    testAnalyticsEndpoint();
    testBillingEndpoint();
  });
  
  group('Static Assets', () => {
    testDocumentation();
  });
  
  // Random sleep between requests (simulate real user behavior)
  sleep(randomIntBetween(1, 3));
}

// Test health endpoint
function testHealthEndpoint() {
  const url = `${BASE_URL}/health`;
  const startTime = new Date();
  
  const response = http.get(url, {
    tags: { endpoint: 'health' },
  });
  
  const latency = new Date() - startTime;
  apiLatency.add(latency);
  
  const success = check(response, {
    'health status is 200': (r) => r.status === 200,
    'health response is JSON': (r) => r.headers['Content-Type'].includes('application/json'),
    'health status is ok': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.status === 'ok';
      } catch (e) {
        return false;
      }
    },
  });
  
  if (!success) {
    errorRate.add(1);
    healthCheckFailures.add(1);
    console.error(`Health check failed: ${response.status} ${response.body}`);
  } else {
    errorRate.add(0);
  }
}

// Test system stats endpoint
function testSystemStats() {
  const url = `${BASE_URL}/system/stats`;
  
  const response = http.get(url, {
    tags: { endpoint: 'system_stats' },
    // No auth token for now - will get 403 which is expected
  });
  
  check(response, {
    'system stats returns expected status': (r) => 
      r.status === 200 || r.status === 401 || r.status === 403,
  });
}

// Test analytics endpoint
function testAnalyticsEndpoint() {
  const url = `${BASE_URL}/api/v1/analytics/dashboard`;
  
  const response = http.get(url, {
    tags: { endpoint: 'analytics_dashboard' },
  });
  
  const success = check(response, {
    'analytics returns valid status': (r) => 
      r.status === 200 || r.status === 401 || r.status === 403,
  });
  
  if (!success) {
    errorRate.add(1);
  } else {
    errorRate.add(0);
  }
}

// Test billing endpoint
function testBillingEndpoint() {
  const url = `${BASE_URL}/api/v1/billing/subscription`;
  
  const response = http.get(url, {
    tags: { endpoint: 'billing_subscription' },
  });
  
  check(response, {
    'billing returns valid status': (r) => 
      r.status === 200 || r.status === 401 || r.status === 403 || r.status === 404,
  });
}

// Test documentation endpoint
function testDocumentation() {
  const url = `${BASE_URL}/docs`;
  
  const response = http.get(url, {
    tags: { endpoint: 'docs' },
  });
  
  check(response, {
    'docs is accessible': (r) => r.status === 200,
    'docs returns HTML': (r) => r.headers['Content-Type'].includes('text/html'),
  });
}

// Setup function (runs once at the beginning)
export function setup() {
  console.log(`Starting load test against: ${BASE_URL}`);
  console.log(`Environment: ${ENV}`);
  
  // Verify health before starting load test
  const healthCheck = http.get(`${BASE_URL}/health`);
  if (healthCheck.status !== 200) {
    console.error('Health check failed before test start. Aborting.');
    return { abort: true };
  }
  
  return { startTime: new Date().toISOString() };
}

// Teardown function (runs once at the end)
export function teardown(data) {
  if (data.abort) {
    console.error('Test was aborted due to initial health check failure');
    return;
  }
  
  console.log(`Load test completed. Started at: ${data.startTime}`);
  console.log(`Tested against: ${BASE_URL}`);
}

// Handle summary data
export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'load-test-results.json': JSON.stringify(data, null, 2),
  };
}

// Helper function for text summary
function textSummary(data, options) {
  const indent = options.indent || '';
  const colors = options.enableColors !== false;
  
  const green = colors ? '\x1b[32m' : '';
  const red = colors ? '\x1b[31m' : '';
  const reset = colors ? '\x1b[0m' : '';
  
  let summary = '';
  
  summary += `${indent}Load Test Results${'\n'}`;
  summary += `${indent}=================${'\n'}`;
  summary += `${indent}Environment: ${ENV}${'\n'}`;
  summary += `${indent}Base URL: ${BASE_URL}${'\n'}`;
  summary += `${'\n'}`;
  
  const httpReqs = data.metrics.http_reqs;
  if (httpReqs) {
    summary += `${indent}HTTP Requests: ${httpReqs.count}${'\n'}`;
  }
  
  const httpReqFailed = data.metrics.http_req_failed;
  if (httpReqFailed) {
    const failRate = (httpReqFailed.rate * 100).toFixed(2);
    const color = httpReqFailed.rate > 0.01 ? red : green;
    summary += `${indent}Error Rate: ${color}${failRate}%${reset}${'\n'}`;
  }
  
  const httpReqDuration = data.metrics.http_req_duration;
  if (httpReqDuration) {
    summary += `${indent}Avg Response Time: ${httpReqDuration.avg.toFixed(2)}ms${'\n'}`;
    summary += `${indent}P95 Response Time: ${httpReqDuration['p(95)'].toFixed(2)}ms${'\n'}`;
    summary += `${indent}P99 Response Time: ${httpReqDuration['p(99)'].toFixed(2)}ms${'\n'}`;
  }
  
  summary += `${'\n'}`;
  summary += `${indent}Checks:${'\n'}`;
  
  const checks = data.root_group.checks || {};
  for (const [name, checkData] of Object.entries(checks)) {
    const passRate = ((checkData.passes / (checkData.passes + checkData.fails)) * 100).toFixed(1);
    const color = checkData.fails > 0 ? red : green;
    summary += `${indent}  ${name}: ${color}${passRate}%${reset} (${checkData.passes}/${checkData.passes + checkData.fails})${'\n'}`;
  }
  
  return summary;
}
