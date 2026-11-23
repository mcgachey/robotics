import { useEffect, useState } from 'react';
import { AppShell, Button, Group, Loader, Select, Text, Title, Center } from '@mantine/core';
import { LoginForm, errorMessage, get, post, type Lesson, type Me } from '@robotics/common';
import { LessonView } from './LessonView';

export function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined); // undefined = still checking
  useEffect(() => {
    get<Me>('/api/me').then(setMe, () => setMe(null));
  }, []);

  if (me === undefined) return <Center mih="100vh"><Loader /></Center>;
  if (me === null || me.role !== 'student') {
    return <LoginForm title="Robotics IDE" role="student" onLogin={setMe} />;
  }
  return <Shell me={me} onLogout={() => setMe(null)} />;
}

function Shell({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [lessons, setLessons] = useState<Lesson[] | null>(null);
  const [lessonId, setLessonId] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    get<Lesson[]>('/api/lessons').then(
      (ls) => {
        setLessons(ls);
        setLessonId(ls[0]?.id ?? null); // single entry for now: open it straight away
      },
      (e) => setError(errorMessage(e)),
    );
  }, []);

  const logout = async () => {
    await post('/api/logout').catch(() => {});
    onLogout();
  };

  return (
    <AppShell header={{ height: 52 }} padding={0}>
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Title order={4}>Robotics IDE</Title>
            {lessons && lessons.length > 0 && (
              <Select
                aria-label="Lesson"
                data={lessons.map((l) => ({ value: l.id, label: l.title }))}
                value={lessonId}
                onChange={setLessonId}
                allowDeselect={false}
                w={260}
              />
            )}
          </Group>
          <Group>
            <Text size="sm">{me.name}</Text>
            <Button variant="default" size="xs" onClick={logout}>Log out</Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        {error && <Text c="red" p="md">{error}</Text>}
        {lessons && lessons.length === 0 && <Text p="md">No lessons yet. Ask your teacher to create one.</Text>}
        {lessonId && <LessonView key={lessonId} lessonId={lessonId} />}
      </AppShell.Main>
    </AppShell>
  );
}
