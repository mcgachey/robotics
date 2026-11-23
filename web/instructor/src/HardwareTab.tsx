import { useCallback, useEffect, useState } from 'react';
import { Alert, Badge, Button, Card, Group, Select, Stack, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  Terminal,
  api,
  errorMessage,
  get,
  post,
  useJobStream,
  type Hardware,
  type HardwareDroid,
  type HardwareStudent,
} from '@robotics/common';

/** What the instructor has picked for one droid: a student and "lessonId:revision". */
interface Pick {
  studentId: string | null;
  build: string | null;
}

const buildKey = (lessonId: string, revision: number) => `${lessonId}:${revision}`;

function buildOptions(student: HardwareStudent | undefined) {
  return (student?.builds ?? []).map((b) => ({
    value: buildKey(b.lessonId, b.revision),
    label: `${b.lessonTitle}, revision ${b.revision}`,
  }));
}

export function HardwareTab() {
  const [hw, setHw] = useState<Hardware | null>(null);
  const [picks, setPicks] = useState<Record<string, Pick>>({});
  const [viewing, setViewing] = useState<HardwareDroid | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const stream = useJobStream();

  const load = useCallback(async () => {
    try {
      setHw(await get<Hardware>('/api/instructor/hardware'));
    } catch (e) {
      notifications.show({ color: 'red', message: errorMessage(e) });
    }
  }, []);
  useEffect(() => {
    void load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);
  // Refresh as soon as a run ends so the Stop button and run state settle.
  useEffect(() => {
    if (!stream.running) void load();
  }, [stream.running, load]);

  /** The pick shown for a droid: what the instructor chose, else what is assigned to it now. */
  const pickFor = (d: HardwareDroid): Pick =>
    picks[d.id] ?? {
      studentId: d.assignment?.studentId ?? null,
      build: d.assignment ? buildKey(d.assignment.lessonId, d.assignment.revision) : null,
    };
  const setPick = (id: string, p: Pick) => setPicks((all) => ({ ...all, [id]: p }));

  const chooseStudent = (d: HardwareDroid, studentId: string | null) => {
    const student = hw?.students.find((s) => s.id === studentId);
    const latest = student?.builds[0]; // builds are newest first: default to the latest
    setPick(d.id, { studentId, build: latest ? buildKey(latest.lessonId, latest.revision) : null });
  };

  const act = async (d: HardwareDroid, what: string, fn: () => Promise<void>) => {
    setBusy(d.id);
    try {
      await fn();
    } catch (e) {
      notifications.show({ color: 'red', title: `Cannot ${what}`, message: errorMessage(e) });
    } finally {
      setBusy(null);
      void load();
    }
  };

  const deploy = (d: HardwareDroid) =>
    act(d, 'deploy', async () => {
      const p = pickFor(d);
      if (!p.studentId || !p.build) return;
      const [lessonId, rev] = p.build.split(':');
      const { jobId } = await post<{ jobId: string }>(`/api/instructor/hardware/${d.id}/deploy`, {
        studentId: p.studentId,
        lessonId,
        revision: Number(rev),
      });
      setViewing(d);
      stream.attach(jobId);
    });

  const stop = (d: HardwareDroid) => act(d, 'stop', async () => void (await post(`/api/instructor/hardware/${d.id}/stop`)));
  const clear = (d: HardwareDroid) =>
    act(d, 'clear', async () => {
      await api('DELETE', `/api/instructor/hardware/${d.id}/assignment`);
      setPicks((all) => {
        const { [d.id]: _gone, ...rest } = all;
        return rest;
      });
    });

  const watch = (d: HardwareDroid) => {
    const jobId = d.run?.jobId ?? d.assignment?.jobId;
    if (!jobId) return;
    setViewing(d);
    stream.attach(jobId);
  };

  if (!hw) return <Text c="dimmed">Loading…</Text>;
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={5}>Droids</Title>
        <Button size="xs" variant="default" onClick={load}>Refresh</Button>
      </Group>
      {!hw.controller.ok && (
        <Alert color="red" title="Board controller unavailable" data-testid="controller-error">
          {hw.controller.error}
        </Alert>
      )}
      {hw.controller.ok && hw.droids.length === 0 && (
        <Text c="dimmed">No droid boards found. Plug one in over USB, then use <b>Scan for boards</b> in the controller (port 5050).</Text>
      )}
      {hw.droids.map((d) => {
        const p = pickFor(d);
        const student = hw.students.find((s) => s.id === p.studentId);
        const running = !!d.run;
        const options = buildOptions(student);
        const assigned = d.assignment;
        return (
          <Card key={d.id} withBorder padding="sm" data-testid="droid-card">
            <Group justify="space-between" mb="xs">
              <Group gap="xs">
                <Text fw={600}>{d.name}</Text>
                <Badge color={d.online ? 'green' : 'gray'} variant="light">{d.online ? 'online' : 'offline'}</Badge>
                {running && <Badge color="blue" data-testid="running-badge">running</Badge>}
                {d.firmware && <Text size="xs" c="dimmed">firmware {d.firmware}</Text>}
              </Group>
              <Text size="xs" c="dimmed">{d.id}</Text>
            </Group>
            <Text size="sm" mb="xs" data-testid="assignment">
              {assigned
                ? <>Assigned: <b>{assigned.studentName}</b>, {assigned.lessonTitle}, revision {assigned.revision}</>
                : <Text span c="dimmed">No student's code assigned.</Text>}
            </Text>
            <Group align="flex-end" gap="xs">
              <Select
                label="Student"
                placeholder={hw.students.length ? 'Choose a student' : 'No built code yet'}
                data={hw.students.map((s) => ({ value: s.id, label: s.name }))}
                value={p.studentId}
                onChange={(v) => chooseStudent(d, v)}
                disabled={running}
                searchable
                w={200}
                data-testid="student-select"
              />
              <Select
                label="Revision"
                placeholder="Choose a revision"
                data={options}
                value={p.build}
                onChange={(v) => setPick(d.id, { studentId: p.studentId, build: v })}
                disabled={running || !student}
                allowDeselect={false}
                w={260}
                data-testid="revision-select"
              />
              <Button
                onClick={() => deploy(d)}
                disabled={!d.online || running || !p.studentId || !p.build}
                loading={busy === d.id}
                data-testid="deploy"
              >
                Deploy
              </Button>
              <Button color="red" variant="outline" onClick={() => stop(d)} disabled={busy === d.id} data-testid="stop">
                Stop
              </Button>
              <Button variant="subtle" onClick={() => watch(d)} disabled={!d.run && !assigned}>Output</Button>
              <Button variant="subtle" color="gray" onClick={() => clear(d)} disabled={running || !assigned}>Clear</Button>
            </Group>
          </Card>
        );
      })}
      {viewing && stream.jobId && (
        <Stack gap={4}>
          <Text size="sm">Output from {viewing.name}</Text>
          <Terminal job={stream.job} running={stream.running} live={stream.live} height={240} />
        </Stack>
      )}
    </Stack>
  );
}
