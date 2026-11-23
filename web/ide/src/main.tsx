import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import './monacoSetup';
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { createRoot } from 'react-dom/client';
import { App } from './App';

createRoot(document.getElementById('root')!).render(
  <MantineProvider defaultColorScheme="auto">
    <Notifications position="top-right" />
    <App />
  </MantineProvider>,
);
