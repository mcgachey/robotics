import { useCallback, useEffect, useRef, useState } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import { Badge, Button, Group, Loader, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { Terminal, errorMessage, get, post, put, useJobStream, type Diagnostic, type Job, type Project, type ProjectState } from '@robotics/common';
import { monaco } from './monacoSetup';

type SaveState = 'saved' | 'dirty' | 'saving' | 'error';
const SAVE_DEBOUNCE_MS = 700;

export function LessonView({ lessonId }: { lessonId: string }) {
  const base = `/api/me/projects/${lessonId}`;
  const [project, setProject] = useState<ProjectState | null>(null);
  const [title, setTitle] = useState('');
  const [initial, setInitial] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>('saved');
  const [canSubmit, setCanSubmit] = useState(false);
  const [loadError, setLoadError] = useState('');

  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const textRef = useRef('');
  const versionRef = useRef(0); // bumped on every edit
  const dirtyRef = useRef(false); // edits not yet saved
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const refreshState = useCallback(async () => {
    const p = await get<Project>(base);
    setProject(p);
    setCanSubmit(p.canSubmit && !dirtyRef.current); // unsaved edits mean the tested code is out of date
    return p;
  }, [base]);

  const showMarkers = useCallback((job: Job | null) => {
    const model = editorRef.current?.getModel();
    if (!model) return;
    monaco.editor.setModelMarkers(
      model,
      'javac',
      (job?.diagnostics ?? []).map((d) => ({
        severity: d.severity === 'error' ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
        message: d.message,
        startLineNumber: d.line,
        startColumn: d.column,
        endLineNumber: d.line,
        endColumn: model.getLineMaxColumn(Math.min(d.line, model.getLineCount())),
      })),
    );
  }, []);

  const stream = useJobStream(
    useCallback(
      (job: Job) => {
        showMarkers(job);
        refreshState().catch(() => {});
      },
      [showMarkers, refreshState],
    ),
  );

  // Load the project (created from the lesson's starter on first open).
  useEffect(() => {
    let cancelled = false;
    get<Project>(base).then(
      (p) => {
        if (cancelled) return;
        setProject(p);
        setTitle(p.title);
        setInitial(p.source);
        textRef.current = p.source;
        setCanSubmit(p.canSubmit);
        if (p.activeJobId) stream.attach(p.activeJobId); // a job was running when the page was reloaded
      },
      (e) => !cancelled && setLoadError(errorMessage(e)),
    );
    return () => {
      cancelled = true;
      clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  const save = useCallback(async () => {
    clearTimeout(timer.current);
    timer.current = undefined;
    const version = versionRef.current;
    setSaveState('saving');
    try {
      const st = await put<ProjectState>(`${base}/source`, { source: textRef.current });
      if (versionRef.current === version) {
        dirtyRef.current = false;
        setSaveState('saved');
        setProject((p) => (p ? { ...p, ...st } : p));
        setCanSubmit(st.canSubmit);
      }
    } catch (e) {
      setSaveState('error');
      notifications.show({ color: 'red', title: 'Could not save', message: errorMessage(e) });
    }
  }, [base]);

  const onChange = (value: string | undefined) => {
    textRef.current = value ?? '';
    versionRef.current += 1;
    dirtyRef.current = true;
    setSaveState('dirty');
    setCanSubmit(false);
    showMarkers(null); // line numbers have moved on
    clearTimeout(timer.current);
    timer.current = setTimeout(save, SAVE_DEBOUNCE_MS);
  };

  const start = async (kind: 'build' | 'test') => {
    try {
      if (dirtyRef.current) await save(); // the job compiles what the server has saved
      const { jobId } = await post<{ jobId: string }>(`${base}/${kind}`);
      showMarkers(null);
      stream.attach(jobId);
    } catch (e) {
      notifications.show({ color: 'red', title: kind === 'build' ? 'Cannot build' : 'Cannot test', message: errorMessage(e) });
    }
  };

  const stop = async () => {
    if (!stream.jobId) return;
    try {
      await post(`/api/me/jobs/${stream.jobId}/stop`);
    } catch (e) {
      notifications.show({ color: 'red', message: errorMessage(e) });
    }
  };

  const submit = async () => {
    try {
      const entry = await post<{ revision: number }>(`${base}/submit`);
      notifications.show({ color: 'green', title: 'Submitted', message: `Your teacher can now see revision ${entry.revision}.` });
      await refreshState();
    } catch (e) {
      notifications.show({ color: 'red', title: 'Cannot submit', message: errorMessage(e) });
    }
  };

  const goto = (d: Diagnostic) => {
    const ed = editorRef.current;
    if (!ed) return;
    ed.revealLineInCenter(d.line);
    ed.setPosition({ lineNumber: d.line, column: d.column });
    ed.focus();
  };

  if (loadError) return <Text c="red" p="md">{loadError}</Text>;
  if (initial === null || !project) return <Loader m="md" />;

  const running = stream.running;
  const submitted = project.lastSubmit;
  return (
    <Stack gap={0} h="calc(100vh - 52px)">
      <Group px="md" py={6} justify="space-between" wrap="nowrap">
        <Group gap="xs">
          <Button onClick={() => start('build')} disabled={running} data-testid="build">Build</Button>
          <Button onClick={() => start('test')} disabled={running} variant="light" data-testid="test">Test</Button>
          <Button onClick={submit} disabled={running || !canSubmit} color="green" data-testid="submit"
            title={canSubmit ? '' : 'Submit unlocks after a passing Test of your current code'}>
            Submit
          </Button>
          <Button onClick={stop} disabled={!running} color="red" variant="outline" data-testid="stop">Stop</Button>
        </Group>
        <Group gap="xs">
          {submitted && <Badge color="green" variant="light">Submitted revision {submitted.revision}</Badge>}
          <Text size="sm" c="dimmed">{title}</Text>
          <Text size="sm" data-testid="save-state" c={saveState === 'error' ? 'red' : 'dimmed'}>
            {{ saved: '✓ Saved', saving: 'Saving…', dirty: 'Unsaved changes…', error: 'Not saved!' }[saveState]}
          </Text>
        </Group>
      </Group>
      <div style={{ flex: 1, minHeight: 0, borderTop: '1px solid var(--mantine-color-gray-3)' }}>
        <Editor
          height="100%"
          language="java"
          defaultValue={initial}
          onChange={onChange}
          onMount={(ed) => {
            editorRef.current = ed;
          }}
          options={{ minimap: { enabled: false }, fontSize: 15, scrollBeyondLastLine: false, automaticLayout: true, tabSize: 4 }}
        />
      </div>
      <div style={{ padding: 8 }}>
        <Terminal job={stream.job} running={running} live={stream.live} onGoto={goto} />
      </div>
    </Stack>
  );
}
