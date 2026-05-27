import { BridgeClient } from "../services/bridgeClient";
import { EquationDraft } from "./wordInsert";

export async function insertEquationIntoPowerPoint(
  draft: EquationDraft,
  client: BridgeClient
): Promise<void> {
  const conversion = await client.convertLatex(draft.latex, ["png"]);
  if (!conversion.png_base64) {
    throw new Error("The bridge did not return a PowerPoint image.");
  }
  const number = resolveNumber(draft);
  const image = number
    ? await appendNumberToImage(conversion.png_base64, number)
    : await trimImageToContent(conversion.png_base64);
  await setSelectedImage(image);
}

function resolveNumber(draft: EquationDraft): string | undefined {
  if (draft.numbering === "manual") {
    return draft.manualNumber?.trim() || undefined;
  }
  if (draft.numbering === "auto") {
    throw new Error("PowerPoint numbered images require a manual number.");
  }
  return undefined;
}

function setSelectedImage(base64: string): Promise<void> {
  return new Promise((resolve, reject) => {
    Office.context.document.setSelectedDataAsync(
      base64,
      { coercionType: Office.CoercionType.Image },
      (result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) {
          resolve();
          return;
        }
        reject(new Error(result.error?.message || "Failed to insert image into PowerPoint."));
      }
    );
  });
}

function appendNumberToImage(base64: string, number: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const source = new Image();
    source.onload = () => {
      const numberWidth = Math.max(62, Math.ceil(source.height * 1.7));
      const canvas = document.createElement("canvas");
      canvas.width = source.width + numberWidth;
      canvas.height = source.height;
      const context = canvas.getContext("2d");
      if (!context) {
        reject(new Error("Failed to compose PowerPoint numbering."));
        return;
      }
      context.drawImage(source, 0, 0);
      context.fillStyle = "#111827";
      context.font = `${Math.max(16, Math.floor(source.height * 0.34))}px "Cambria Math", "Times New Roman", serif`;
      context.textAlign = "right";
      context.textBaseline = "middle";
      context.fillText(number, canvas.width - 8, canvas.height / 2);
      resolve(canvas.toDataURL("image/png").replace(/^data:image\/png;base64,/, ""));
    };
    source.onerror = () => reject(new Error("Failed to compose PowerPoint numbering."));
    source.src = `data:image/png;base64,${base64}`;
  });
}

function trimImageToContent(base64: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const source = new Image();
    source.onload = () => {
      const sourceCanvas = document.createElement("canvas");
      sourceCanvas.width = source.width;
      sourceCanvas.height = source.height;
      const sourceContext = sourceCanvas.getContext("2d", { willReadFrequently: true });
      if (!sourceContext) {
        reject(new Error("Failed to trim PowerPoint formula image."));
        return;
      }
      sourceContext.drawImage(source, 0, 0);
      const pixels = sourceContext.getImageData(0, 0, source.width, source.height).data;
      let left = source.width;
      let top = source.height;
      let right = -1;
      let bottom = -1;
      for (let y = 0; y < source.height; y += 1) {
        for (let x = 0; x < source.width; x += 1) {
          const offset = (y * source.width + x) * 4;
          const alpha = pixels[offset + 3];
          const containsInk = alpha > 8 && (
            alpha < 245 ||
            pixels[offset] < 248 ||
            pixels[offset + 1] < 248 ||
            pixels[offset + 2] < 248
          );
          if (!containsInk) {
            continue;
          }
          left = Math.min(left, x);
          top = Math.min(top, y);
          right = Math.max(right, x);
          bottom = Math.max(bottom, y);
        }
      }
      if (right < left || bottom < top) {
        resolve(base64);
        return;
      }
      const margin = 2;
      left = Math.max(0, left - margin);
      top = Math.max(0, top - margin);
      right = Math.min(source.width - 1, right + margin);
      bottom = Math.min(source.height - 1, bottom + margin);
      const canvas = document.createElement("canvas");
      canvas.width = right - left + 1;
      canvas.height = bottom - top + 1;
      const context = canvas.getContext("2d");
      if (!context) {
        reject(new Error("Failed to trim PowerPoint formula image."));
        return;
      }
      context.drawImage(source, left, top, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL("image/png").replace(/^data:image\/png;base64,/, ""));
    };
    source.onerror = () => reject(new Error("Failed to trim PowerPoint formula image."));
    source.src = `data:image/png;base64,${base64}`;
  });
}
