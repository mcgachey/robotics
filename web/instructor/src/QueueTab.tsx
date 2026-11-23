import { useCallback, useEffect, useState } from 'react';
import { Button, Group, Stack, Table, Text, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { Terminal, errorMessage, get, post, useJobStream, type QueueEntry } from '@robotics/common';

export function QueueTab() {
  const [entries, setEntries] = useState<QueueEntry[]>([]);
  const [checking, setChecking] = useState<QueueEntry | null>(null);
  const stream = useJobStream();

  const load = useCallback(async () => {
    try {
      setEntries(await get<QueueEntry[]>('/api/instructor/queue'));
    } catch (e) {
      notifications.show({ color: 'red', message: errorMessage(e) });
    }
  }, []);
  useEffect(() => {
    void load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  // Build / Test run the same service as the student's, on the pinned revision.
  const verify = async (e: QueueEntry, kind: 'build' | 'test') => {
    try {
      const { jobId } = await post<{ jobId: string }>(`/api/instructor/queue/${e.key}/${kind}`);
      setChecking(e);
      stream.attach(jobId);
    } catch (err) {
      notifications.show({ color: 'red', title: `Cannot ${kind}`, message: errorMessage(err) });
    }
  };

  const stop = async () => {
    if (stream.jobId) await post(`/api/instructor/jobs/${stream.jobId}/stop`).catch(() => {});
  };

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={5}>Submissions</Title>
        <Button size="xs" variant="default" onClick={load}>Refresh</Button>
      </Group>
      <Table withTableBorder>
        <Table.Thead>
          <Table.Tr><Table.Th>#</Table.Th><Table.Th>Student</Table.Th><Table.Th>Lesson</Table.Th><Table.Th>Revision</Table.Th><Table.Th>Submitted</Table.Th><Table.Th /></Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {entries.map((e, i) => (
            <Table.Tr key={e.key} data-testid="queue-row">
              <Table.Td>{i + 1}</Table.Td>
              <Table.Td>{e.studentName} <Text span c="dimmed" size="xs">({e.studentLogin})</Text></Table.Td>
              <Table.Td>{e.lessonTitle}</Table.Td>
              <Table.Td>{e.revision}</Table.Td>
              <Table.Td>{new Date(e.submittedAt).toLocaleString()}</Table.Td>
              <Table.Td>
                <Group gap="xs">
                  <Button size="compact-sm" onClick={() => verify(e, 'build')} disabled={stream.running} data-testid="verify-build">Build</Button>
                  <Button size="compact-sm" variant="light" onClick={() => verify(e, 'test')} disabled={stream.running} data-testid="verify-test">Test</Button>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
          {entries.length === 0 && <Table.Tr><Table.Td colSpan={6}><Text c="dimmed">No submissions yet.</Text></Table.Td></Table.Tr>}
        </Table.Tbody>
      </Table>
      {checking && (
        <Stack gap={4}>
          <Group justify="space-between">
            <Text size="sm">Checking {checking.studentName}'s {checking.lessonTitle}, revision {checking.revision}</Text>
            <Button size="compact-xs" color="red" variant="outline" disabled={!stream.running} onClick={stop}>Stop</Button>
          </Group>
          <Terminal job={stream.job} running={stream.running} live={stream.live} height={240} />
        </Stack>
      )}
    </Stack>
  );
}
