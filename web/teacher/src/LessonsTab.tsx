import { useCallback, useEffect, useState } from 'react';
import { Button, Group, NavLink, NumberInput, Stack, Text, Textarea, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { errorMessage, get, post, put, type LessonFull } from '@robotics/common';

const BLANK: LessonFull = { id: '', title: '', className: '', targetPhase: 1, apiVersion: 0, starter: '', tests: '' };

export function LessonsTab() {
  const [lessons, setLessons] = useState<LessonFull[]>([]);
  const [form, setForm] = useState<LessonFull>(BLANK);
  const [isNew, setIsNew] = useState(true);

  const load = useCallback(async () => {
    try {
      setLessons(await get<LessonFull[]>('/api/teacher/lessons'));
    } catch (e) {
      notifications.show({ color: 'red', message: errorMessage(e) });
    }
  }, []);
  useEffect(() => void load(), [load]);

  const save = async () => {
    try {
      const body = { title: form.title, className: form.className, starter: form.starter, tests: form.tests, targetPhase: form.targetPhase, apiVersion: form.apiVersion };
      if (isNew) await post('/api/teacher/lessons', { id: form.id, ...body });
      else await put(`/api/teacher/lessons/${form.id}`, body);
      notifications.show({ color: 'green', message: `Saved ${form.title}.` });
      setIsNew(false);
      await load();
    } catch (e) {
      notifications.show({ color: 'red', title: 'Cannot save lesson', message: errorMessage(e) });
    }
  };

  const set = (k: keyof LessonFull) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.currentTarget.value });

  return (
    <Group align="flex-start" wrap="nowrap">
      <Stack gap={0} w={220}>
        <Button variant="light" mb="xs" onClick={() => { setForm(BLANK); setIsNew(true); }}>New lesson</Button>
        {lessons.map((l) => (
          <NavLink key={l.id} label={l.title} active={!isNew && form.id === l.id} onClick={() => { setForm(l); setIsNew(false); }} />
        ))}
        {lessons.length === 0 && <Text size="sm" c="dimmed">No lessons yet.</Text>}
      </Stack>
      <Stack style={{ flex: 1 }}>
        <Group grow>
          <TextInput label="Id" description="lowercase letters, digits, -" disabled={!isNew} value={form.id} onChange={set('id')} />
          <TextInput label="Title" value={form.title} onChange={set('title')} />
          <TextInput label="Class name" description="the student's class, e.g. HelloWorld" disabled={!isNew} value={form.className} onChange={set('className')} />
        </Group>
        <Group>
          <NumberInput label="Target phase" w={120} min={1} value={form.targetPhase} onChange={(v) => setForm({ ...form, targetPhase: Number(v) || 1 })} />
          <NumberInput label="API version" w={120} min={0} value={form.apiVersion} onChange={(v) => setForm({ ...form, apiVersion: Number(v) || 0 })} />
        </Group>
        <Textarea label="Starter code" autosize minRows={8} maxRows={18} styles={{ input: { fontFamily: 'monospace' } }} value={form.starter} onChange={set('starter')} />
        <Textarea label={`Tests (JUnit 4, class ${form.className ? form.className + 'Test' : '<ClassName>Test'})`} autosize minRows={8} maxRows={18}
          styles={{ input: { fontFamily: 'monospace' } }} value={form.tests} onChange={set('tests')} />
        <Group>
          <Button onClick={save} disabled={!form.id || !form.title || !form.className}>{isNew ? 'Create lesson' : 'Save changes'}</Button>
          {!isNew && <Text size="sm" c="dimmed">Changing the starter does not affect projects students have already opened.</Text>}
        </Group>
      </Stack>
    </Group>
  );
}
