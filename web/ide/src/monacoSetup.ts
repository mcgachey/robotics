// Monaco comes from the npm package and is bundled by Vite, so the IDE never loads it from a CDN.
// Only the editor core, the Java grammar and a few contributions are imported (not every language).
import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/editor/editor.api';
import 'monaco-editor/languages/definitions/java/register';
import 'monaco-editor/editor/contrib/bracketMatching/browser/bracketMatching';
import 'monaco-editor/editor/contrib/clipboard/browser/clipboard';
import 'monaco-editor/editor/contrib/comment/browser/comment';
import 'monaco-editor/editor/contrib/contextmenu/browser/contextmenu';
import 'monaco-editor/editor/contrib/find/browser/findController';
import 'monaco-editor/editor/contrib/folding/browser/folding';
import 'monaco-editor/editor/contrib/hover/browser/hoverContribution';
import 'monaco-editor/editor/contrib/indentation/browser/indentation';
import 'monaco-editor/editor/contrib/linesOperations/browser/linesOperations';
import 'monaco-editor/editor/contrib/multicursor/browser/multicursor';
import 'monaco-editor/editor/contrib/smartSelect/browser/smartSelect';
import 'monaco-editor/editor/contrib/wordHighlighter/browser/wordHighlighter';
import 'monaco-editor/editor/contrib/wordOperations/browser/wordOperations';
import '@monaco-codicon.css';
import EditorWorker from 'monaco-editor/editor/editor.worker?worker';

(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};

loader.config({ monaco });
export { monaco };
