import { useState } from 'react';
import { Alert, Button, Center, Paper, PasswordInput, Stack, TextInput, Title } from '@mantine/core';
import { errorMessage, post } from './api';
import type { Me, Role } from './types';

export function LoginForm({ title, role, onLogin }: { title: string; role: Role; onLogin: (me: Me) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const me = await post<Me>('/api/login', { username, password });
      if (me.role !== role) {
        await post('/api/logout');
        setError(role === 'teacher' ? 'That is not a teacher account.' : 'Teachers: use the teacher page.');
      } else {
        onLogin(me);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Center mih="100vh">
      <Paper withBorder shadow="sm" p="xl" w={340}>
        <form onSubmit={submit}>
          <Stack>
            <Title order={3}>{title}</Title>
            <TextInput label="Username" autoFocus autoComplete="username" value={username}
              onChange={(e) => setUsername(e.currentTarget.value)} />
            <PasswordInput label="Password" autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.currentTarget.value)} />
            {error && <Alert color="red" data-testid="login-error">{error}</Alert>}
            <Button type="submit" loading={busy} disabled={!username || !password}>Log in</Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
