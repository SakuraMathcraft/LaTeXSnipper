from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from functools import reduce
from operator import mul
from typing import Any

from sympy import (
    Catalan,
    E,
    EulerGamma,
    Eq,
    Expr,
    Float,
    GoldenRatio,
    Integral,
    Integer,
    Limit,
    Matrix as SympyMatrix,
    Poly,
    Product,
    Rational,
    Sum,
    Symbol,
    diff,
    expand as sp_expand,
    factor as sp_factor,
    latex as sp_latex,
    log,
    oo,
    pi,
    simplify as sp_simplify,
    sin,
    cos,
    tan,
    sqrt,
    exp,
    sympify,
    nsimplify,
)
from sympy import N as sp_numeric
from sympy import roots as sp_roots
from sympy.solvers import solve as sp_solve


@dataclass
class CasResult:
    success: bool
    latex: str = ""
    detail: str = ""
    status: str = ""
    source: str = "sympy"
    variable: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "success": self.success,
                "latex": self.latex,
                "detail": self.detail,
                "status": self.status,
                "source": self.source,
                "variable": self.variable,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_exception(cls, detail: str, status: str = "高级引擎求解失败") -> "CasResult":
        return cls(False, detail=detail, status=status)


class MathJsonConverter:
    _BOUND_WRAPPERS = {"Tuple", "Sequence", "List", "Hold", "Delimiter", "Range", "Pair", "Limits"}

    _CONST_MAP = {
        "Pi": pi,
        "ExponentialE": E,
        "PositiveInfinity": oo,
        "NegativeInfinity": -oo,
        "Infinity": oo,
        "Half": Rational(1, 2),
    }

    _UNARY_MAP = {
        "Sin": sin,
        "Cos": cos,
        "Tan": tan,
        "Sqrt": sqrt,
        "Exp": exp,
        "Ln": log,
        "Log": log,
    }

    def __init__(self) -> None:
        self._symbols: dict[str, Symbol] = {}

    def convert(self, node: Any) -> Any:
        if node is None:
            return sympify(0)
        if isinstance(node, bool):
            return sympify(int(node))
        if isinstance(node, int):
            return Integer(node)
        if isinstance(node, float):
            return Float(node)
        if isinstance(node, str):
            if node in self._CONST_MAP:
                return self._CONST_MAP[node]
            if node == "Nothing":
                return sympify(0)
            return self._symbols.setdefault(node, Symbol(node))
        if isinstance(node, dict):
            if "num" in node and "den" in node:
                return Rational(node["num"], node["den"])
            if "value" in node:
                return self.convert(node["value"])
            return sympify(0)
        if not isinstance(node, list) or not node:
            return sympify(0)

        head = node[0]
        args = node[1:]

        if head in {"Annotated", "Style", "Hold", "Error"} and args:
            return self.convert(args[0])
        if head in {"Tuple", "List", "Sequence"}:
            return [self.convert(arg) for arg in args] if head != "Tuple" else tuple(self.convert(arg) for arg in args)
        if head in self._UNARY_MAP and args:
            return self._UNARY_MAP[head](self.convert(args[0]))
        if head == "Negate" and args:
            return -self.convert(args[0])
        if head == "Add":
            return sum((self.convert(arg) for arg in args), sympify(0))
        if head == "Subtract":
            base = self.convert(args[0])
            for arg in args[1:]:
                base -= self.convert(arg)
            return base
        if head == "Multiply":
            return reduce(mul, (self.convert(arg) for arg in args), sympify(1))
        if head == "Divide":
            base = self.convert(args[0])
            for arg in args[1:]:
                base /= self.convert(arg)
            return base
        if head == "Power" and len(args) >= 2:
            return self.convert(args[0]) ** self.convert(args[1])
        if head == "Square" and args:
            return self.convert(args[0]) ** 2
        if head == "Equal" and len(args) >= 2:
            return Eq(self.convert(args[0]), self.convert(args[1]))
        if head == "Derivative" and len(args) >= 2:
            expr = self.convert(args[0])
            var = self._bound_variable(args[1])
            return diff(expr, var)
        if head in {"Integral", "Integrate"} and len(args) >= 2:
            expr = self.convert(args[0])
            return Integral(expr, self._extract_limits(args[1:]))
        if head == "Sum" and len(args) >= 2:
            expr = self.convert(args[0])
            return Sum(expr, self._extract_limits(args[1:]))
        if head == "Product" and len(args) >= 2:
            expr = self.convert(args[0])
            return Product(expr, self._extract_limits(args[1:]))
        if head == "Limit" and len(args) >= 3:
            expr = self.convert(args[0])
            bounds = self._extract_limits(args[1:])
            var = bounds[0] if bounds else self._symbols.setdefault("x", Symbol("x"))
            point = bounds[1] if len(bounds) > 1 else self.convert(args[2])
            return Limit(expr, var, point)
        if head == "Matrix" and args:
            rows = self.convert(args[0])
            if isinstance(rows, tuple):
                rows = list(rows)
            if not isinstance(rows, list):
                raise ValueError("Matrix 节点缺少有效的行列数据")
            normalized_rows: list[list[Any]] = []
            for row in rows:
                if isinstance(row, tuple):
                    row = list(row)
                if not isinstance(row, list):
                    row = [row]
                normalized_rows.append(row)
            return SympyMatrix(normalized_rows)
        if head == "Determinant" and args:
            matrix = self.convert(args[0])
            if hasattr(matrix, "det"):
                return matrix.det()
            raise ValueError("Determinant 节点未能转换为矩阵")

        return self._symbols.setdefault(str(head), Symbol(str(head)))

    def _bound_variable(self, node: Any) -> Symbol:
        converted = self.convert(node)
        if isinstance(converted, Symbol):
            return converted
        if hasattr(converted, "lhs") and isinstance(converted.lhs, Symbol):
            return converted.lhs
        return self._symbols.setdefault("x", Symbol("x"))

    def _bound_tuple(self, node: Any) -> tuple[Any, ...]:
        if isinstance(node, list) and node and node[0] == "Tuple":
            items = node[1:]
        else:
            items = [node]
        converted = [self.convert(item) for item in items]
        if len(converted) == 2 and hasattr(converted[0], "lhs") and hasattr(converted[0], "rhs"):
            return (converted[0].lhs, converted[0].rhs, converted[1])
        if len(converted) == 3:
            return tuple(converted)
        if converted:
            first = converted[0]
            if isinstance(first, Symbol):
                return (first,)
        return tuple(converted)

    def _bound_tuple_from_args(self, items: list[Any]) -> tuple[Any, ...]:
        if not items:
            return tuple()
        if len(items) == 1:
            return self._bound_tuple(items[0])
        converted = [self.convert(item) for item in items]
        if len(converted) >= 3:
            return tuple(converted[:3])
        if len(converted) == 2 and hasattr(converted[0], "lhs") and hasattr(converted[0], "rhs"):
            return (converted[0].lhs, converted[0].rhs, converted[1])
        return tuple(converted)

    def _extract_limits(self, items: list[Any]) -> tuple[Any, ...]:
        if not items:
            return tuple()

        flattened: list[Any] = []
        for item in items:
            flattened.extend(self._flatten_bound_node(item))

        symbol = next((item for item in flattened if isinstance(item, Symbol)), None)
        bounds = [item for item in flattened if not isinstance(item, Symbol)]

        if symbol is None and flattened and isinstance(flattened[0], Symbol):
            symbol = flattened[0]

        if symbol is not None and len(bounds) >= 2:
            return (symbol, bounds[0], bounds[1])
        if symbol is not None and len(bounds) == 1:
            return (symbol, bounds[0])

        fallback = self._bound_tuple_from_args(items)
        if len(fallback) >= 3:
            return fallback[:3]
        return fallback

    def _flatten_bound_node(self, node: Any) -> list[Any]:
        if isinstance(node, list) and node:
            head = node[0]
            args = node[1:]
            if head == "Equal" and len(args) >= 2:
                left = self.convert(args[0])
                right = self.convert(args[1])
                return [left, right]
            if head in self._BOUND_WRAPPERS:
                flat: list[Any] = []
                for arg in args:
                    flat.extend(self._flatten_bound_node(arg))
                return flat
        converted = self.convert(node)
        if isinstance(converted, tuple):
            return list(converted)
        return [converted]


