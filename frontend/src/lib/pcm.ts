export const VOICE_INPUT_RATE = 16000;
export const VOICE_OUTPUT_RATE = 24000;

export function floatTo16BitPCM(input: Float32Array): Int16Array<ArrayBuffer> {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]!));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

export function int16ToFloat32(input: Int16Array): Float32Array<ArrayBuffer> {
  const out = new Float32Array(input.length);
  for (let i = 0; i < input.length; i++) {
    out[i] = input[i]! / 0x8000;
  }
  return out;
}

export function downsample(input: Float32Array, fromRate: number, toRate: number): Float32Array<ArrayBuffer> {
  if (fromRate === toRate) return new Float32Array(input);
  const ratio = fromRate / toRate;
  const length = Math.floor(input.length / ratio);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j]!;
    out[i] = end > start ? sum / (end - start) : 0;
  }
  return out;
}

export function rms(input: Float32Array): number {
  if (input.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < input.length; i++) sum += input[i]! * input[i]!;
  return Math.sqrt(sum / input.length);
}
