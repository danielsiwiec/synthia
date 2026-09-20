import { describe, it, expect } from "vitest";
import { downsample, floatTo16BitPCM, int16ToFloat32, rms } from "./pcm";

describe("pcm", () => {
  it("converts floats to 16-bit and back within rounding", () => {
    const input = new Float32Array([0, 0.5, -0.5, 1, -1, 1.5, -1.5]);
    const pcm = floatTo16BitPCM(input);
    expect(pcm[0]).toBe(0);
    expect(pcm[3]).toBe(0x7fff);
    expect(pcm[4]).toBe(-0x8000);
    expect(pcm[5]).toBe(0x7fff);
    expect(pcm[6]).toBe(-0x8000);
    const back = int16ToFloat32(pcm);
    expect(back[1]).toBeCloseTo(0.5, 3);
    expect(back[2]).toBeCloseTo(-0.5, 3);
  });

  it("downsamples by averaging to the target rate", () => {
    const input = new Float32Array(48000).fill(0.25);
    const out = downsample(input, 48000, 16000);
    expect(out.length).toBe(16000);
    expect(out[0]).toBeCloseTo(0.25, 6);
    expect(out[15999]).toBeCloseTo(0.25, 6);
  });

  it("copies the input when rates match", () => {
    const input = new Float32Array([0.1, 0.2]);
    expect(downsample(input, 16000, 16000)).toEqual(input);
  });

  it("computes rms", () => {
    expect(rms(new Float32Array([]))).toBe(0);
    expect(rms(new Float32Array([0.5, -0.5]))).toBeCloseTo(0.5, 6);
  });
});