def _pick_symbol(expr: Any) -> Symbol:
    free = sorted(getattr(expr, "free_symbols", []), key=lambda item: item.name)
    return free[0] if free else Symbol("x")


def _render_solution(variable: Symbol, solved: list[Any]) -> str:
    return ",\\;".join(f"{sp_latex(variable)} = {sp_latex(item)}" for item in solved)


def _is_heavy_expr(expr: Any) -> bool:
    return isinstance(expr, (Product, Sum, Integral, Limit))


def _recognize_symbolic_constant(expr: Any) -> Any:
    approx = sp_numeric(expr, 50)
    return nsimplify(
        approx,
        [pi, E, sqrt(2), sqrt(3), log(2), log(10), EulerGamma, Catalan, GoldenRatio],
    )


def _evaluate_or_recognize(expr: Any) -> Any:
    result = expr.doit() if hasattr(expr, "doit") else expr
    result = sp_simplify(result)
    if _is_heavy_expr(result) or result == expr:
        try:
            recognized = _recognize_symbolic_constant(expr)
            if recognized is not None:
                return recognized
        except Exception:
            pass
    return result


def _factor_via_roots(expr: Any) -> Any:
    variable = _pick_symbol(expr)
    poly = Poly(expr, variable)
    root_map = sp_roots(poly.as_expr(), variable)
    if not root_map:
        return expr

    rebuilt = poly.LC()
    for root, multiplicity in root_map.items():
        rebuilt *= (variable - root) ** multiplicity
    return rebuilt


