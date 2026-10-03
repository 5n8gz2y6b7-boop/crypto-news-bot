import React from "react";
import {
  AbsoluteFill,
  Composition,
  Easing,
  Freeze,
  Img,
  OffthreadVideo,
  Sequence,
  getStaticFiles,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { Sparkles } from "./Composition";

const FPS = 30;
const DURATION = 10 * FPS;
// The AI clip (8 s from Veo) plays between the intro and the smile hold.
const CLIP_START = 15;
const CLIP_LEN = 8 * FPS;
const CLIP_END = CLIP_START + CLIP_LEN;
const AI_CLIP = "ai-dance.mp4";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const ProIntroComposition = () => (
  <Composition
    id="DanceIntroPro"
    component={DanceIntroPro}
    durationInFrames={DURATION}
    fps={FPS}
    width={1080}
    height={1920}
  />
);

const fill = { width: "100%", height: "100%", objectFit: "cover" } as const;

export const DanceIntroPro: React.FC = () => {
  const frame = useCurrentFrame();
  const hasClip = getStaticFiles().some((f) => f.name === AI_CLIP);

  const flash = interpolate(frame, [0, 6, 18], [1, 0.8, 0], clamp);
  const photoOut = interpolate(
    frame,
    [CLIP_START, CLIP_START + 10],
    [1, 0],
    clamp,
  );
  // Ending: hold the last frame (the smile) and push in on the face.
  const hold = interpolate(frame, [CLIP_END, DURATION - 10], [0, 1], {
    ...clamp,
    easing: Easing.inOut(Easing.cubic),
  });
  const fadeOut = interpolate(frame, [DURATION - 8, DURATION], [0, 1], clamp);

  if (!hasClip) {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: "#111",
          color: "white",
          fontSize: 48,
          fontFamily: "sans-serif",
          justifyContent: "center",
          alignItems: "center",
          textAlign: "center",
          padding: 80,
        }}
      >
        Run `npm run ai-video` to generate public/{AI_CLIP}
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "white", overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          transformOrigin: "50% 22%",
          transform: `scale(${1 + hold * 0.35})`,
        }}
      >
        <Sequence from={CLIP_START} durationInFrames={CLIP_LEN}>
          <OffthreadVideo src={staticFile(AI_CLIP)} style={fill} />
        </Sequence>
        <Sequence from={CLIP_END}>
          <Freeze frame={CLIP_LEN - 1}>
            <OffthreadVideo src={staticFile(AI_CLIP)} style={fill} muted />
          </Freeze>
        </Sequence>
        <AbsoluteFill
          style={{
            opacity: photoOut,
            justifyContent: "center",
            alignItems: "center",
          }}
        >
          <Img
            src={staticFile("dancer-source.png")}
            style={{ height: "100%", objectFit: "contain" }}
          />
        </AbsoluteFill>
      </AbsoluteFill>

      {/* Subtle vignette for a cinematic look. */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse at 50% 45%, transparent 55%, rgba(0,0,0,0.25) 100%)",
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 30%, rgba(255,214,170,0.3) 0%, transparent 40%)",
          opacity: hold,
        }}
      />
      <Sparkles progress={hold} frame={frame} />

      <AbsoluteFill style={{ backgroundColor: "white", opacity: flash }} />
      <AbsoluteFill style={{ backgroundColor: "white", opacity: fadeOut }} />
    </AbsoluteFill>
  );
};
