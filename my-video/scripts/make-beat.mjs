// Generates public/beat.wav: a simple 120 BPM beat, 10 seconds long.
import { writeFileSync } from "node:fs";

const sampleRate = 44100;
const seconds = 10;
const bpm = 120;
const beat = 60 / bpm;
const n = sampleRate * seconds;
const out = new Float32Array(n);

const add = (start, len, fn) => {
  const s0 = Math.floor(start * sampleRate);
  for (let i = 0; i < len * sampleRate && s0 + i < n; i++) {
    out[s0 + i] += fn(i / sampleRate);
  }
};

const kick = (t) => Math.sin(2 * Math.PI * (50 + 120 * Math.exp(-t * 30)) * t) * Math.exp(-t * 8) * 0.9;
const hat = (t) => (Math.random() * 2 - 1) * Math.exp(-t * 60) * 0.25;
const clap = (t) => (Math.random() * 2 - 1) * Math.exp(-t * 18) * 0.35;
const bassNotes = [55, 55, 65.4, 49];
const bass = (f) => (t) => Math.sign(Math.sin(2 * Math.PI * f * t)) * Math.exp(-t * 4) * 0.12;

// Music runs until 8.5s, then a soft chord rings for the ending.
const musicEnd = 8.5;
for (let b = 0; b * beat < musicEnd; b++) {
  const t = b * beat;
  add(t, 0.5, kick);
  add(t + beat / 2, 0.1, hat);
  if (b % 2 === 1) add(t, 0.3, clap);
  add(t, beat, bass(bassNotes[Math.floor(b / 4) % 4]));
}
const chord = [261.6, 329.6, 392, 523.3];
add(musicEnd, seconds - musicEnd, (t) =>
  chord.reduce((s, f) => s + Math.sin(2 * Math.PI * f * t), 0) * 0.06 * Math.exp(-t * 1.2) * Math.min(1, t * 20),
);

const buf = Buffer.alloc(44 + n * 2);
buf.write("RIFF", 0);
buf.writeUInt32LE(36 + n * 2, 4);
buf.write("WAVEfmt ", 8);
buf.writeUInt32LE(16, 16);
buf.writeUInt16LE(1, 20);
buf.writeUInt16LE(1, 22);
buf.writeUInt32LE(sampleRate, 24);
buf.writeUInt32LE(sampleRate * 2, 28);
buf.writeUInt16LE(2, 32);
buf.writeUInt16LE(16, 34);
buf.write("data", 36);
buf.writeUInt32LE(n * 2, 40);
for (let i = 0; i < n; i++) {
  buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, out[i])) * 32767), 44 + i * 2);
}
writeFileSync(new URL("../public/beat.wav", import.meta.url), buf);
