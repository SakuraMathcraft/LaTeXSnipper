// @vitest-environment jsdom

import { describe, expect, it } from "vitest";

import {
  MathJaxRenderer,
  preprocessTexSource,
  validateMathMl,
} from "../src/rendering/mathJaxRenderer";

describe("MathJax rendering boundary", () => {
  it("reuses the Windows colorbox preprocessing semantics", () => {
    expect(preprocessTexSource("$x+1$")).toBe("x+1");
    expect(preprocessTexSource("\\colorbox{yellow}{$x^2$}")).toBe(
      "\\bbox[yellow]{x^2}",
    );
  });

  it("validates MathML before it can reach the Word adapter", () => {
    expect(validateMathMl('<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>'))
      .toContain("<mi>x</mi>");
    expect(() => validateMathMl("<div>x</div>")).toThrow(/有效 MathML/);
    expect(() => validateMathMl('<math xmlns="urn:not-mathml"><mi>x</mi></math>'))
      .toThrow(/有效 MathML/);
  });

  it("returns a cloned SVG and removes active or external content", async () => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("onload", "alert(1)");
    svg.setAttribute("style", "fill: url(https://example.invalid/image)");
    const externalLink = document.createElementNS("http://www.w3.org/2000/svg", "a");
    externalLink.setAttribute("href", "https://example.invalid/");
    const script = document.createElementNS("http://www.w3.org/2000/svg", "script");
    svg.append(externalLink, script);
    const container = document.createElement("div");
    container.append(svg);

    const renderer = new MathJaxRenderer(async () => ({
      startup: { promise: Promise.resolve() },
      tex2svg: () => container,
      tex2mml: () =>
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>',
    }));
    const rendered = await renderer.render("x", false);

    expect(rendered.svg).not.toBe(svg);
    expect(rendered.svg.hasAttribute("onload")).toBe(false);
    expect(rendered.svg.hasAttribute("style")).toBe(false);
    expect(rendered.svg.querySelector("script")).toBeNull();
    expect(rendered.svg.querySelector("a")?.hasAttribute("href")).toBe(false);
  });
});
