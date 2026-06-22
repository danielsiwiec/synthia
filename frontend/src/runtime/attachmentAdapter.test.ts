import { describe, it, expect } from "vitest";
import type { PendingAttachment } from "@assistant-ui/react";
import { attachmentAdapter } from "./attachmentAdapter";
import iphoneHeicUrl from "./__fixtures__/iphone.heic?url";

async function _loadHeicFixture(): Promise<File> {
  const response = await fetch(iphoneHeicUrl);
  const bytes = await response.arrayBuffer();
  return new File([bytes], "iphone.heic", { type: "" });
}

async function _makeImageFile(
  name: string,
  width: number,
  height: number,
): Promise<File> {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  const gradient = ctx.createLinearGradient(0, 0, width, height);
  gradient.addColorStop(0, "#ff0000");
  gradient.addColorStop(1, "#0000ff");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);
  const blob = await new Promise<Blob>((resolve) =>
    canvas.toBlob((b) => resolve(b!), "image/png"),
  );
  return new File([blob], name, { type: "image/png" });
}

describe("attachmentAdapter HEIC handling", () => {
  it("converts a HEIC attachment into a browser-renderable JPEG", async () => {
    const pending = (await attachmentAdapter.add({ file: await _loadHeicFixture() })) as PendingAttachment;

    expect(pending.type).toBe("image");
    expect(pending.contentType).toBe("image/jpeg");
    expect(pending.file.type).toBe("image/jpeg");
    expect(pending.file.name).toMatch(/\.jpg$/);

    const head = new Uint8Array(await pending.file.slice(0, 3).arrayBuffer());
    expect([...head]).toEqual([0xff, 0xd8, 0xff]);
  });
});

describe("attachmentAdapter image downscaling", () => {
  it("bounds an oversized image's long edge to 1568px and re-encodes as JPEG", async () => {
    const file = await _makeImageFile("large.png", 4032, 3024);
    const pending = (await attachmentAdapter.add({ file })) as PendingAttachment;

    expect(pending.type).toBe("image");
    expect(pending.contentType).toBe("image/jpeg");
    expect(pending.file.type).toBe("image/jpeg");
    expect(pending.file.name).toBe("large.jpg");

    const bitmap = await createImageBitmap(pending.file);
    expect(Math.max(bitmap.width, bitmap.height)).toBe(1568);
    expect(pending.file.size).toBeLessThan(file.size);
  });

  it("leaves an image already within bounds untouched", async () => {
    const file = await _makeImageFile("small.png", 800, 600);
    const pending = (await attachmentAdapter.add({ file })) as PendingAttachment;

    expect(pending.file).toBe(file);
    expect(pending.contentType).toBe("image/png");
  });
});
