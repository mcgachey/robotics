import { describe, expect, it } from 'vitest';
import { ApiError, api } from './api';
import { diagnosticLabel, durationLabel, kindLabel, statusColor, testSummary } from './format';
import type { Diagnostic } from './types';

describe('format', () => {
  it('labels diagnostics with their line', () => {
    const d = { line: 6, message: 'A semicolon (;) is missing.' } as Diagnostic;
    expect(diagnosticLabel(d)).toBe('line 6: A semicolon (;) is missing.');
  });
  it('summarises tests', () => {
    expect(testSummary([])).toBe('No tests ran.');
    expect(testSummary([{ name: 'a', status: 'passed', message: '' }, { name: 'b', status: 'failed', message: 'x' }])).toBe(
      '1 of 2 tests passed',
    );
  });
  it('sums durations', () => {
    expect(durationLabel({ durations: { compileMs: 1200, testMs: 800 } })).toBe('2.0 s');
    expect(durationLabel({ durations: {} })).toBe('');
  });
  it('colours and kinds', () => {
    expect(statusColor({ status: 'passed' }, false)).toBe('green');
    expect(statusColor({ status: 'passed' }, true)).toBe('blue');
    expect(kindLabel({ kind: 'test', origin: 'instructor-verify' })).toBe('Test (instructor check)');
  });
});

describe('api', () => {
  it('turns server errors into ApiError with the friendly message', async () => {
    globalThis.fetch = (async () => new Response(JSON.stringify({ error: 'Please log in.' }), { status: 401 })) as typeof fetch;
    await expect(api('GET', '/api/me')).rejects.toMatchObject({ status: 401, message: 'Please log in.' });
    await expect(api('GET', '/api/me')).rejects.toBeInstanceOf(ApiError);
  });
  it('reports an unreachable server', async () => {
    globalThis.fetch = (async () => {
      throw new TypeError('network');
    }) as typeof fetch;
    await expect(api('GET', '/x')).rejects.toMatchObject({ status: 0 });
  });
});
