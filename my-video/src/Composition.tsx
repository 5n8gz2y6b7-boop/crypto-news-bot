import React from "react";
import {
  AbsoluteFill,
  Composition,
  Easing,
  Html5Audio,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const FPS = 30;
const DURATION = 10 * FPS;
const WIDTH = 1080;
const HEIGHT = 1920;

// 120 BPM -> one beat every 15 frames.
const BEAT = FPS / 2;
const DANCE_START = 30;
const DANCE_END = 255;

// Layout of the dancer inside the 1080x1920 frame.
const IMG_RATIO = 468 / 1098;
const DANCER_H = 1500;
const DANCER_W = DANCER_H * IMG_RATIO;
const DANCER_BOTTOM = 1860;
const DANCER_TOP = DANCER_BOTTOM - DANCER_H;
// The face sits ~12% from the top of the source image.
const FACE_Y = DANCER_TOP + 0.12 * DANCER_H;

export const MyComposition = () => {
  return (
    <Composition
      id="DanceIntro"
      component={DanceIntro}
      durationInFrames={DURATION}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Dance pose for a given frame. `energy` scales the whole move (0 = still).
const pose = (f: number, energy: number) => {
  const beatPhase = (f % BEAT) / BEAT;
  const bounce = -Math.abs(Math.sin(Math.PI * beatPhase)) * 45 * energy;
  // Squash on landing, stretch in the air.
  const landing = Math.exp(-beatPhase * 10);
  const scaleY = 1 + (0.04 * (1 - landing) - 0.05 * landing) * energy;
  const scaleXSquash = 1 + 0.04 * landing * energy;
  const sway = Math.sin((2 * Math.PI * f) / (BEAT * 2)) * 7 * energy;
  const hips = Math.sin((2 * Math.PI * f) / (BEAT * 2) + Math.PI / 2) * 5 * energy;
  const step = Math.sin((2 * Math.PI * f) / (BEAT * 4)) * 110 * energy;

  // Two quick spins (a horizontal flip that reads as a turn).
  let turn = 1;
  for (const start of [120, 210]) {
    const p = interpolate(f, [start, start + BEAT], [0, 1], clamp);
    if (p > 0 && p < 1) turn = Math.cos(2 * Math.PI * p);
  }

  return { bounce, scaleY, scaleX: scaleXSquash * turn, sway, hips, step };
};

const Dancer: React.FC<{
  f: number;
  energy: number;
  opacity?: number;
  entrance: number;
}> = ({ f, energy, opacity = 1, entrance }) => {
  const p = pose(f, energy);
  return (
    <div
      style={{
        position: "absolute",
        left: WIDTH / 2 - DANCER_W / 2,
        top: DANCER_TOP,
        width: DANCER_W,
        height: DANCER_H,
        opacity,
        transformOrigin: "50% 100%",
        transform: [
          `translateX(${p.step}px)`,
          `translateY(${p.bounce + (1 - entrance) * 300}px)`,
          `rotate(${p.sway}deg)`,
          `skewX(${p.hips}deg)`,
          `scale(${p.scaleX * (0.7 + 0.3 * entrance)}, ${p.scaleY * (0.7 + 0.3 * entrance)})`,
        ].join(" "),
      }}
    >
      <Img
        src={staticFile("dancer.png")}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
};

const Lights: React.FC<{ frame: number; energy: number }> = ({
  frame,
  energy,
}) => {
  const pulse = Math.exp(-((frame % BEAT) / BEAT) * 4) * energy;
  const blobs = [
    { color: "#7fd8e6", x: 0.2, y: 0.25, speed: 1 },
    { color: "#f2a7d8", x: 0.8, y: 0.35, speed: 1.3 },
    { color: "#b9a8ff", x: 0.5, y: 0.75, speed: 0.8 },
  ];
  return (
    <AbsoluteFill>
      {blobs.map((b, i) => {
        const t = (frame / FPS) * b.speed;
        const cx = (b.x + Math.sin(t + i) * 0.15) * WIDTH;
        const cy = (b.y + Math.cos(t * 0.8 + i) * 0.1) * HEIGHT;
        const r = 520 + pulse * 120;
        return (
          <div
            key={b.color}
            style={{
              position: "absolute",
              left: cx - r,
              top: cy - r,
              width: r * 2,
              height: r * 2,
              borderRadius: "50%",
              background: `radial-gradient(circle, ${b.color} 0%, transparent 65%)`,
              opacity: 0.35 + 0.45 * energy,
            }}
          />
        );
      })}
      {/* Floor shadow that follows the beat. */}
      <div
        style={{
          position: "absolute",
          left: WIDTH / 2 - 260,
          top: DANCER_BOTTOM - 30,
          width: 520,
          height: 70,
          borderRadius: "50%",
          background:
            "radial-gradient(ellipse, rgba(20,40,50,0.35), transparent 70%)",
          transform: `scaleX(${1 - pulse * 0.15})`,
        }}
      />
    </AbsoluteFill>
  );
};

const Sparkles: React.FC<{ progress: number; frame: number }> = ({
  progress,
  frame,
}) => {
  const items = [
    { dx: -150, dy: -120, s: 1 },
    { dx: 160, dy: -80, s: 0.8 },
    { dx: -120, dy: 110, s: 0.7 },
    { dx: 140, dy: 130, s: 1.1 },
    { dx: 0, dy: -190, s: 0.6 },
  ];
  return (
    <AbsoluteFill>
      {items.map((it, i) => {
        const local = interpolate(progress, [i * 0.1, i * 0.1 + 0.4], [0, 1], clamp);
        const twinkle = 0.7 + 0.3 * Math.sin(frame / 3 + i);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: WIDTH / 2 + it.dx - 40,
              top: HEIGHT / 2 + it.dy - 40,
              width: 80,
              height: 80,
              fontSize: 70 * it.s,
              textAlign: "center",
              color: "#fff6c9",
              textShadow: "0 0 25px #ffd86b, 0 0 50px #ffb3e6",
              opacity: local * twinkle,
              transform: `scale(${local * twinkle}) rotate(${frame * 2 + i * 40}deg)`,
            }}
          >
            ✦
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

export const DanceIntro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entrance = spring({ frame, fps, config: { damping: 12 } });

  // Dance energy ramps up after the entrance and fades out for the ending.
  const energy =
    interpolate(frame, [DANCE_START - 10, DANCE_START + 10], [0, 1], clamp) *
    interpolate(frame, [DANCE_END - 20, DANCE_END], [1, 0], {
      ...clamp,
      easing: Easing.inOut(Easing.cubic),
    });

  // Final camera move: push in on the face for the closing smile.
  const zoom = interpolate(frame, [DANCE_END - 10, DURATION - 15], [0, 1], {
    ...clamp,
    easing: Easing.inOut(Easing.cubic),
  });
  const camScale = 1 + zoom * 2.4;
  const camShiftY = (HEIGHT / 2 - FACE_Y) * zoom;

  const flash = interpolate(frame, [0, 6, 18], [1, 0.8, 0], clamp);
  const fadeOut = interpolate(frame, [DURATION - 8, DURATION], [0, 1], clamp);

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(180deg, #f7fbfc 0%, #eef3f7 100%)",
        overflow: "hidden",
      }}
    >
      <Html5Audio src={staticFile("beat.wav")} />

      <AbsoluteFill
        style={{
          transformOrigin: `${WIDTH / 2}px ${FACE_Y}px`,
          transform: `translateY(${camShiftY}px) scale(${camScale})`,
        }}
      >
        <Lights frame={frame} energy={energy} />
        {/* Motion trails behind the dancer. */}
        {energy > 0.05 &&
          [6, 3].map((lag) => (
            <Dancer
              key={lag}
              f={Math.max(0, frame - lag)}
              energy={energy}
              entrance={entrance}
              opacity={0.18 * energy}
            />
          ))}
        <Dancer f={frame} energy={energy} entrance={entrance} />
      </AbsoluteFill>

      {/* Warm glow on the face during the ending. */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 50%, rgba(255,214,170,0.35) 0%, transparent 45%)",
          opacity: zoom,
        }}
      />
      <Sparkles progress={zoom} frame={frame} />

      <AbsoluteFill style={{ backgroundColor: "white", opacity: flash }} />
      <AbsoluteFill style={{ backgroundColor: "white", opacity: fadeOut }} />
    </AbsoluteFill>
  );
};
