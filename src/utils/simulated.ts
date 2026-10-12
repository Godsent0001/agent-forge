/**
 * The backend's built-in test runner (FakeRunner, the default unless AGENTFORGE_RUNNER=v2) answers with
 * "FakeRunner completed: <task>". Detect it so the UI can say plainly that the reply is simulated,
 * instead of presenting it as a real model answer.
 * Ideal long-term fix: expose the runner mode from GET /health and read it there.
 */
export function isSimulatedText(text: string | null | undefined): boolean {
  return !!text && text.startsWith("FakeRunner completed:");
}
