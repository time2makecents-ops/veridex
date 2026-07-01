"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  lobbyTerminalConfig,
  lobbyTerminalRegionClass,
  regionVisible,
  type LobbyTerminalConfig,
  type LobbyTerminalMode,
  type LobbyTerminalRegionName,
} from "@/lib/lobby-terminal-config";
import {
  cloneLobbyTerminalConfig,
  clampPercent,
  formatPercent,
  LOBBY_TERMINAL_REGION_NAMES,
  parsePercentInput,
  regionModeSummary,
  roundPercent,
} from "@/lib/lobby-terminal-calibration";

type DragState = {
  region: LobbyTerminalRegionName;
  mode: "move" | "resize";
  startX: number;
  startY: number;
  startTop: number;
  startLeft: number;
  startWidth: number;
  startHeight: number;
  boundsWidth: number;
  boundsHeight: number;
};

function regionLabel(name: LobbyTerminalRegionName): string {
  switch (name) {
    case "mainDisplay":
      return "Main display";
    case "textInput":
      return "Text input";
    case "keypadOverlay":
      return "Keypad overlay";
    case "pinDots":
      return "PIN dots";
    case "statusPanel":
      return "Status panel";
    case "logoPanel":
      return "Logo panel";
    default:
      return name;
  }
}

function modeLabel(mode: LobbyTerminalMode): string {
  switch (mode) {
    case "text":
      return "Text";
    case "pin":
      return "PIN";
    case "voice":
      return "Voice";
    case "none":
      return "Hidden";
    default:
      return mode;
  }
}

function percentValue(value: string): number {
  return clampPercent(parsePercentInput(value));
}

