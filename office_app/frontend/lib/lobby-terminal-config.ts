import type { CSSProperties } from "react";

export type LobbyTerminalMode = "text" | "pin" | "voice" | "none";
export type LobbyTerminalRegionName =
  | "mainDisplay"
  | "textInput"
  | "keypadOverlay"
  | "pinDots"
  | "statusPanel"
  | "logoPanel";

export type LobbyTerminalRegionConfig = {
  top: string;
  left: string;
  width: string;
  height: string;
  visible: Record<LobbyTerminalMode, boolean>;
  pointerEvents?: CSSProperties["pointerEvents"];
  padding?: string;
  borderRadius?: string;
  zIndex?: number;
};

export type LobbyTerminalTextStyle = {
  fontFamily: string;
  fontSize: string;
  lineHeight: number;
  color: string;
  textShadow: string;
  textAlign: CSSProperties["textAlign"];
  verticalAlign: "top" | "middle" | "bottom";
  overflow: CSSProperties["overflow"];
  autoScroll: boolean;
};

export type LobbyTerminalPinStyle = {
  pinLength: number;
  masked: boolean;
  idleGlowAnimationMs: number;
  sequentialGlowMs: number;
};

export type LobbyTerminalConfig = {
  terminalId: string;
  name: string;
  frameAsset: string;
  aspectRatio: {
    width: number;
    height: number;
  };
  defaultMode: LobbyTerminalMode;
  regions: Record<LobbyTerminalRegionName, LobbyTerminalRegionConfig>;
  textStyle: LobbyTerminalTextStyle;
  pinStyle: LobbyTerminalPinStyle;
  animation: {
    transitionMs: number;
    scrollMs: number;
  };
  mobile: {
    fillViewport: boolean;
    lockScroll: boolean;
    scaleMode: "cover" | "contain";
  };
};

export const lobbyTerminalConfig: LobbyTerminalConfig = {
  terminalId: "veridex-lobby-terminal",
  name: "Veridex Lobby Terminal",
  frameAsset: "/terminal_frame.jpg",
  aspectRatio: {
    width: 630,
    height: 353,
  },
  defaultMode: "text",
  regions: {
    mainDisplay: {
      top: "8.5%",
      left: "10%",
      width: "80%",
      height: "53%",
      visible: {
        text: true,
        pin: true,
        voice: true,
        none: false,
      },
      pointerEvents: "auto",
      padding: "3.5% 4.5%",
      borderRadius: "8px",
      zIndex: 2,
    },
    textInput: {
      top: "74.5%",
      left: "15.5%",
      width: "69%",
      height: "13.5%",
      visible: {
        text: true,
        pin: false,
        voice: false,
        none: false,
      },
      pointerEvents: "auto",
      padding: "0",
      borderRadius: "0",
      zIndex: 3,
    },
    keypadOverlay: {
      top: "70.5%",
      left: "15%",
      width: "70%",
      height: "20%",
      visible: {
        text: false,
        pin: true,
        voice: false,
        none: false,
      },
      pointerEvents: "auto",
      padding: "0",
      borderRadius: "0",
      zIndex: 3,
    },
    pinDots: {
      top: "66.5%",
      left: "31%",
      width: "38%",
      height: "6%",
      visible: {
        text: false,
        pin: true,
        voice: false,
        none: false,
      },
      pointerEvents: "none",
      padding: "0",
      borderRadius: "0",
      zIndex: 4,
    },
    statusPanel: {
      top: "3.5%",
      left: "6%",
      width: "88%",
      height: "6%",
      visible: {
        text: false,
        pin: false,
        voice: false,
        none: false,
      },
      pointerEvents: "none",
      padding: "0",
      borderRadius: "0",
      zIndex: 4,
    },
    logoPanel: {
      top: "3%",
      left: "42%",
      width: "16%",
      height: "6%",
      visible: {
        text: false,
        pin: false,
        voice: false,
        none: false,
      },
      pointerEvents: "none",
      padding: "0",
      borderRadius: "0",
      zIndex: 4,
    },
  },
  textStyle: {
    fontFamily: '"Courier New", Courier, monospace',
    fontSize: "0.72rem",
    lineHeight: 1.18,
    color: "#d9f7ff",
    textShadow: "0 0 6px rgba(91, 213, 255, 0.16)",
    textAlign: "left",
    verticalAlign: "top",
    overflow: "hidden",
    autoScroll: true,
  },
  pinStyle: {
    pinLength: 4,
    masked: true,
    idleGlowAnimationMs: 900,
    sequentialGlowMs: 140,
  },
  animation: {
    transitionMs: 180,
    scrollMs: 240,
  },
  mobile: {
    fillViewport: true,
    lockScroll: true,
    scaleMode: "cover",
  },
};

export type LobbyRegionStyle = CSSProperties & {
  position: "absolute";
  top: string;
  left: string;
  width: string;
  height: string;
};

export function regionVisible(region: LobbyTerminalRegionConfig, mode: LobbyTerminalMode): boolean {
  return Boolean(region.visible[mode]);
}

export function regionStyle(region: LobbyTerminalRegionConfig, mode: LobbyTerminalMode): LobbyRegionStyle {
  return {
    position: "absolute",
    top: region.top,
    left: region.left,
    width: region.width,
    height: region.height,
    padding: region.padding,
    borderRadius: region.borderRadius,
    zIndex: region.zIndex,
    pointerEvents: region.pointerEvents,
    overflow: "hidden",
  };
}

export function lobbyTerminalRegionClass(name: LobbyTerminalRegionName): string {
  return `lobby-terminal-region lobby-terminal-region-${name}`;
}

export function textStyleToCss(style: LobbyTerminalTextStyle): CSSProperties {
  return {
    fontFamily: style.fontFamily,
    fontSize: style.fontSize,
    lineHeight: style.lineHeight,
    color: style.color,
    textShadow: style.textShadow,
    textAlign: style.textAlign,
    overflow: style.overflow,
  };
}
