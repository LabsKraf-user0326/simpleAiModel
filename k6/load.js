// Generic load test — every knob comes from environment variables so the
// dashboard can drive it without regenerating the script.
//
// Required:
//   TARGET_URL   — full URL to hit
//   STAGES_JSON  — JSON array of {duration, target} for ramping-vus
//
// Optional:
//   METHOD          (default GET)
//   HEADERS_JSON    JSON object of header → value      (default {})
//   BODY            request body string                (default none)
//   THINK_MS        per-iteration sleep in ms          (default 100)
//   P95_THRESHOLD   max acceptable p95 latency in ms   (default 5000)
//   FAIL_THRESHOLD  max acceptable failure rate (0..1) (default 0.50)

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.1.0/index.js';

const TARGET_URL  = __ENV.TARGET_URL;
const METHOD      = (__ENV.METHOD || 'GET').toUpperCase();
const HEADERS     = __ENV.HEADERS_JSON ? JSON.parse(__ENV.HEADERS_JSON) : {};
const BODY        = __ENV.BODY || null;
const STAGES      = JSON.parse(__ENV.STAGES_JSON);
const THINK_MS    = Number(__ENV.THINK_MS || 100);
const P95_MAX     = Number(__ENV.P95_THRESHOLD  || 5000);
const FAIL_MAX    = Number(__ENV.FAIL_THRESHOLD || 0.50);

if (!TARGET_URL) throw new Error('TARGET_URL is required');
if (!Array.isArray(STAGES) || STAGES.length === 0) {
  throw new Error('STAGES_JSON must be a non-empty array');
}

export const options = {
  scenarios: {
    custom_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: STAGES,
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    http_req_failed:   [`rate<${FAIL_MAX}`],
    http_req_duration: [`p(95)<${P95_MAX}`],
  },
  // Make p(99) available in the JSON summary the dashboard reads.
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

const reqDuration = new Trend('req_duration', true);
const reqErrors   = new Counter('req_errors');

export default function () {
  const params = { headers: HEADERS, tags: { endpoint: 'custom' } };
  const body = (METHOD === 'GET' || METHOD === 'HEAD') ? null : BODY;
  const res = http.request(METHOD, TARGET_URL, body, params);

  const ok = check(res, {
    'status 2xx': (r) => r.status >= 200 && r.status < 300,
  });
  reqDuration.add(res.timings.duration);
  if (!ok) reqErrors.add(1);

  if (THINK_MS > 0) sleep(THINK_MS / 1000);
}

export function handleSummary(data) {
  return {
    'reports/load-summary.json': JSON.stringify(data, null, 2),
    'reports/load-summary.txt':  textSummary(data, { indent: ' ', enableColors: false }),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}
