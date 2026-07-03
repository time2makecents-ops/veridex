export const NANCY_MODE_PREFIX = "Nancy, ";
export const NANCY_ROOM_ID = "my_office";

export function effectiveNancyMode(activeRoom: string, nancyMode: boolean): boolean {
  return activeRoom !== NANCY_ROOM_ID && nancyMode;
}

export function isNancyButtonHighlighted(activeRoom: string, nancyMode: boolean): boolean {
  return activeRoom === NANCY_ROOM_ID || effectiveNancyMode(activeRoom, nancyMode);
}

export function nextNancyMode(activeRoom: string, nancyMode: boolean): boolean {
  if (activeRoom === NANCY_ROOM_ID) {
    return false;
  }
  return !nancyMode;
}

export function buildNancyModeRequest(text: string): string {
  const value = text.trim();
  if (/^nancy\s*[,.:\-]/i.test(value)) {
    return value;
  }
  return `${NANCY_MODE_PREFIX}${value}`;
}
