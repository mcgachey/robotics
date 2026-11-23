import { useCallback, useEffect, useRef, useState } from 'react';
import { get } from './api';
import type { Job } from './types';

export interface JobStreamState {
  jobId: string | null;
  running: boolean;
  /** Raw output so far, while running. */
  live: string;
  /** The finished job, with its full output. */
  job: Job | null;
}

const IDLE: JobStreamState = { jobId: null, running: false, live: '', job: null };

/** Follow a job's server-sent events; falls back to polling if the stream breaks. */
export function useJobStream(onDone?: (job: Job) => void) {
  const [state, setState] = useState<JobStreamState>(IDLE);
  const closer = useRef<() => void>(() => {});
  const doneCb = useRef(onDone);
  doneCb.current = onDone;

  const detach = useCallback(() => {
    closer.current();
    closer.current = () => {};
  }, []);

  const attach = useCallback(
    (jobId: string) => {
      detach();
      setState({ jobId, running: true, live: '', job: null });
      let finished = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      let es: EventSource | undefined;

      const finish = async () => {
        if (finished) return;
        finished = true;
        es?.close();
        try {
          const job = await get<Job>(`/api/jobs/${jobId}`);
          setState((s) => (s.jobId === jobId ? { ...s, running: false, job } : s));
          doneCb.current?.(job);
        } catch {
          setState((s) => (s.jobId === jobId ? { ...s, running: false } : s));
        }
      };

      const poll = async () => {
        if (finished) return;
        try {
          const job = await get<Job>(`/api/jobs/${jobId}`);
          if (job.status !== 'running') return void finish();
          setState((s) => (s.jobId === jobId ? { ...s, live: job.output ?? s.live } : s));
        } catch {
          /* keep trying */
        }
        timer = setTimeout(poll, 1000);
      };

      es = new EventSource(`/api/jobs/${jobId}/events`);
      const append = (text: string) => setState((s) => (s.jobId === jobId ? { ...s, live: s.live + text } : s));
      es.addEventListener('output', (ev) => append((JSON.parse((ev as MessageEvent).data) as { text: string }).text));
      es.addEventListener('status', (ev) =>
        append(`== ${(JSON.parse((ev as MessageEvent).data) as { text: string }).text}\n`),
      );
      es.addEventListener('done', () => void finish());
      es.onerror = () => {
        if (finished) return;
        es?.close();
        timer = setTimeout(poll, 500);
      };
      closer.current = () => {
        finished = true;
        es?.close();
        if (timer) clearTimeout(timer);
      };
    },
    [detach],
  );

  const reset = useCallback(() => {
    detach();
    setState(IDLE);
  }, [detach]);

  useEffect(() => detach, [detach]);
  return { ...state, attach, reset };
}
