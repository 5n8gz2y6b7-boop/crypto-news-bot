// Turns public/dancer-source.png into public/ai-dance.mp4 with Google Veo
// (image-to-video through the Gemini API).
//
// Usage:
//   GEMINI_API_KEY=... npm run ai-video
// Optional: VEO_MODEL (default below), VEO_PROMPT to override the prompt.

import { readFileSync, writeFileSync } from "node:fs";

const API = "https://generativelanguage.googleapis.com/v1beta";
const key = process.env.GEMINI_API_KEY;
const model = process.env.VEO_MODEL ?? "veo-3.1-generate-preview";

const prompt =
  process.env.VEO_PROMPT ??
  [
    "Fashion film, the woman from the photo in her long dark leather coat,",
    "teal leather jumpsuit and black knee-high boots, in a bright white studio.",
    "She starts dancing to an upbeat electronic beat: confident hip sways,",
    "shoulder rolls, a smooth spin that makes the long coat flare out, stylish footwork.",
    "Fluid, natural, professional choreography. Full body in frame, static camera.",
    "In the last two seconds she stops, faces the camera and gives a warm, genuine smile.",
    "Keep her face, glasses, hair and outfit exactly as in the photo.",
  ].join(" ");

if (!key) {
  console.error("GEMINI_API_KEY is not set.");
  process.exit(1);
}

const headers = { "x-goog-api-key": key, "Content-Type": "application/json" };
const image = readFileSync(
  new URL("../public/dancer-source.png", import.meta.url),
);

const api = async (path, init) => {
  const res = await fetch(`${API}/${path}`, { ...init, headers });
  const body = await res.json();
  if (!res.ok)
    throw new Error(`${res.status}: ${JSON.stringify(body.error ?? body)}`);
  return body;
};

console.log(`Starting ${model}...`);
let op = await api(`models/${model}:predictLongRunning`, {
  method: "POST",
  body: JSON.stringify({
    instances: [
      {
        prompt,
        image: {
          bytesBase64Encoded: image.toString("base64"),
          mimeType: "image/png",
        },
      },
    ],
    parameters: {
      aspectRatio: "9:16",
      durationSeconds: 8,
      personGeneration: "allow_adult",
    },
  }),
});

while (!op.done) {
  await new Promise((r) => setTimeout(r, 10000));
  op = await api(op.name);
  process.stdout.write(".");
}
console.log();

if (op.error) throw new Error(JSON.stringify(op.error));
const sample = op.response?.generateVideoResponse?.generatedSamples?.[0];
if (!sample?.video?.uri) {
  throw new Error(
    `No video returned (possibly filtered): ${JSON.stringify(op.response)}`,
  );
}

const video = await fetch(sample.video.uri, {
  headers: { "x-goog-api-key": key },
});
if (!video.ok) throw new Error(`Download failed: ${video.status}`);
writeFileSync(
  new URL("../public/ai-dance.mp4", import.meta.url),
  Buffer.from(await video.arrayBuffer()),
);
console.log("Saved public/ai-dance.mp4");
