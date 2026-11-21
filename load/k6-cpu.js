// Constant-arrival-rate load on the CPU endpoint (used by E3).
// Each request does a fixed ~50 ms of CPU work, so 7 req/s ~= 350 millicores of demand,
// i.e. 3.5x the 100m request of one pod (70% of its 500m limit).
import http from 'k6/http';

const RATE = __ENV.RATE ? parseInt(__ENV.RATE) : 7;
const DURATION = __ENV.DURATION || '180s';
const TARGET = __ENV.TARGET || 'http://sen421-control-plane:30080';

export const options = {
  discardResponseBodies: true,
  scenarios: {
    cpu: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
};

export default function () {
  http.get(`${TARGET}/cpu`, { timeout: '10s' });
}