def _solve_with_fallbacks(expr: Any, variable: Symbol) -> list[Any]:
    target = expr
    if isinstance(target, Expr):
        target = Eq(target, 0)

    solved = list(sp_solve(target, variable) or [])
    if solved:
        return solved

    try:
        poly = Poly(expr, variable)
    except Exception:
        poly = None

    if poly is not None:
        try:
            root_map = sp_roots(poly.as_expr(), variable)
            if root_map:
                roots_list: list[Any] = []
                for root, multiplicity in root_map.items():
                    roots_list.extend([root] * int(multiplicity))
                if roots_list:
                    return roots_list
        except Exception:
            pass

        try:
            numeric_roots = list(poly.nroots())
            if numeric_roots:
                return numeric_roots
        except Exception:
            pass

    return []


def _parse_simple_latex_atom(text: str) -> Any:
    raw = (text or "").strip()
    raw = raw.strip("{} ").replace(r"\left", "").replace(r"\right", "")
    if raw in {r"\infty", r"+\infty"}:
        return oo
    if raw == r"-\infty":
        return -oo
    if re.fullmatch(r"-?\d+", raw):
        return Integer(int(raw))
    frac = re.fullmatch(r"\\frac\{(-?\d+)\}\{(-?\d+)\}", raw)
    if frac:
        return Rational(int(frac.group(1)), int(frac.group(2)))
    if re.fullmatch(r"[a-zA-Z]+", raw):
        return Symbol(raw)
    return sympify(raw.replace("^", "**"))


def _extract_prod_sum_bounds_from_latex(latex: str) -> tuple[Symbol, Any, Any] | None:
    raw = (latex or "").replace(" ", "")
    m = re.search(r"\\(?:prod|sum)_\{([a-zA-Z]+)=([^}]*)\}\^\{([^}]*)\}", raw)
    if not m:
        return None
    var = Symbol(m.group(1))
    lower = _parse_simple_latex_atom(m.group(2))
    upper = _parse_simple_latex_atom(m.group(3))
    return (var, lower, upper)


def _extract_limit_bounds_from_latex(latex: str) -> tuple[Symbol, Any] | None:
    raw = (latex or "").replace(" ", "")
    m = re.search(r"\\lim_\{([a-zA-Z]+)\\to([^}]*)\}", raw)
    if not m:
        return None
    return (Symbol(m.group(1)), _parse_simple_latex_atom(m.group(2)))


def _convert_with_latex_bounds(converter: MathJsonConverter, parsed: Any, latex: str) -> Any:
    if not isinstance(parsed, list) or len(parsed) < 2:
        raise ValueError("原始表达式结构不足，无法从 LaTeX 回补上下界")

    head = parsed[0]
    expr = converter.convert(parsed[1])
    if head == "Product":
        bounds = _extract_prod_sum_bounds_from_latex(latex)
        if not bounds:
            raise ValueError("无法从 LaTeX 中识别乘积上下界")
        return Product(expr, bounds)
    if head == "Sum":
        bounds = _extract_prod_sum_bounds_from_latex(latex)
        if not bounds:
            raise ValueError("无法从 LaTeX 中识别求和上下界")
        return Sum(expr, bounds)
    if head in {"Integral", "Integrate"}:
        bounds = _extract_prod_sum_bounds_from_latex(latex.replace(r"\int", r"\sum", 1))
        if bounds:
            return Integral(expr, bounds)
        raise ValueError("无法从 LaTeX 中识别积分上下界")
    if head == "Limit":
        bounds = _extract_limit_bounds_from_latex(latex)
        if not bounds:
            raise ValueError("无法从 LaTeX 中识别极限目标")
        return Limit(expr, bounds[0], bounds[1])
    raise ValueError("当前表达式不支持 LaTeX 上下界回补")


