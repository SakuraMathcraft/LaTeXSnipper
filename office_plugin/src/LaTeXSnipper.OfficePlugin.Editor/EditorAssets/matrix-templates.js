(function () {
  "use strict";

  function cells(rows, cols, value) {
    return Array.from({ length: rows }, (_, row) =>
      Array.from({ length: cols }, (_, col) => value(row, col)).join(" & ")
    ).join(" \\\\ ");
  }

  function template(environment, rows, cols) {
    if (environment === "cases") {
      cols = 2;
    }

    if (environment === "jacobian") {
      const body = cells(
        rows,
        cols,
        (row, col) => `\\frac{\\partial f_{${row + 1}}}{\\partial x_{${col + 1}}}`
      );
      return `\\begin{bmatrix} ${body} \\end{bmatrix}`;
    }

    if (environment === "hessian") {
      const body = cells(
        rows,
        cols,
        (row, col) =>
          `\\frac{\\partial^2 f}{\\partial x_{${row + 1}}\\partial x_{${col + 1}}}`
      );
      return `\\begin{bmatrix} ${body} \\end{bmatrix}`;
    }

    if (environment === "identity") {
      const body = cells(rows, rows, (row, col) => row === col ? "1" : "0");
      return `\\begin{bmatrix} ${body} \\end{bmatrix}`;
    }

    if (environment === "diagonal") {
      const body = cells(
        rows,
        rows,
        (row, col) => row === col ? `a_{${row + 1}}` : "0"
      );
      return `\\begin{bmatrix} ${body} \\end{bmatrix}`;
    }

    if (environment === "augmented") {
      const alignment = `${"c".repeat(cols)}|c`;
      const body = cells(rows, cols + 1, () => "#?");
      return `\\left[\\begin{array}{${alignment}} ${body} \\end{array}\\right]`;
    }

    const body = cells(rows, cols, () => "#?");
    return `\\begin{${environment}} ${body} \\end{${environment}}`;
  }

  function insert(mathfield, environment, rows = 2, cols = 2) {
    mathfield.insert(template(environment, rows, cols), { format: "latex" });
    mathfield.focus();
  }

  window.LaTeXSnipperMatrixTemplates = Object.freeze({ insert, template });
})();
