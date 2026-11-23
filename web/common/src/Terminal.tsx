import { useState } from 'react';
import { Anchor, Badge, Code, Group, Paper, ScrollArea, SimpleGrid, Stack, Switch, Text } from '@mantine/core';
import { diagnosticLabel, durationLabel, kindLabel, statusColor, testIcon, testSummary } from './format';
import type { Diagnostic, Job } from './types';

interface Props {
  job: Job | null;
  running: boolean;
  live: string;
  /** Called when a diagnostic is clicked, so the editor can jump to its line. */
  onGoto?: (d: Diagnostic) => void;
  height?: number | string;
  /** Robot log (robot.log messages) on the left, build/test results on the right, instead of a raw-output toggle. */
  split?: boolean;
}

/** Status line, diagnostics, test results, program output, with a raw-output toggle. */
export function Terminal({ job, running, live, onGoto, height = 220, split = false }: Props) {
  const [raw, setRaw] = useState(false);
  const empty = !job && !running && !live;

  const rawView = (
    <Code block data-testid="raw-output" style={{ whiteSpace: 'pre-wrap' }}>
      {running ? live : (job?.output ?? live)}
    </Code>
  );
  const robotLogView = (
    <Code block data-testid="robot-log" style={{ whiteSpace: 'pre-wrap' }}>
      {running ? '' : (job?.robotLog ?? '')}
    </Code>
  );
  const results = !running && job && (
          <Stack gap={6}>
          {job.diagnostics.map((d, i) => (
            <Text key={i} size="sm" c={d.severity === 'error' ? 'red.7' : 'yellow.8'} data-testid="diagnostic">
              {d.severity === 'error' ? '✘' : '⚠'}{' '}
              <Anchor component="button" type="button" size="sm" c="inherit" onClick={() => onGoto?.(d)}>
                {diagnosticLabel(d)}
              </Anchor>
            </Text>
          ))}
          {job.tests.length > 0 && (
            <Text size="sm" fw={600}>{testSummary(job.tests)}</Text>
          )}
          {job.tests.map((t, i) => (
            <Text key={i} size="sm" c={t.status === 'passed' ? 'green.8' : t.status === 'skipped' ? 'dimmed' : 'red.7'} data-testid="test-result">
              {testIcon(t)} {t.name}
              {t.message && <Text span display="block" ml="md" style={{ whiteSpace: 'pre-wrap' }}>{t.message}</Text>}
            </Text>
          ))}
          {job.programOutput && (
            <>
              <Text size="xs" c="dimmed" mt={4}>Program output</Text>
              <Code block style={{ whiteSpace: 'pre-wrap' }} data-testid="program-output">{job.programOutput}</Code>
            </>
          )}
        </Stack>
  );

  return (
    <Paper withBorder p="xs" data-testid="terminal">
      <Group justify="space-between" mb={4}>
        <Group gap="xs">
          {running && <Badge color="blue">Running…</Badge>}
          {!running && job && (
            <Badge color={statusColor(job, false)} data-testid="status-badge">
              {kindLabel(job)}: {job.status}
            </Badge>
          )}
          {!running && job && (
            <Text size="sm" data-testid="status-message">
              {job.message} {durationLabel(job) && <Text span c="dimmed">({durationLabel(job)})</Text>}
            </Text>
          )}
          {empty && <Text size="sm" c="dimmed">Press Build or Test to see results here.</Text>}
        </Group>
        {!split && <Switch size="xs" label="Show raw output" checked={raw} onChange={(e) => setRaw(e.currentTarget.checked)} />}
      </Group>
      {split ? (
        <SimpleGrid cols={2} spacing="xs">
          <div>
            <Text size="xs" c="dimmed" mb={2}>Robot log</Text>
            <ScrollArea h={height} type="auto">{robotLogView}</ScrollArea>
          </div>
          <div>
            <Text size="xs" c="dimmed" mb={2}>Build / test output</Text>
            <ScrollArea h={height} type="auto">{results}</ScrollArea>
          </div>
        </SimpleGrid>
      ) : (
        <ScrollArea h={height} type="auto">
          {(running || raw) && rawView}
          {!running && !raw && results}
        </ScrollArea>
      )}
    </Paper>
  );
}