export default function LobbyTerminalCalibrationEditor() {
  const [draft, setDraft] = useState<LobbyTerminalConfig>(() => cloneLobbyTerminalConfig());
  const [previewMode, setPreviewMode] = useState<LobbyTerminalMode>(lobbyTerminalConfig.defaultMode);
  const [selectedRegion, setSelectedRegion] = useState<LobbyTerminalRegionName>("mainDisplay");
  const [savedAt, setSavedAt] = useState<string>("");
  const [jsonCopied, setJsonCopied] = useState(false);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem("veridex:lobby-terminal-calibration");
    if (!stored) {
      return;
    }

    try {
      const parsed = JSON.parse(stored) as LobbyTerminalConfig;
      setDraft(parsed);
      setPreviewMode(parsed.defaultMode);
    } catch {
      window.localStorage.removeItem("veridex:lobby-terminal-calibration");
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem("veridex:lobby-terminal-calibration", JSON.stringify(draft));
    setSavedAt(new Date().toLocaleTimeString());
  }, [draft]);

  useEffect(() => {
    if (!dragState) {
      return;
    }

    const onMove = (event: PointerEvent) => {
      setDraft((current) => {
        const region = current.regions[dragState.region];
        const deltaX = ((event.clientX - dragState.startX) / dragState.boundsWidth) * 100;
        const deltaY = ((event.clientY - dragState.startY) / dragState.boundsHeight) * 100;
        const minSize = 4;

        if (dragState.mode === "move") {
          const nextLeft = clampPercent(dragState.startLeft + deltaX, 0, 100 - dragState.startWidth);
          const nextTop = clampPercent(dragState.startTop + deltaY, 0, 100 - dragState.startHeight);
          return {
            ...current,
            regions: {
              ...current.regions,
              [dragState.region]: {
                ...region,
                left: `${roundPercent(nextLeft)}%`,
                top: `${roundPercent(nextTop)}%`,
              },
            },
          };
        }

        const nextWidth = clampPercent(dragState.startWidth + deltaX, minSize, 100 - dragState.startLeft);
        const nextHeight = clampPercent(dragState.startHeight + deltaY, minSize, 100 - dragState.startTop);
        return {
          ...current,
          regions: {
            ...current.regions,
            [dragState.region]: {
              ...region,
              width: `${roundPercent(nextWidth)}%`,
              height: `${roundPercent(nextHeight)}%`,
            },
          },
        };
      });
    };

    const onUp = () => setDragState(null);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [dragState]);

  const jsonText = useMemo(() => JSON.stringify(draft, null, 2), [draft]);

  function updateRegion(
    region: LobbyTerminalRegionName,
    patch: Partial<LobbyTerminalConfig["regions"][LobbyTerminalRegionName]>,
  ) {
    setDraft((current) => ({
      ...current,
      regions: {
        ...current.regions,
        [region]: {
          ...current.regions[region],
          ...patch,
        },
      },
    }));
  }

  function updateTextStyle(patch: Partial<LobbyTerminalConfig["textStyle"]>) {
    setDraft((current) => ({
      ...current,
      textStyle: {
        ...current.textStyle,
        ...patch,
      },
    }));
  }

  function updatePinStyle(patch: Partial<LobbyTerminalConfig["pinStyle"]>) {
    setDraft((current) => ({
      ...current,
      pinStyle: {
        ...current.pinStyle,
        ...patch,
      },
    }));
  }

  function updateGeneral(patch: Partial<LobbyTerminalConfig>) {
    setDraft((current) => ({
      ...current,
      ...patch,
    }));
  }

  async function copyJson() {
    await navigator.clipboard.writeText(jsonText);
    setJsonCopied(true);
    window.setTimeout(() => setJsonCopied(false), 1200);
  }

  function downloadDraft() {
    const blob = new Blob([jsonText], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "lobby-terminal-config.json";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function beginDrag(region: LobbyTerminalRegionName, mode: "move" | "resize", x: number, y: number) {
    const preview = previewRef.current;
    if (!preview) {
      return;
    }

    const rect = preview.getBoundingClientRect();
    const current = draft.regions[region];
    setSelectedRegion(region);
    setDragState({
      region,
      mode,
      startX: x,
      startY: y,
      startTop: parsePercentInput(current.top),
      startLeft: parsePercentInput(current.left),
      startWidth: parsePercentInput(current.width),
      startHeight: parsePercentInput(current.height),
      boundsWidth: rect.width || 1,
      boundsHeight: rect.height || 1,
    });
  }

  function resetDraft() {
    setDraft(cloneLobbyTerminalConfig());
    setPreviewMode(lobbyTerminalConfig.defaultMode);
    setSelectedRegion("mainDisplay");
  }

  const selected = draft.regions[selectedRegion];

  return (
    <main className="screen calibration-page">
      <section className="card calibration-hero">
        <div className="terminal-label">Lobby Terminal Calibration</div>
        <h1 className="title">Overlay editor</h1>
        <p className="muted">
          Move and resize each layer directly on a blank work surface. No graphics, no frame art, just layout.
        </p>
      </section>

      <section className="card calibration-toolbar">
        <div className="calibration-toolbar-row">
          {(Object.keys(draft.regions) as LobbyTerminalRegionName[]).map((name) => (
            <button
              key={name}
              type="button"
              className={selectedRegion === name ? "primary" : "ghost"}
              onClick={() => setSelectedRegion(name)}
            >
              {regionLabel(name)}
            </button>
          ))}
        </div>
        <div className="calibration-toolbar-row calibration-toolbar-row-wrap">
          {(["text", "pin", "voice", "none"] as LobbyTerminalMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              className={previewMode === mode ? "secondary" : "ghost"}
              onClick={() => setPreviewMode(mode)}
            >
              Preview {modeLabel(mode)}
            </button>
          ))}
        </div>
      </section>

      <section className="card calibration-panel">
        <div className="terminal-panel-title">Terminal basics</div>
        <div className="calibration-field-grid">
          <label className="calibration-span-2">
            <span>Terminal id</span>
            <input
              type="text"
              value={draft.terminalId}
              onChange={(event) => updateGeneral({ terminalId: event.target.value })}
            />
          </label>
          <label className="calibration-span-2">
            <span>Name</span>
            <input type="text" value={draft.name} onChange={(event) => updateGeneral({ name: event.target.value })} />
          </label>
          <label className="calibration-span-2">
            <span>Frame asset</span>
            <input
              type="text"
              value={draft.frameAsset}
              onChange={(event) => updateGeneral({ frameAsset: event.target.value })}
            />
          </label>
          <label>
            <span>Aspect width</span>
            <input
              type="number"
              min={1}
              step={1}
              value={draft.aspectRatio.width}
              onChange={(event) =>
                updateGeneral({
                  aspectRatio: {
                    ...draft.aspectRatio,
                    width: Number(event.target.value),
                  },
                })
              }
            />
          </label>
          <label>
            <span>Aspect height</span>
            <input
              type="number"
              min={1}
              step={1}
              value={draft.aspectRatio.height}
              onChange={(event) =>
                updateGeneral({
                  aspectRatio: {
                    ...draft.aspectRatio,
                    height: Number(event.target.value),
                  },
                })
              }
            />
          </label>
          <label>
            <span>Default mode</span>
            <select
              value={draft.defaultMode}
              onChange={(event) => updateGeneral({ defaultMode: event.target.value as LobbyTerminalMode })}
            >
              {(["text", "pin", "voice", "none"] as LobbyTerminalMode[]).map((mode) => (
                <option key={mode} value={mode}>
                  {modeLabel(mode)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="calibration-workbench">
        <div className="card calibration-preview-card">
          <div ref={previewRef} className="calibration-preview calibration-preview-blank">
            <div className="calibration-grid" />
            {LOBBY_TERMINAL_REGION_NAMES.map((name) => {
              const region = draft.regions[name];
              const active = selectedRegion === name;
              const liveVisible = regionVisible(region, previewMode);
              const opacity = liveVisible ? 1 : 0.26;

              return (
                <div
                  key={name}
                  className={`${lobbyTerminalRegionClass(name)} calibration-region-box ${active ? "is-selected" : ""}`}
                  style={{
                    position: "absolute",
                    top: region.top,
                    left: region.left,
                    width: region.width,
                    height: region.height,
                    opacity,
                    zIndex: region.zIndex ?? 1,
                    pointerEvents: "auto",
                    borderRadius: region.borderRadius || "12px",
                  }}
                  onPointerDown={(event) => beginDrag(name, "move", event.clientX, event.clientY)}
                >
                  <div className="calibration-region-label">
                    <span>{regionLabel(name)}</span>
                    <span>{liveVisible ? modeLabel(previewMode) : "hidden"}</span>
                  </div>
                  <button
                    type="button"
                    className="calibration-resize-handle"
                    onPointerDown={(event) => {
                      event.stopPropagation();
                      beginDrag(name, "resize", event.clientX, event.clientY);
                    }}
                    aria-label={`Resize ${regionLabel(name)}`}
                  />
                </div>
              );
            })}
            <div className="calibration-overlay-copy">
              <div className="terminal-label">Mode preview</div>
              <div className="calibration-overlay-badge">{modeLabel(previewMode)}</div>
            </div>
          </div>
        </div>

        <div className="calibration-sidebar">
          <section className="card calibration-panel">
            <div className="terminal-panel-title">Selected layer</div>
            <div className="stack">
              <strong>{regionLabel(selectedRegion)}</strong>
              <div className="calibration-inline-meta">{regionModeSummary(selected)}</div>
              <div className="calibration-field-grid">
                <label>
                  <span>Top</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.1}
                    value={parsePercentInput(selected.top)}
                    onChange={(event) =>
                      updateRegion(selectedRegion, { top: `${formatPercent(percentValue(event.target.value))}` })
                    }
                  />
                </label>
                <label>
                  <span>Left</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.1}
                    value={parsePercentInput(selected.left)}
                    onChange={(event) =>
                      updateRegion(selectedRegion, { left: `${formatPercent(percentValue(event.target.value))}` })
                    }
                  />
                </label>
                <label>
                  <span>Width</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.1}
                    value={parsePercentInput(selected.width)}
                    onChange={(event) =>
                      updateRegion(selectedRegion, { width: `${formatPercent(percentValue(event.target.value))}` })
                    }
                  />
                </label>
                <label>
                  <span>Height</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.1}
                    value={parsePercentInput(selected.height)}
                    onChange={(event) =>
                      updateRegion(selectedRegion, { height: `${formatPercent(percentValue(event.target.value))}` })
                    }
                  />
                </label>
              </div>
              <div className="calibration-field-grid">
                <label>
                  <span>Padding</span>
                  <input
                    type="text"
                    value={selected.padding || ""}
                    onChange={(event) => updateRegion(selectedRegion, { padding: event.target.value || undefined })}
                    placeholder="e.g. 3% 4%"
                  />
                </label>
                <label>
                  <span>Radius</span>
                  <input
                    type="text"
                    value={selected.borderRadius || ""}
                    onChange={(event) => updateRegion(selectedRegion, { borderRadius: event.target.value || undefined })}
                    placeholder="e.g. 12px"
                  />
                </label>
              </div>
              <div className="calibration-field-grid">
                <label>
                  <span>Z-index</span>
                  <input
                    type="number"
                    value={selected.zIndex ?? 1}
                    onChange={(event) => updateRegion(selectedRegion, { zIndex: Number(event.target.value) })}
                  />
                </label>
                <label>
                  <span>Pointer events</span>
                  <select
                    value={selected.pointerEvents || "auto"}
                    onChange={(event) =>
                      updateRegion(selectedRegion, {
                        pointerEvents: event.target.value as LobbyTerminalConfig["regions"][LobbyTerminalRegionName]["pointerEvents"],
                      })
                    }
                  >
                    <option value="auto">auto</option>
                    <option value="none">none</option>
                  </select>
                </label>
              </div>
            </div>
          </section>

          <section className="card calibration-panel">
            <div className="terminal-panel-title">Mode visibility</div>
            <div className="calibration-visibility">
              {(["text", "pin", "voice", "none"] as LobbyTerminalMode[]).map((mode) => (
                <label key={mode} className="calibration-toggle">
                  <input
                    type="checkbox"
                    checked={selected.visible[mode]}
                    onChange={(event) =>
                      updateRegion(selectedRegion, {
                        visible: {
                          ...selected.visible,
                          [mode]: event.target.checked,
                        },
                      })
                    }
                  />
                  <span>{modeLabel(mode)}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="card calibration-panel">
            <div className="terminal-panel-title">Text styling</div>
            <div className="calibration-field-grid">
              <label className="calibration-span-2">
                <span>Font family</span>
                <input
                  type="text"
                  value={draft.textStyle.fontFamily}
                  onChange={(event) => updateTextStyle({ fontFamily: event.target.value })}
                />
              </label>
              <label>
                <span>Font size</span>
                <input
                  type="text"
                  value={draft.textStyle.fontSize}
                  onChange={(event) => updateTextStyle({ fontSize: event.target.value })}
                />
              </label>
              <label>
                <span>Line height</span>
                <input
                  type="number"
                  min={0.5}
                  max={3}
                  step={0.01}
                  value={draft.textStyle.lineHeight}
                  onChange={(event) => updateTextStyle({ lineHeight: Number(event.target.value) })}
                />
              </label>
              <label>
                <span>Color</span>
                <input
                  type="text"
                  value={draft.textStyle.color}
                  onChange={(event) => updateTextStyle({ color: event.target.value })}
                />
              </label>
              <label>
                <span>Shadow</span>
                <input
                  type="text"
                  value={draft.textStyle.textShadow}
                  onChange={(event) => updateTextStyle({ textShadow: event.target.value })}
                />
              </label>
              <label>
                <span>Align</span>
                <select
                  value={draft.textStyle.textAlign}
                  onChange={(event) => updateTextStyle({ textAlign: event.target.value as LobbyTerminalConfig["textStyle"]["textAlign"] })}
                >
                  <option value="left">left</option>
                  <option value="center">center</option>
                  <option value="right">right</option>
                </select>
              </label>
              <label>
                <span>Overflow</span>
                <select
                  value={draft.textStyle.overflow}
                  onChange={(event) => updateTextStyle({ overflow: event.target.value as LobbyTerminalConfig["textStyle"]["overflow"] })}
                >
                  <option value="hidden">hidden</option>
                  <option value="auto">auto</option>
                  <option value="scroll">scroll</option>
                  <option value="visible">visible</option>
                </select>
              </label>
              <label>
                <span>Auto scroll</span>
                <select
                  value={draft.textStyle.autoScroll ? "yes" : "no"}
                  onChange={(event) => updateTextStyle({ autoScroll: event.target.value === "yes" })}
                >
                  <option value="yes">yes</option>
                  <option value="no">no</option>
                </select>
              </label>
            </div>
          </section>

          <section className="card calibration-panel">
            <div className="terminal-panel-title">PIN behavior</div>
            <div className="calibration-field-grid">
              <label>
                <span>PIN length</span>
                <input
                  type="number"
                  min={4}
                  max={8}
                  step={1}
                  value={draft.pinStyle.pinLength}
                  onChange={(event) => updatePinStyle({ pinLength: Number(event.target.value) })}
                />
              </label>
              <label>
                <span>Masked</span>
                <select
                  value={draft.pinStyle.masked ? "yes" : "no"}
                  onChange={(event) => updatePinStyle({ masked: event.target.value === "yes" })}
                >
                  <option value="yes">yes</option>
                  <option value="no">no</option>
                </select>
              </label>
              <label>
                <span>Idle glow (ms)</span>
                <input
                  type="number"
                  min={0}
                  step={10}
                  value={draft.pinStyle.idleGlowAnimationMs}
                  onChange={(event) => updatePinStyle({ idleGlowAnimationMs: Number(event.target.value) })}
                />
              </label>
              <label>
                <span>Dot glow (ms)</span>
                <input
                  type="number"
                  min={0}
                  step={10}
                  value={draft.pinStyle.sequentialGlowMs}
                  onChange={(event) => updatePinStyle({ sequentialGlowMs: Number(event.target.value) })}
                />
              </label>
            </div>
          </section>

          <section className="card calibration-panel">
            <div className="terminal-panel-title">Draft</div>
            <div className="stack">
              <textarea readOnly value={jsonText} rows={14} className="calibration-json" />
              <div className="row">
                <button type="button" className="primary" onClick={copyJson}>
                  {jsonCopied ? "Copied" : "Copy JSON"}
                </button>
                <button type="button" className="secondary" onClick={downloadDraft}>
                  Save file
                </button>
                <button type="button" className="ghost" onClick={resetDraft}>
                  Reset
                </button>
              </div>
              <div className="muted">
                Draft saves locally in this browser. Last saved: {savedAt || "just now"}.
              </div>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
