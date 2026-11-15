// The peonza's frames as SVG, from the brand's own model (~/Repos/logo-peonza:
// src/pose.mjs -> src/mark.mjs). theme/peonza/gen.py runs this, rasterises each
// SVG with rsvg-convert and composes the sheets; nothing here touches a file.
//
//   node theme/peonza/frames.mjs <logo-peonza repo>  < jobs.json  > frames.json
//
// jobs.json: [{ "key", "motion": "still" | "think" | "wobble", "frames", "opsz", "ink": { "fg", "bg" } }]
// frames.json: { key: [svg, ...] }, `frames` SVGs per job, evenly over one period.
//
// still   the still logo (STILL), one frame.
// think   the brand's working state over one period (1.2 s): plays while sessions are busy.
// wobble  the same precession, WOBBLE times wider: the top nods like the film's dying
//         swings and loops. Same timing as think, so its seam keeps think's distance from
//         the axis wherever the axis passes upright (no four-point sparkle).
// Each drawing is the brand's 'mark' layout drawn for `opsz` device px (src/opsz.mjs):
// the optics a <peonza-mark> of that width would have. Plain inks, no plate, grooves
// filled with the ground colour, transparent around.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const WOBBLE = 1.35;

const repo = process.argv[2];
if (!repo) throw new Error('usage: node theme/peonza/frames.mjs <logo-peonza repo> < jobs.json');
const load = (rel) => import(pathToFileURL(join(repo, rel)).href);
const { STILL, CAMERA, think, frameTimes } = await load('src/pose.mjs');
const { staticSVG, layout } = await load('src/mark.mjs');

const wider = (p, k) => ({ ...p, lean: k * p.lean, alpha: CAMERA + k * (p.alpha - CAMERA) });
const poses = {
  still: () => [STILL],
  think: (n) => frameTimes(think, n / think.period).map((t) => think.pose(t)),
  wobble: (n) => frameTimes(think, n / think.period).map((t) => wider(think.pose(t), WOBBLE)),
};

const out = {};
for (const job of JSON.parse(readFileSync(0, 'utf8'))) {
  const make = poses[job.motion];
  if (!make) throw new Error(`frames.mjs: unknown motion ${JSON.stringify(job.motion)} in job ${job.key}`);
  const list = make(job.frames);
  if (list.length !== job.frames) throw new Error(`frames.mjs: ${job.key} gave ${list.length} frames, wanted ${job.frames}`);
  const opts = { layout: { ...layout('mark'), opsz: job.opsz }, ink: job.ink, decimals: 2 };
  out[job.key] = list.map((pose) => staticSVG(pose, opts));
}
process.stdout.write(JSON.stringify(out));