def compute_from_mathjson(action: str, latex: str, mathjson_payload: str) -> CasResult:
    try:
        parsed = json.loads(mathjson_payload or "null")
    except Exception as e:
        return CasResult(False, detail=f"无法解析 MathJSON：{e}", status="高级引擎解析失败")

    converter = MathJsonConverter()
    try:
        expr = converter.convert(parsed)
    except Exception as e:
        message = str(e)
        try:
            expr = _convert_with_latex_bounds(converter, parsed, latex)
        except Exception:
            return CasResult(False, detail=f"无法转换为 SymPy 表达式：{message}", status="高级引擎转换失败")

    try:
        if action == "evaluate":
            result = _evaluate_or_recognize(expr)
            return CasResult(
                True,
                latex=sp_latex(result),
                detail="结果由本地高级求解引擎 SymPy/mpmath 提供。",
                status="已切换本地高级引擎完成计算",
            )
        if action == "numeric":
            result = expr.doit() if hasattr(expr, "doit") else expr
            result = sp_numeric(result, 30)
            return CasResult(
                True,
                latex=sp_latex(result),
                detail="结果由本地高级求解引擎提供数值近似。",
                status="已切换本地高级引擎完成数值化",
            )
        if action == "simplify":
            result = _evaluate_or_recognize(expr)
            return CasResult(
                True,
                latex=sp_latex(result),
                detail="结果由本地高级求解引擎完成化简。",
                status="已切换本地高级引擎完成化简",
            )
        if action == "expand":
            result = sp_expand(expr)
            return CasResult(
                True,
                latex=sp_latex(result),
                detail="结果由本地高级求解引擎完成展开。",
                status="已切换本地高级引擎完成展开",
            )
        if action == "factor":
            result = sp_factor(expr)
            if sp_simplify(result - expr) == 0 and sp_simplify(result) == sp_simplify(expr):
                try:
                    rebuilt = _factor_via_roots(expr)
                    if sp_simplify(rebuilt - expr) == 0:
                        result = rebuilt
                except Exception:
                    pass
            return CasResult(
                True,
                latex=sp_latex(result),
                detail="结果由本地高级求解引擎完成因式分解。",
                status="已切换本地高级引擎完成因式分解",
            )
        if action == "solve":
            variable = _pick_symbol(expr)
            solved = _solve_with_fallbacks(expr, variable)
            if not solved:
                return CasResult(False, detail=f"未找到关于 {variable} 的可用解", status="高级引擎未找到结果")
            return CasResult(
                True,
                latex=_render_solution(variable, solved),
                detail=f"结果由本地高级求解引擎完成关于 {variable} 的求解。",
                status="已切换本地高级引擎完成求解",
                variable=str(variable),
            )
        return CasResult(False, detail=f"暂不支持动作：{action}", status="高级引擎不支持该动作")
    except Exception as e:
        return CasResult(False, detail=f"本地高级求解失败：{e}", status="高级引擎求解失败")


def compute_from_mathjson_json(action: str, latex: str, mathjson_payload: str) -> str:
    return compute_from_mathjson(action, latex, mathjson_payload).to_json()


def compute_worker(action: str, latex: str, mathjson_payload: str) -> str:
    try:
        return compute_from_mathjson_json(action, latex, mathjson_payload)
    except Exception as e:
        return CasResult.from_exception(f"本地高级求解进程失败：{e}").to_json()


def _worker_main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw or "{}")
        action = str(payload.get("action", "") or "")
        latex = str(payload.get("latex", "") or "")
        mathjson_payload = str(payload.get("mathjson", "") or "")
        sys.stdout.write(compute_worker(action, latex, mathjson_payload))
        sys.stdout.flush()
        return 0
    except Exception as e:
        sys.stdout.write(CasResult.from_exception(f"本地高级求解进程失败：{e}").to_json())
        sys.stdout.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(_worker_main())
