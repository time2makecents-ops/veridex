import type { LobbyTerminalConfig, LobbyTerminalMode, LobbyTerminalRegionName } from "./lobby-terminal-config";
import { lobbyTerminalConfig } from "./lobby-terminal-config";

export const LOBBY_TERMINAL_REGION_NAMES: LobbyTerminalRegionName[] = [
  "mainDisplay",
  "textInput",
  "keypadOverlay",
  "pinDots",
  "statusPanel",
  "logoPanel",
];

export function cloneLobbyTerminalConfig(config: LobbyTerminalConfig = lobbyTerminalConfig): LobbyTerminalConfig {
  return JSON.parse(JSON.stringify(config)) as LobbyTerminalConfig;
}

export function clampPercent(value: number, min = 0, max = 100): number {
  if (Number.isNaN(value) || !Number.isFinite(value)) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}

export function roundPercent(value: number): number {
  return Math.round(value * 10) / 10;
}

export function parsePercentInput(value: string): number {
  const parsed = Number.parseFloat(value.replace(/%/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatPercent(value: number): string {
  return `${roundPercent(value)}%`;
}

export function regionModeSummary(region: LobbyTerminalConfig["regions"][LobbyTerminalRegionName]): string {
  return (Object.keys(region.visible) as LobbyTerminalMode[])
    .filter((mode) => region.visible[mode])
    .join(", ");
}

