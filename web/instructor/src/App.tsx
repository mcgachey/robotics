import { useEffect, useState } from 'react';
import { AppShell, Button, Center, Container, Group, Loader, Tabs, Text, Title } from '@mantine/core';
import { ColorSchemeToggle, LoginForm, get, post, type Me } from '@robotics/common';
import { LessonsTab } from './LessonsTab';
import { QueueTab } from './QueueTab';
import { StudentsTab } from './StudentsTab';

export function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  useEffect(() => {
    get<Me>('/api/me').then(setMe, () => setMe(null));
  }, []);

  if (me === undefined) return <Center mih="100vh"><Loader /></Center>;
  if (me === null || me.role !== 'instructor') return <LoginForm title="Instructor login" role="instructor" onLogin={setMe} />;

  const logout = async () => {
    await post('/api/logout').catch(() => {});
    setMe(null);
  };
  return (
    <AppShell header={{ height: 52 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Title order={4}>Robotics: Instructor</Title>
          <Group>
            <Text size="sm">{me.name}</Text>
            <Button variant="default" size="xs" onClick={logout}>Log out</Button>
            <ColorSchemeToggle />
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Container size="lg">
          <Tabs defaultValue="queue" keepMounted={false}>
            <Tabs.List mb="md">
              <Tabs.Tab value="queue">Queue</Tabs.Tab>
              <Tabs.Tab value="students">Students</Tabs.Tab>
              <Tabs.Tab value="lessons">Lessons</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="queue"><QueueTab /></Tabs.Panel>
            <Tabs.Panel value="students"><StudentsTab /></Tabs.Panel>
            <Tabs.Panel value="lessons"><LessonsTab /></Tabs.Panel>
          </Tabs>
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
