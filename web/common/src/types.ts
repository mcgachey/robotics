export type Role = 'student' | 'teacher';

export interface Me {
  role: Role;
  id: string;
  name: string;
}

export interface Diagnostic {
  file: string;
  line: number;
  column: number;
  severity: 'error' | 'warning';
  message: string; // beginner-friendly
  javac: string; // javac's own text
  raw: string;
}

export interface TestResult {
  name: string;
  status: 'passed' | 'failed' | 'error' | 'skipped';
  message: string;
}

export type JobStatus = 'running' | 'passed' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  kind: 'build' | 'test';
  origin: 'student' | 'teacher-verify';
  studentId: string;
  lessonId: string;
  revision: number;
  status: JobStatus;
  reason: string;
  message: string;
  durations: Record<string, number>;
  diagnostics: Diagnostic[];
  tests: TestResult[];
  output?: string;
  programOutput?: string;
}

export interface JobRef {
  jobId: string;
  revision: number;
  status: string;
  reason: string;
}

export interface Lesson {
  id: string;
  title: string;
  className: string;
  targetPhase: number;
  apiVersion: number;
}

export interface LessonFull extends Lesson {
  starter: string;
  tests: string;
}

export interface ProjectState {
  lessonId: string;
  className: string;
  revision: number;
  lastBuild: JobRef | null;
  lastGoodBuild: { jobId: string; revision: number } | null;
  lastTest: JobRef | null;
  lastSubmit: { revision: number; submittedAt: string } | null;
  canSubmit: boolean;
}

export interface Project extends ProjectState {
  title: string;
  source: string;
  activeJobId: string | null;
}

export interface Student {
  id: string;
  name: string;
  login: string;
  enabled: boolean;
  projects: Record<string, Omit<ProjectState, 'lessonId' | 'className' | 'lastGoodBuild'>>;
}

export interface QueueEntry {
  key: string;
  studentId: string;
  studentName: string;
  studentLogin: string;
  lessonId: string;
  lessonTitle: string;
  buildId: string;
  revision: number;
  submittedAt: string;
}
