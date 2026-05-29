// Ramp-up test: gradually increase virtual users from 1 → 10 → 50.
// Goal: find the load level where /predict starts to slow down.
//
// Run:  k6 run k6/ramp-up.js
// Env:  BASE_URL (default http://localhost:5000)

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5000';

const predictDuration = new Trend('predict_duration', true);
const predictErrors = new Counter('predict_errors');

const TASKS = [
  'Fix production outage in payments service',
  'Patch critical security vulnerability in auth module',
  'Prepare quarterly business review deck',
  'Review pull request from teammate on billing service',
  'Read newsletter from cloud provider',
  'Watch recorded conference talk on distributed systems',
  'Schedule onboarding session for new hire',
  'Hotfix login bug blocking all users',
  'Refactor user service to use new logger',
  'Browse engineering blog posts saved earlier',
];

export const options = {
  scenarios: {
    ramp_up: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 1 },   // warm up at 1 VU
        { duration: '30s', target: 1 },   // hold at 1 VU
        { duration: '20s', target: 10 },  // ramp to 10 VUs
        { duration: '30s', target: 10 },  // hold at 10 VUs
        { duration: '20s', target: 50 },  // ramp to 50 VUs
        { duration: '60s', target: 50 },  // hold at 50 VUs
        { duration: '20s', target: 0 },   // ramp down
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],          // <2% failures overall
    http_req_duration: ['p(95)<1500'],       // 95% of requests under 1.5s
    'predict_duration': ['p(95)<1500'],
  },
};

export default function () {
  const task = TASKS[Math.floor(Math.random() * TASKS.length)];
  const res = http.post(
    `${BASE_URL}/predict`,
    JSON.stringify({ task }),
    { headers: { 'content-type': 'application/json' }, tags: { endpoint: 'predict' } },
  );

  const ok = check(res, {
    'status is 200': (r) => r.status === 200,
    'has priority': (r) => {
      try { return ['High', 'Medium', 'Low'].includes(r.json('priority')); }
      catch (_) { return false; }
    },
  });

  predictDuration.add(res.timings.duration);
  if (!ok) predictErrors.add(1);

  sleep(0.2); // small think-time between requests
}

export function handleSummary(data) {
  return {
    'reports/ramp-up-summary.json': JSON.stringify(data, null, 2),
    'reports/ramp-up-summary.txt': textSummary(data, { indent: ' ', enableColors: false }),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}
