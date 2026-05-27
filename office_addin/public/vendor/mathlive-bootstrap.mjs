import { MathfieldElement } from "./mathlive.min.mjs";

if (!customElements.get("math-field")) {
  customElements.define("math-field", MathfieldElement);
}
