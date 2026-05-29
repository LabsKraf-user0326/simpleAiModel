// Spike test: 5 VUs → jump to 100 VUs almost instantly → drop back to 5.
// Goal: see whether the API survives a sudden burst and recovers afterwards.
//
// Run:  k6 run k6/spike.js
// Env:  BASE_URL (default http://localhost:5000)

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5000';

const predictDuration = new Trend('predict_duration', true);
const predictErrors = new Counter('predict_errors');
const recoveryErrors = new Counter('recovery_errors'); // failures during the post-spike window

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
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 5 },    // baseline
        { duration: '5s',  target: 100 },  // SPIKE — near-instant burst
        { duration: '60s', target: 100 },  // sustain spike
        { duration: '5s',  target: 5 },    // drop back fast
        { duration: '45s', target: 5 },    // recovery window
        { duration: '5s',  target: 0 },
      ],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    // Spike thresholds are intentionally looser than the ramp-up test.
    http_req_failed: ['rate<0.20'],     // tolerate up to 20% failures during the burst
    http_req_duration: ['p(95)<5000'],  // p95 under 5s
    'predict_duration': ['p(95)<5000'],
  },
};

// Stage boundaries (in seconds from test start). Used to tag the recovery window.
const RECOVERY_START_S = 20 + 5 + 60 + 5;          // 90s
const RECOVERY_END_S   = RECOVERY_START_S + 45;     // 135s
const testStart = Date.now();

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
  if (!ok) {
    predictErrors.add(1);
    const elapsed = (Date.now() - testStart) / 1000;
    if (elapsed >= RECOVERY_START_S && elapsed <= RECOVERY_END_S) {
      recoveryErrors.add(1);
    }
  }

  sleep(0.1);
}

export function handleSummary(data) {
  return {
    'reports/spike-summary.json': JSON.stringify(data, null, 2),
    'reports/spike-summary.txt': textSummary(data, { indent: ' ', enableColors: false }),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}
