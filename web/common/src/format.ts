import type { Diagnostic, Job, TestResult } from './types';

export function statusColor(job: Pick<Job, 'status'> | null, running: boolean): string {
  if (running) return 'blue';
  switch (job?.status) {
    case 'passed':
      return 'green';
    case 'failed':
      return 'red';
    case 'cancelled':
      return 'gray';
    default:
      return 'gray';
  }
}

export function diagnosticLabel(d: Diagnostic): string {
  return `line ${d.line}: ${d.message}`;
}

export function testIcon(t: TestResult): string {
  return t.status === 'passed' ? '✔' : t.status === 'skipped' ? '–' : '✘';
}

export function testSummary(tests: TestResult[]): string {
  if (tests.length === 0) return 'No tests ran.';
  const ok = tests.filter((t) => t.status === 'passed').length;
  return `${ok} of ${tests.length} test${tests.length === 1 ? '' : 's'} passed`;
}

/** "3.2 s" from the job's timings (compile + tests), or '' when unknown. */
export function durationLabel(job: Pick<Job, 'durations'>): string {
  const d = job.durations ?? {};
  const ms = (d.compileMs ?? 0) + (d.testCompileMs ?? 0) + (d.testMs ?? 0);
  return ms > 0 ? `${(ms / 1000).toFixed(1)} s` : '';
}

export function kindLabel(job: Pick<Job, 'kind' | 'origin'>): string {
  const k = job.kind === 'build' ? 'Build' : 'Test';
  return job.origin === 'instructor-verify' ? `${k} (instructor check)` : k;
}
