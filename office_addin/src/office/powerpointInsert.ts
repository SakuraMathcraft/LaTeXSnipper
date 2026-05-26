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
  await setSelectedImage(conversion.png_base64);
  if (number) {
    await setSelectedText(` ${number}`);
  }
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

function setSelectedText(text: string): Promise<void> {
  return new Promise((resolve) => {
    Office.context.document.setSelectedDataAsync(
      text,
      { coercionType: Office.CoercionType.Text },
      () => resolve()
    );
  });
}
