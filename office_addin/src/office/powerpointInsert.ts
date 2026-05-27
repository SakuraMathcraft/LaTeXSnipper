import { BridgeClient } from "../services/bridgeClient";
import { allocateEquationNumber } from "../services/equationSession";
import { EquationDraft } from "./wordInsert";

export async function insertEquationIntoPowerPoint(
  draft: EquationDraft,
  client: BridgeClient
): Promise<void> {
  const conversion = await client.convertLatex(draft.latex, ["png"]);
  if (!conversion.png_base64) {
    throw new Error("The bridge did not return a PowerPoint image.");
  }
  const number = await resolveNumber(draft);
  const image = number ? await appendNumberToImage(conversion.png_base64, number) : conversion.png_base64;
  await setSelectedImage(image);
}

function resolveNumber(draft: EquationDraft): Promise<string | undefined> {
  if (draft.numbering === "manual") {
    return Promise.resolve(draft.manualNumber?.trim() || undefined);
  }
  if (draft.numbering === "auto") {
    return allocateEquationNumber();
  }
  return Promise.resolve(undefined);
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
