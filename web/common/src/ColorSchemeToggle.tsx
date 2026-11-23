import { ActionIcon, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';

/** Dark/light switch for the page header. Mantine remembers the choice in localStorage. */
export function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('light', { getInitialValueInEffect: true });
  const dark = scheme === 'dark';
  return (
    <ActionIcon
      variant="default"
      size="lg"
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      data-testid="color-scheme-toggle"
      onClick={() => setColorScheme(dark ? 'light' : 'dark')}
    >
      {dark ? '☀' : '☾'}
    </ActionIcon>
  );
}
