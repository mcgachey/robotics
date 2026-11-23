import { useCallback, useEffect, useState } from 'react';
import { Badge, Button, Code, Group, Modal, PasswordInput, Stack, Switch, Table, Text, TextInput, Title } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { Terminal, errorMessage, get, patch, post, type Job, type Student } from '@robotics/common';

interface Review {
  title: string;
  source: string;
  revisions: number[];
  revision: number;
  student: { name: string };
  lastBuildJob: Job | null;
  lastTestJob: Job | null;
}

function projectBadge(p: Student['projects'][string] | undefined) {
  if (!p) return <Badge color="gray" variant="light">not started</Badge>;
  const t = p.lastTest?.status;
  return (
    <Group gap={4}>
      <Badge variant="light">rev {p.revision}</Badge>
      {p.lastBuild && <Badge color={p.lastBuild.status === 'passed' ? 'green' : 'red'} variant="light">build {p.lastBuild.status}</Badge>}
      {t && <Badge color={t === 'passed' ? 'green' : 'red'} variant="light">test {t}</Badge>}
      {p.lastSubmit && <Badge color="teal">submitted rev {p.lastSubmit.revision}</Badge>}
    </Group>
  );
}

export function StudentsTab() {
  const [students, setStudents] = useState<Student[]>([]);
  const [lessons, setLessons] = useState<{ id: string; title: string }[]>([]);
  const [form, setForm] = useState({ name: '', username: '', password: '' });
  const [review, setReview] = useState<Review | null>(null);
  const [pwFor, setPwFor] = useState<Student | null>(null);
  const [newPw, setNewPw] = useState('');

  const load = useCallback(async () => {
    try {
      setStudents(await get<Student[]>('/api/instructor/students'));
      setLessons(await get('/api/instructor/lessons'));
    } catch (e) {
      notifications.show({ color: 'red', message: errorMessage(e) });
    }
  }, []);
  useEffect(() => void load(), [load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await post('/api/instructor/students', form);
      setForm({ name: '', username: '', password: '' });
      notifications.show({ color: 'green', message: `Created ${form.username}.` });
      await load();
    } catch (err) {
      notifications.show({ color: 'red', title: 'Cannot create student', message: errorMessage(err) });
    }
  };

  const toggle = async (s: Student, enabled: boolean) => {
    try {
      await patch(`/api/instructor/students/${s.id}`, { enabled });
      await load();
    } catch (err) {
      notifications.show({ color: 'red', message: errorMessage(err) });
    }
  };

  const resetPw = async () => {
    if (!pwFor) return;
    try {
      await patch(`/api/instructor/students/${pwFor.id}`, { password: newPw });
      notifications.show({ color: 'green', message: `New password set for ${pwFor.login}.` });
      setPwFor(null);
      setNewPw('');
    } catch (err) {
      notifications.show({ color: 'red', message: errorMessage(err) });
    }
  };

  const open = async (s: Student, lessonId: string) => {
    try {
      const r = await get<Review>(`/api/instructor/students/${s.id}/projects/${lessonId}`);
      setReview(r);
    } catch (err) {
      notifications.show({ color: 'red', message: errorMessage(err) });
    }
  };

  return (
    <Stack>
      <form onSubmit={create}>
        <Group align="flex-end">
          <TextInput label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} />
          <TextInput label="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.currentTarget.value })} />
          <PasswordInput label="Initial password" value={form.password} onChange={(e) => setForm({ ...form, password: e.currentTarget.value })} />
          <Button type="submit" disabled={!form.name || !form.username || !form.password}>Create student</Button>
        </Group>
      </form>
      <Table withTableBorder>
        <Table.Thead>
          <Table.Tr><Table.Th>Name</Table.Th><Table.Th>Username</Table.Th><Table.Th>Enabled</Table.Th><Table.Th>Projects</Table.Th><Table.Th /></Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {students.map((s) => (
            <Table.Tr key={s.id} data-testid="student-row">
              <Table.Td>{s.name}</Table.Td>
              <Table.Td>{s.login}</Table.Td>
              <Table.Td><Switch checked={s.enabled} onChange={(e) => toggle(s, e.currentTarget.checked)} aria-label={`Enable ${s.login}`} /></Table.Td>
              <Table.Td>
                <Stack gap={4}>
                  {lessons.map((l) => (
                    <Group key={l.id} gap="xs">
                      <Text size="sm" w={120} truncate>{l.title}</Text>
                      {projectBadge(s.projects[l.id])}
                      {s.projects[l.id] && <Button size="compact-xs" variant="subtle" onClick={() => open(s, l.id)}>Review</Button>}
                    </Group>
                  ))}
                </Stack>
              </Table.Td>
              <Table.Td><Button size="compact-xs" variant="default" onClick={() => setPwFor(s)}>Reset password</Button></Table.Td>
            </Table.Tr>
          ))}
          {students.length === 0 && <Table.Tr><Table.Td colSpan={5}><Text c="dimmed">No students yet.</Text></Table.Td></Table.Tr>}
        </Table.Tbody>
      </Table>

      <Modal opened={!!review} onClose={() => setReview(null)} size="xl" title={review ? `${review.student.name}: ${review.title}` : ''}>
        {review && (
          <Stack>
            <Text size="sm" c="dimmed">Working copy (revisions snapshotted so far: {review.revisions.join(', ') || 'none'})</Text>
            <Code block data-testid="review-source">{review.source}</Code>
            {review.lastBuildJob && <><Title order={6}>Latest build</Title><Terminal job={review.lastBuildJob} running={false} live="" height={100} /></>}
            {review.lastTestJob && <><Title order={6}>Latest test</Title><Terminal job={review.lastTestJob} running={false} live="" height={120} /></>}
          </Stack>
        )}
      </Modal>
      <Modal opened={!!pwFor} onClose={() => setPwFor(null)} title={pwFor ? `New password for ${pwFor.login}` : ''}>
        <Stack>
          <PasswordInput label="New password" value={newPw} onChange={(e) => setNewPw(e.currentTarget.value)} />
          <Button onClick={resetPw} disabled={newPw.length < 4}>Set password</Button>
        </Stack>
      </Modal>
    </Stack>
  );
}
