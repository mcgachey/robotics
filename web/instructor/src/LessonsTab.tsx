import { useCallback, useEffect, useState } from 'react';
import { Badge, Button, Table, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { errorMessage, get, patch, type Lesson } from '@robotics/common';

// Lessons are defined in the repo (lessons/<id>/). The instructor only decides which ones students can see.
export function LessonsTab() {
  const [lessons, setLessons] = useState<Lesson[]>([]);

  const load = useCallback(async () => {
    try {
      setLessons(await get<Lesson[]>('/api/instructor/lessons'));
    } catch (e) {
      notifications.show({ color: 'red', message: errorMessage(e) });
    }
  }, []);
  useEffect(() => void load(), [load]);

  const toggle = async (l: Lesson) => {
    try {
      await patch(`/api/instructor/lessons/${l.id}`, { enabled: !l.enabled });
      notifications.show({ color: 'green', message: `${l.title} is now ${l.enabled ? 'hidden from' : 'available to'} students.` });
      await load();
    } catch (e) {
      notifications.show({ color: 'red', title: 'Cannot change lesson', message: errorMessage(e) });
    }
  };

  return (
    <>
      <Text size="sm" c="dimmed" mb="sm">
        Lessons are defined in the project's source code. Enable a lesson to make it available to students.
        Disabling one hides it but keeps students' work.
      </Text>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Lesson</Table.Th><Table.Th>Id</Table.Th><Table.Th>Class</Table.Th>
            <Table.Th>Phase</Table.Th><Table.Th>API</Table.Th><Table.Th>Status</Table.Th><Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {lessons.map((l) => (
            <Table.Tr key={l.id} data-testid="lesson-row">
              <Table.Td>{l.title}</Table.Td>
              <Table.Td>{l.id}</Table.Td>
              <Table.Td>{l.className}</Table.Td>
              <Table.Td>{l.targetPhase}</Table.Td>
              <Table.Td>{l.apiVersion}</Table.Td>
              <Table.Td><Badge color={l.enabled ? 'green' : 'gray'}>{l.enabled ? 'Enabled' : 'Disabled'}</Badge></Table.Td>
              <Table.Td>
                <Button size="compact-sm" variant={l.enabled ? 'default' : 'filled'} onClick={() => toggle(l)}>
                  {l.enabled ? 'Disable' : 'Enable'}
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
          {lessons.length === 0 && <Table.Tr><Table.Td colSpan={7}><Text c="dimmed">No lessons are defined in the source tree.</Text></Table.Td></Table.Tr>}
        </Table.Tbody>
      </Table>
    </>
  );
}
