import { MathfieldElement } from "./vendor/mathlive.min.mjs";

const STRINGS = {
  en: {
    acceptInsert: "Insert",
    acceptUpdate: "Update",
    cancel: "Cancel",
    ready: "Ready",
    latexRequired: "Enter a LaTeX formula first.",
    rows: "Rows",
    columns: "Columns",
    tabs: {
      greek: "Greek",
      structures: "Structures",
      delimiters: "Delimiters",
      analysis: "Analysis",
      algebra: "Algebra",
      geometry: "Geometry",
      topology: "Topology",
      relations: "Relations",
      operators: "Operators",
      bigops: "Big Ops",
      arrows: "Arrows",
      sets: "Sets",
      functions: "Functions",
      probability: "Probability",
      chemistry: "Chemistry",
      physics: "Physics",
      accents: "Accents",
      misc: "Misc",
    },
  },
  zh: {
    acceptInsert: "插入",
    acceptUpdate: "更新",
    cancel: "取消",
    ready: "就绪",
    latexRequired: "请先输入 LaTeX 公式。",
    rows: "行数",
    columns: "列数",
    tabs: {
      greek: "希腊",
      structures: "结构",
      delimiters: "分隔符",
      analysis: "分析",
      algebra: "代数",
      geometry: "几何",
      topology: "拓扑",
      relations: "关系",
      operators: "运算",
      bigops: "大型",
      arrows: "箭头",
      sets: "集合",
      functions: "函数",
      probability: "概率",
      chemistry: "化学",
      physics: "物理",
      accents: "字体",
      misc: "其他",
    },
  },
};

const GROUPS = [
  {
    id: "greek",
    items: [
      ["α", "\\alpha"], ["β", "\\beta"], ["γ", "\\gamma"], ["δ", "\\delta"], ["π", "\\pi"],
      ["σ", "\\sigma"], ["θ", "\\theta"], ["λ", "\\lambda"], ["μ", "\\mu"], ["ω", "\\omega"],
      ["φ", "\\phi"], ["τ", "\\tau"], ["ε", "\\epsilon"], ["κ", "\\kappa"], ["ρ", "\\rho"],
      ["ζ", "\\zeta"], ["η", "\\eta"], ["ι", "\\iota"], ["ν", "\\nu"], ["ξ", "\\xi"],
      ["υ", "\\upsilon"], ["χ", "\\chi"], ["ψ", "\\psi"],
      ["Γ", "\\Gamma"], ["Δ", "\\Delta"], ["Θ", "\\Theta"], ["Λ", "\\Lambda"], ["Π", "\\Pi"],
      ["Σ", "\\Sigma"], ["Φ", "\\Phi"], ["Ψ", "\\Psi"], ["Ω", "\\Omega"], ["Ξ", "\\Xi"],
      ["ϑ", "\\vartheta"], ["ϕ", "\\varphi"], ["ϵ", "\\varepsilon"], ["ϰ", "\\varkappa"],
      ["ϖ", "\\varpi"], ["ϱ", "\\varrho"], ["ς", "\\varsigma"], ["ϝ", "\\digamma"],
      ["∂", "\\partial"], ["∇", "\\nabla"], ["∞", "\\infty"],
      ["ℵ", "\\aleph"], ["ℶ", "\\beth"], ["ℷ", "\\gimel"], ["ℸ", "\\daleth"],
    ],
  },
  {
    id: "structures",
    structures: true,
    items: [
      ["分数", "\\frac{#?}{#?}", "Fraction"],
      ["上标", "^{#?}", "Superscript"],
      ["下标", "_{#?}", "Subscript"],
      ["上下标", "_{#?}^{#?}", "Subscript and superscript"],
      ["根号", "\\sqrt{#?}", "Square root"],
      ["n 次根", "\\sqrt[#?]{#?}", "Nth root"],
      ["求和", "\\sum_{#?}^{#?} #?", "Summation"],
      ["积分", "\\int_{#?}^{#?} #?\\,d#?", "Integral"],
      ["极限", "\\lim_{#? \\to #?} #?", "Limit"],
      ["乘积", "\\prod_{#?}^{#?} #?", "Product"],
      ["二项式", "\\binom{#?}{#?}", "Binomial"],
      ["对齐", "\\begin{aligned} #? &= #? \\\\ #? &= #? \\end{aligned}", "Aligned equations"],
      ["分段", "matrix:cases", "Cases"],
      ["矩阵", "matrix:matrix", "Matrix"],
      ["方括号矩阵", "matrix:bmatrix", "Bracketed matrix"],
      ["海森矩阵", "matrix:hessian", "Hessian matrix"],
      ["行列式", "matrix:vmatrix", "Determinant"],
      ["圆括号矩阵", "matrix:pmatrix", "Parenthesized matrix"],
      ["花括号矩阵", "matrix:Bmatrix", "Braced matrix"],
    ],
  },
  {
    id: "delimiters",
    items: [
      ["( )", "\\left( #? \\right)", "Parentheses"],
      ["[ ]", "\\left[ #? \\right]", "Brackets"],
      ["{ }", "\\left\\{ #? \\right\\}", "Braces"],
      ["| |", "\\left| #? \\right|", "Absolute value"],
      ["‖ ‖", "\\left\\| #? \\right\\|", "Norm"],
      ["⟨ ⟩", "\\left\\langle #? \\right\\rangle", "Angle brackets"],
      ["⎡ ⎤", "\\left\\lceil #? \\right\\rceil", "Ceiling"],
      ["⎣ ⎦", "\\left\\lfloor #? \\right\\rfloor", "Floor"],
      ["⟦ ⟧", "\\left\\llbracket #? \\right\\rrbracket", "Double brackets"],
      ["⌜ ⌝", "\\left\\ulcorner #? \\right\\urcorner", "Top corners"],
      ["⌞ ⌟", "\\left\\llcorner #? \\right\\lrcorner", "Bottom corners"],
      ["/", "/", "Slash"],
      ["\\", "\\backslash", "Backslash"],
      ["( ]", "\\left( #? \\right]", "Half-open left"],
      ["[ )", "\\left[ #? \\right)", "Half-open right"],
      ["⎛ ⎞", "\\left\\lgroup #? \\right\\rgroup", "Grouping parentheses"],
      ["\\bigl( \\bigr)", "\\bigl(#?\\bigr)", "Big parentheses"],
      ["\\bigl[ \\bigr]", "\\bigl[#?\\bigr]", "Big brackets"],
      ["\\bigl\\{ \\bigr\\}", "\\bigl\\{#?\\bigr\\}", "Big braces"],
      ["\\bigl\\langle \\bigr\\rangle", "\\bigl\\langle#?\\bigr\\rangle", "Big angle brackets"],
      ["\\bigl\\lvert \\bigr\\rvert", "\\bigl\\lvert#?\\bigr\\rvert", "Big absolute"],
      ["\\bigl\\lVert \\bigr\\rVert", "\\bigl\\lVert#?\\bigr\\rVert", "Big norm"],
      ["\\left. \\right|", "\\left. #? \\right|_{#?}", "Evaluation at"],
      ["\\underbrace{}_{}", "\\underbrace{#?}_{#?}", "Underbrace"],
      ["\\overbrace{}^{}", "\\overbrace{#?}^{#?}", "Overbrace"],
      ["\\boxed{}", "\\boxed{#?}", "Boxed"],
      ["\\cancel{}", "\\cancel{#?}", "Cancel"],
      ["\\sout{}", "\\sout{#?}", "Strikethrough"],
      ["\\overset{}{}", "\\overset{#?}{#?}", "Overset"],
      ["\\underset{}{}", "\\underset{#?}{#?}", "Underset"],
      ["\\underline{}", "\\underline{#?}", "Underline"],
      ["\\overline{}", "\\overline{#?}", "Overline"],
      ["\\overrightarrow{}", "\\overrightarrow{#?}", "overrightarrow"],
      ["\\overleftarrow{}", "\\overleftarrow{#?}", "overleftarrow"],
    ],
  },
  {
    id: "analysis",
    structures: true,
    items: [
      ["导数", "\\frac{d}{dx}", "Derivative"],
      ["偏导", "\\frac{\\partial #?}{\\partial #?}", "Partial derivative"],
      ["微分", "#?\\,d#?", "Differential"],
      ["不定积分", "\\int #?\\,d#?", "Indefinite integral"],
      ["定积分", "\\int_{#?}^{#?} #?\\,d#?", "Definite integral"],
      ["极限", "\\lim_{#? \\to #?} #?", "Limit"],
      ["梯度", "\\nabla #?", "Gradient"],
      ["散度", "\\nabla\\cdot #?", "Divergence"],
      ["旋度", "\\nabla\\times #?", "Curl"],
      ["拉普拉斯", "\\nabla^2 #?", "Laplacian"],
      ["级数", "\\sum_{n=0}^{\\infty} #?", "Series"],
      ["泰勒", "\\sum_{n=0}^{\\infty} \\frac{#?^{(n)}(#?)}{n!}(x-#?)^n", "Taylor expansion"],
      ["方向导数", "\\nabla_{\\mathbf{v}} f", "Directional derivative"],
      ["雅可比", "\\frac{\\partial(#?,\\ldots)}{\\partial(#?,\\ldots)}", "Jacobian"],
      ["链式法则", "\\frac{d}{dt}f(\\mathbf{r}(t)) = \\nabla f\\cdot\\mathbf{r}'(t)", "Chain rule"],
      ["全微分", "df = \\frac{\\partial f}{\\partial x}dx + \\frac{\\partial f}{\\partial y}dy", "Total differential"],
      ["隐函数", "\\frac{dy}{dx} = -\\frac{\\partial F/\\partial x}{\\partial F/\\partial y}", "Implicit function"],
      ["拉格朗日乘数", "\\mathcal{L}(x,\\lambda) = f(x) - \\lambda g(x)", "Lagrange multiplier"],
      ["欧拉-拉格朗日", "\\frac{\\partial\\mathcal{L}}{\\partial q} - \\frac{d}{dt}\\frac{\\partial\\mathcal{L}}{\\partial\\dot{q}} = 0", "Euler-Lagrange"],
      ["拉普拉斯变换", "\\mathcal{L}\\{f\\}(s) = \\int_0^\\infty f(t)e^{-st}dt", "Laplace transform"],
      ["傅里叶变换", "\\hat{f}(\\xi) = \\int_{-\\infty}^{\\infty} f(x)e^{-2\\pi i x\\xi}dx", "Fourier transform"],
      ["傅里叶级数", "f(x) = \\sum_{n=-\\infty}^{\\infty} c_n e^{inx}", "Fourier series"],
      ["卷积", "(f * g)(x) = \\int_{-\\infty}^{\\infty} f(y)g(x-y)dy", "Convolution"],
      ["逆傅里叶", "f(x) = \\int_{-\\infty}^{\\infty} \\hat{f}(\\xi)e^{2\\pi i x\\xi}d\\xi", "Inverse Fourier transform"],
      ["高阶导", "\\frac{d^{#?}}{dx^{#?}}", "Higher derivative"],
      ["混合偏导", "\\frac{\\partial^2 #?}{\\partial #?\\,\\partial #?}", "Mixed partial"],
      ["物质导数", "\\frac{D}{Dt} = \\frac{\\partial}{\\partial t} + \\mathbf{v}\\cdot\\nabla", "Material derivative"],
      ["变分", "\\delta #?", "Variation"],
      ["上极限", "\\limsup_{#? \\to #?} #?", "Limit superior"],
      ["下极限", "\\liminf_{#? \\to #?} #?", "Limit inferior"],
      ["幂级数", "\\sum_{n=0}^{\\infty} a_n (x - c)^n", "Power series"],
      ["麦克劳林", "\\sum_{n=0}^{\\infty} \\frac{#?^{(n)}(0)}{n!} x^n", "Maclaurin series"],
      ["曲线积分", "\\oint #?\\,d#?", "Contour integral"],
      ["二重积分", "\\iint_{#?} #?\\,d#?", "Double integral"],
      ["曲面积分", "\\oiint_{#?} #?\\,dS", "Surface integral"],
      ["体积分", "\\iiint_{#?} #?\\,dV", "Volume integral"],
      ["双调和", "\\nabla^4 #?", "Biharmonic"],
      ["狄拉克 delta", "\\delta(x)", "Dirac delta"],
      ["单位阶跃", "H(x) = \\begin{cases}0 & x<0\\\\ 1 & x\\ge 0\\end{cases}", "Heaviside step"],
      ["符号函数", "\\operatorname{sgn}(x) = \\begin{cases}-1 & x<0\\\\ 0 & x=0\\\\ 1 & x>0\\end{cases}", "Sign function"],
      ["误差函数", "\\operatorname{erf}(x) = \\frac{2}{\\sqrt{\\pi}}\\int_0^x e^{-t^2}dt", "Error function"],
      ["伽马函数", "\\Gamma(z) = \\int_0^\\infty t^{z-1}e^{-t}dt", "Gamma function"],
      ["黎曼 zeta", "\\zeta(s) = \\sum_{n=1}^\\infty \\frac{1}{n^s}", "Riemann zeta"],
      ["热方程", "\\frac{\\partial u}{\\partial t} = \\alpha\\nabla^2 u", "Heat equation"],
      ["波动方程", "\\frac{\\partial^2 u}{\\partial t^2} = c^2\\nabla^2 u", "Wave equation"],
      ["拉普拉斯方程", "\\nabla^2 u = 0", "Laplace equation"],
      ["泊松方程", "\\nabla^2 u = f", "Poisson equation"],
      ["亥姆霍兹", "\\nabla^2 u + k^2 u = 0", "Helmholtz equation"],
      ["纳维-斯托克斯", "\\frac{\\partial\\mathbf{u}}{\\partial t}+(\\mathbf{u}\\cdot\\nabla)\\mathbf{u}=-\\nabla p+\\nu\\nabla^2\\mathbf{u}", "Navier-Stokes"],
      ["傅里叶系数", "c_n = \\frac{1}{2\\pi}\\int_{-\\pi}^{\\pi} f(x)e^{-inx}dx", "Fourier coefficient"],
      ["帕塞瓦尔", "\\sum_{n=-\\infty}^{\\infty} |c_n|^2 = \\frac{1}{2\\pi}\\int_{-\\pi}^{\\pi} |f(x)|^2dx", "Parseval identity"],
      ["普朗歇尔", "\\int_{-\\infty}^{\\infty} |f(x)|^2dx = \\int_{-\\infty}^{\\infty} |\\hat{f}(\\xi)|^2d\\xi", "Plancherel theorem"],
      ["赫尔德不等式", "\\int_\\Omega |fg|dx \\le \\left(\\int_\\Omega |f|^p dx\\right)^{1/p}\\left(\\int_\\Omega |g|^q dx\\right)^{1/q}", "Holder inequality"],
      ["闵可夫斯基", "\\left(\\int |f+g|^p\\right)^{1/p} \\le \\left(\\int |f|^p\\right)^{1/p} + \\left(\\int |g|^p\\right)^{1/p}", "Minkowski inequality"],
      ["庞加莱不等式", "\\int_\\Omega |u-\\bar{u}|^2 dx \\le C\\int_\\Omega |\\nabla u|^2 dx", "Poincare inequality"],
      ["索伯列夫范数", "\\|u\\|_{W^{k,p}(\\Omega)} = \\left(\\sum_{|\\alpha|\\le k}\\int_\\Omega |D^\\alpha u|^p dx\\right)^{1/p}", "Sobolev norm"],
      ["离散傅里叶", "\\hat{f}[k] = \\sum_{n=0}^{N-1} f[n]e^{-2\\pi i kn/N}", "Discrete Fourier transform"],
      ["短时傅里叶", "S(\\tau,\\omega) = \\int f(t)g(t-\\tau)e^{-i\\omega t}dt", "Short-time Fourier transform"],
      ["小波变换", "W_f(a,b) = \\frac{1}{\\sqrt{a}}\\int f(t)\\overline{\\psi\\!\\left(\\frac{t-b}{a}\\right)}dt", "Wavelet transform"],
      ["勒让德多项式", "P_n(x) = \\frac{1}{2^n n!}\\frac{d^n}{dx^n}(x^2-1)^n", "Legendre polynomials"],
      ["连带勒让德", "P_l^m(x) = (-1)^m(1-x^2)^{m/2}\\frac{d^m}{dx^m}P_l(x)", "Associated Legendre"],
      ["球谐函数", "Y_l^m(\\theta,\\phi) = \\sqrt{\\frac{2l+1}{4\\pi}\\frac{(l-m)!}{(l+m)!}}P_l^m(\\cos\\theta)e^{im\\phi}", "Spherical harmonics"],
      ["贝塞尔函数 J", "J_n(x) = \\sum_{k=0}^\\infty \\frac{(-1)^k}{k!\\,\\Gamma(n+k+1)}\\left(\\frac{x}{2}\\right)^{2k+n}", "Bessel J"],
      ["埃尔米特多项式", "H_n(x) = (-1)^n e^{x^2}\\frac{d^n}{dx^n}e^{-x^2}", "Hermite polynomials"],
      ["拉盖尔多项式", "L_n(x) = \\frac{e^x}{n!}\\frac{d^n}{dx^n}(x^n e^{-x})", "Laguerre polynomials"],
      ["切比雪夫 T", "T_n(x) = \\cos(n\\arccos x)", "Chebyshev T"],
      ["贝塔函数", "\\mathrm{B}(p,q) = \\int_0^1 t^{p-1}(1-t)^{q-1}dt", "Beta function"],
      ["超几何 2F1", "{}_2F_1(a,b;c;z) = \\sum_{n=0}^\\infty\\frac{(a)_n(b)_n}{(c)_n}\\frac{z^n}{n!}", "Hypergeometric 2F1"],
      ["输运方程", "\\frac{\\partial u}{\\partial t} + \\mathbf{a}\\cdot\\nabla u = 0", "Transport equation"],
      ["对流扩散", "\\frac{\\partial u}{\\partial t} + \\mathbf{v}\\cdot\\nabla u = D\\nabla^2 u", "Advection-diffusion"],
      ["伯格方程", "\\frac{\\partial u}{\\partial t} + u\\frac{\\partial u}{\\partial x} = \\nu\\frac{\\partial^2 u}{\\partial x^2}", "Burgers equation"],
      ["KdV 方程", "\\frac{\\partial u}{\\partial t} + u\\frac{\\partial u}{\\partial x} + \\frac{\\partial^3 u}{\\partial x^3} = 0", "KdV equation"],
      ["欧拉方程", "\\frac{\\partial\\mathbf{u}}{\\partial t}+(\\mathbf{u}\\cdot\\nabla)\\mathbf{u} = -\\nabla p", "Euler equations"],
      ["程函方程", "|\\nabla u| = 1", "Eikonal equation"],
      ["反应扩散", "\\frac{\\partial u}{\\partial t} = D\\nabla^2 u + f(u)", "Reaction-diffusion"],
      ["希尔伯特变换", "\\mathcal{H}f(x) = \\frac{1}{\\pi}\\operatorname{p.v.}\\int_{-\\infty}^{\\infty}\\frac{f(y)}{x-y}dy", "Hilbert transform"],
      ["泊松求和", "\\sum_{n=-\\infty}^{\\infty} f(n) = \\sum_{k=-\\infty}^{\\infty} \\hat{f}(k)", "Poisson summation"],
      ["拉普拉斯逆", "f(t) = \\frac{1}{2\\pi i}\\int_{\\sigma-i\\infty}^{\\sigma+i\\infty}F(s)e^{st}ds", "Inverse Laplace"],
      ["梅林变换", "\\mathcal{M}\\{f\\}(s) = \\int_0^\\infty f(x)x^{s-1}dx", "Mellin transform"],
      ["拉克斯-米尔格拉姆", "a(u,v) = \\langle f, v \\rangle \\quad \\forall v \\in V", "Lax-Milgram"],
      ["里斯表示", "\\langle f, \\cdot \\rangle \\leftrightarrow f", "Riesz representation"],
      ["弗雷歇导数", "Df(x)[h] = \\lim_{t\\to 0}\\frac{f(x+th)-f(x)}{t}", "Frechet derivative"],
      ["黑-舒尔斯", "\\frac{\\partial V}{\\partial t}+\\frac12\\sigma^2 S^2\\frac{\\partial^2 V}{\\partial S^2}+rS\\frac{\\partial V}{\\partial S}-rV=0", "Black-Scholes"],
      ["索伯列夫嵌入", "W^{k,p}(\\Omega) \\hookrightarrow L^q(\\Omega)", "Sobolev embedding"],
      ["索伯列夫不等式", "\\|u\\|_{L^q(\\mathbb{R}^n)} \\le C\\|\\nabla u\\|_{L^p(\\mathbb{R}^n)}", "Sobolev inequality"],
      ["雅可比椭圆 sn", "\\operatorname{sn}(u,k)", "Jacobi elliptic sn"],
      ["δ 函数", "\\delta_{ij} = \\begin{cases}1 & i=j\\\\ 0 & i\\ne j\\end{cases}", "Kronecker delta"],
      ["缓增分布", "\\mathcal{S}'(\\mathbb{R}^n)", "Tempered distributions"],
      ["施瓦茨空间", "\\mathcal{S}(\\mathbb{R}^n) = \\left\\{\\varphi\\in C^\\infty: \\sup|x^\\alpha D^\\beta\\varphi|<\\infty\\right\\}", "Schwartz space"],
    ],
  },
  {
    id: "algebra",
    structures: true,
    items: [
      ["点乘", "#? \\cdot #?", "Dot product"],
      ["叉乘", "#? \\times #?", "Cross product"],
      ["内积", "\\left\\langle #?, #? \\right\\rangle", "Inner product"],
      ["范数", "\\left\\| #? \\right\\|", "Norm"],
      ["转置", "#?^{\\mathsf{T}}", "Transpose"],
      ["逆矩阵", "#?^{-1}", "Inverse"],
      ["迹", "\\operatorname{tr}(#?)", "Trace"],
      ["行列式", "\\det(#?)", "Determinant"],
      ["秩", "\\operatorname{rank}(#?)", "Rank"],
      ["特征值", "\\lambda", "Eigenvalue"],
      ["特征向量", "\\mathbf{v}", "Eigenvector"],
      ["单位阵", "I_{#?}", "Identity matrix"],
      ["对角阵", "\\operatorname{diag}(#?)", "Diagonal matrix"],
      ["向量列", "\\begin{bmatrix} #? \\\\ #? \\end{bmatrix}", "Column vector"],
      ["核", "\\ker(#?)", "Kernel"],
      ["像", "\\operatorname{im}(#?)", "Image"],
      ["余核", "\\operatorname{coker}(#?)", "Cokernel"],
      ["张成", "\\operatorname{span}\\{#?\\}", "Span"],
      ["正交投影", "\\mathbf{P} = \\mathbf{A}(\\mathbf{A}^{\\mathsf{T}}\\!\\mathbf{A})^{-1}\\mathbf{A}^{\\mathsf{T}}", "Projection"],
      ["最小二乘", "\\mathbf{A}^{\\mathsf{T}}\\!\\mathbf{A}\\mathbf{x} = \\mathbf{A}^{\\mathsf{T}}\\!\\mathbf{b}", "Least squares"],
      ["伪逆", "\\mathbf{A}^+", "Pseudoinverse"],
      ["群", "G", "Group"],
      ["阿贝尔群", "\\mathbb{Z}_n", "Abelian group"],
      ["环", "R", "Ring"],
      ["域", "\\mathbb{F}", "Field"],
      ["同态", "\\varphi: G \\to H", "Homomorphism"],
      ["同构", "G \\cong H", "Isomorphism"],
      ["自同构", "\\operatorname{Aut}(G)", "Automorphism"],
      ["理想", "I \\triangleleft R", "Ideal"],
      ["商群", "G / N", "Quotient group"],
      ["商环", "R / I", "Quotient ring"],
      ["置换群", "S_n", "Symmetric group"],
      ["循环群", "C_n", "Cyclic group"],
      ["二面体群", "D_{2n}", "Dihedral group"],
      ["群作用", "G \\times X \\to X", "Group action"],
      ["多项式环", "K[x_1,\\ldots,x_n]", "Polynomial ring"],
      ["局部化", "S^{-1}R", "Localization"],
      ["整环", "R \\text{ integral domain}", "Integral domain"],
      ["PID", "R \\text{ PID}", "Principal ideal domain"],
      ["UFD", "R \\text{ UFD}", "Unique factorization domain"],
      ["欧几里得环", "R \\text{ Euclidean}", "Euclidean domain"],
      ["有限域", "\\mathbb{F}_q", "Finite field"],
      ["代数闭包", "\\overline{K}", "Algebraic closure"],
      ["伽罗瓦群", "\\operatorname{Gal}(L/K)", "Galois group"],
      ["域扩张", "L/K", "Field extension"],
      ["正合列", "A \\xrightarrow{f} B \\xrightarrow{g} C", "Exact sequence"],
      ["短正合列", "0 \\to A \\xrightarrow{f} B \\xrightarrow{g} C \\to 0", "Short exact sequence"],
      ["蛇形引理", "\\ker f \\to \\ker g \\to \\ker h \\xrightarrow{\\delta} \\operatorname{coker}f \\to \\operatorname{coker}g \\to \\operatorname{coker}h", "Snake lemma"],
      ["张量积", "M \\otimes_R N", "Tensor product"],
      ["直和", "V \\oplus W", "Direct sum"],
      ["交换图", "\\begin{CD}A@>f>>B\\\\@VgVV@VVhV\\\\C@>k>>D\\end{CD}", "Commutative diagram"],
      ["李括号", "[X,Y]", "Lie bracket"],
      ["指数映射", "\\exp: \\mathfrak{g} \\to G", "Exponential map"],
      ["Killing 型", "B(X,Y) = \\operatorname{tr}(\\operatorname{ad}_X \\circ \\operatorname{ad}_Y)", "Killing form"],
      ["根系", "\\Phi \\subset \\mathfrak{h}^*", "Root system"],
      ["单李代数", "\\mathfrak{g}", "Simple Lie algebra"],
      ["最高权", "V(\\lambda)", "Highest weight module"],
      ["函子", "F: \\mathcal{C} \\to \\mathcal{D}", "Functor"],
      ["自然变换", "\\eta: F \\Rightarrow G", "Natural transformation"],
      ["伴随", "F \\dashv G", "Adjoint functor"],
      ["极限", "\\varprojlim F", "Limit"],
      ["余极限", "\\varinjlim F", "Colimit"],
      ["链复形", "\\cdots \\to C_{n+1} \\xrightarrow{\\partial} C_n \\xrightarrow{\\partial} C_{n-1} \\to \\cdots", "Chain complex"],
      ["同调", "H_n(C) = \\ker\\partial_n / \\operatorname{im}\\partial_{n+1}", "Homology"],
      ["上同调", "H^n(C) = \\ker d_n / \\operatorname{im} d_{n-1}", "Cohomology"],
      ["Tor", "\\operatorname{Tor}_n^R(A,B)", "Tor functor"],
      ["Ext", "\\operatorname{Ext}^n_R(A,B)", "Ext functor"],
      ["投射模", "P \\text{ projective}", "Projective module"],
      ["内射模", "I \\text{ injective}", "Injective module"],
      ["导出函子", "R^nF(A)", "Derived functor"],
      ["谱序列", "E^r_{p,q} \\Rightarrow E^\\infty_{p+q}", "Spectral sequence"],
      ["群上同调", "H^n(G,M)", "Group cohomology"],
      ["导出范畴", "D(\\mathcal{A})", "Derived category"],
      ["外代数", "\\bigwedge(V)", "Exterior algebra"],
      ["对称代数", "\\operatorname{Sym}(V)", "Symmetric algebra"],
      ["张量代数", "T(V)", "Tensor algebra"],
      ["Spec", "\\operatorname{Spec}(R)", "Prime spectrum"],
      ["Proj", "\\operatorname{Proj}(S)", "Projective spectrum"],
      ["概形", "(X,\\mathcal{O}_X)", "Scheme"],
      ["仿射簇", "V(f_1,\\ldots,f_k) \\subset \\mathbb{A}^n", "Affine variety"],
      ["射影簇", "V_+(F_1,\\ldots,F_k) \\subset \\mathbb{P}^n", "Projective variety"],
      ["C*-代数", "\\mathcal{A}", "C*-algebra"],
      ["李群", "G \\text{ Lie group}", "Lie group"],
      ["李代数", "\\mathfrak{g} = T_eG", "Lie algebra"],
      ["PBW 定理", "\\operatorname{gr} U(\\mathfrak{g}) \\cong \\operatorname{Sym}(\\mathfrak{g})", "PBW theorem"],
    ],
  },
  {
    id: "geometry",
    structures: true,
    items: [
      ["角度", "\\theta", "Angle"],
      ["度", "^\\circ", "Degree"],
      ["曲率", "\\kappa = \\frac{|\\mathbf{r}'\\times\\mathbf{r}''|}{|\\mathbf{r}'|^3}", "Curvature"],
      ["挠率", "\\tau = \\frac{(\\mathbf{r}'\\times\\mathbf{r}'')\\cdot\\mathbf{r}'''}{|\\mathbf{r}'\\times\\mathbf{r}''|^2}", "Torsion"],
      ["弧长", "s = \\int \\sqrt{g_{ij}dx^i dx^j}", "Arc length"],
      ["第一基本形式", "\\mathrm{I} = E\\,du^2 + 2F\\,du\\,dv + G\\,dv^2", "First fundamental form"],
      ["第二基本形式", "\\mathrm{II} = L\\,du^2 + 2M\\,du\\,dv + N\\,dv^2", "Second fundamental form"],
      ["高斯曲率", "K = \\frac{LN-M^2}{EG-F^2}", "Gaussian curvature"],
      ["平均曲率", "H = \\frac{EN+GL-2FM}{2(EG-F^2)}", "Mean curvature"],
      ["度量张量", "g = g_{ij}\\,dx^i\\otimes dx^j", "Metric tensor"],
      ["克里斯托费尔", "\\Gamma^k_{ij} = \\frac12 g^{kl}\\left(\\partial_i g_{jl}+\\partial_j g_{il}-\\partial_l g_{ij}\\right)", "Christoffel symbols"],
      ["协变导数", "\\nabla_i V^j = \\partial_i V^j + \\Gamma^j_{ik}V^k", "Covariant derivative"],
      ["李导数", "\\mathcal{L}_X Y = [X,Y]", "Lie derivative"],
      ["黎曼曲率", "R^i_{jkl} = \\partial_k\\Gamma^i_{jl}-\\partial_l\\Gamma^i_{jk}+\\Gamma^i_{mk}\\Gamma^m_{jl}-\\Gamma^i_{ml}\\Gamma^m_{jk}", "Riemann curvature"],
      ["里奇曲率", "R_{ij} = R^k_{ikj}", "Ricci curvature"],
      ["标量曲率", "R = g^{ij}R_{ij}", "Scalar curvature"],
      ["爱因斯坦张量", "G_{\\mu\\nu} = R_{\\mu\\nu} - \\frac12 R g_{\\mu\\nu}", "Einstein tensor"],
      ["测地线", "\\frac{d^2x^i}{dt^2}+\\Gamma^i_{jk}\\frac{dx^j}{dt}\\frac{dx^k}{dt}=0", "Geodesic"],
      ["平行移动", "V^i(t) = V^i(0) - \\int_0^t \\Gamma^i_{jk}\\dot{x}^j V^k dt", "Parallel transport"],
      ["联络", "\\nabla_X Y", "Connection"],
      ["切空间", "T_pM", "Tangent space"],
      ["余切空间", "T^*_pM", "Cotangent space"],
      ["微分形式", "\\Omega^k(M)", "Differential forms"],
      ["外微分", "d\\omega", "Exterior derivative"],
      ["楔积", "\\omega \\wedge \\eta", "Wedge product"],
      ["霍奇星", "\\star \\omega", "Hodge star"],
      ["霍奇拉普拉斯", "\\Delta = d\\!\\!\\!^\\dagger d + d d\\!\\!\\!^\\dagger", "Hodge Laplacian"],
      ["向量场", "X = X^i\\partial_i", "Vector field"],
      ["流", "\\phi_t: M \\to M", "Flow"],
      ["德拉姆上同调", "H^k_{\\mathrm{dR}}(M)", "de Rham cohomology"],
      ["霍奇定理", "H^k_{\\mathrm{dR}}(M) \\cong \\mathcal{H}^k(M)", "Hodge theorem"],
      ["霍奇分解", "\\Omega^k = \\operatorname{im}d \\oplus \\operatorname{im}d^\\dagger \\oplus \\mathcal{H}^k", "Hodge decomposition"],
      ["高斯-博内", "\\int_M K\\,dA = 2\\pi\\chi(M)", "Gauss-Bonnet theorem"],
      ["高斯-博内-陈", "\\int_M \\operatorname{Pf}(\\Omega) = (2\\pi)^n\\chi(M)", "Chern-Gauss-Bonnet"],
      ["陈类", "c_1(L) = \\left[\\frac{i}{2\\pi}F\\right]", "Chern class"],
      ["陈数", "\\int_M c_1(L) \\in \\mathbb{Z}", "Chern number"],
      ["陈特征", "\\operatorname{ch}(E) = \\operatorname{tr}\\exp\\!\\left(\\frac{i}{2\\pi}F\\right)", "Chern character"],
      ["托德类", "\\operatorname{Td}(TM)", "Todd class"],
      ["阿蒂亚-辛格", "\\operatorname{ind}(D) = \\int_M \\hat{A}(M)\\,\\operatorname{ch}(E)", "Atiyah-Singer index"],
      ["狄拉克算子", "\\displaystyle{\\not}D = \\gamma^\\mu\\nabla_\\mu", "Dirac operator"],
      ["旋量", "\\psi \\in \\Gamma(S)", "Spinor"],
      ["联络形式", "\\omega", "Connection form"],
      ["曲率形式", "\\Omega = d\\omega + \\omega\\wedge\\omega", "Curvature form"],
      ["规范场", "F = dA + A\\wedge A", "Gauge field"],
      ["杨-米尔斯", "D_\\mu F^{\\mu\\nu} = 0", "Yang-Mills equation"],
      ["陈-西蒙斯", "S_{\\mathrm{CS}} = \\int \\operatorname{tr}\\!\\left(A\\wedge dA + \\frac23 A\\wedge A\\wedge A\\right)", "Chern-Simons"],
      ["瞬子", "F = \\star F", "Instanton"],
      ["自对偶", "F^+ = 0", "Self-dual"],
      ["里奇流", "\\frac{\\partial g}{\\partial t} = -2\\operatorname{Ric}(g)", "Ricci flow"],
      ["爱因斯坦方程", "R_{\\mu\\nu} - \\frac12 R g_{\\mu\\nu} = 8\\pi T_{\\mu\\nu}", "Einstein field equations"],
      ["闵氏度量", "\\eta_{\\mu\\nu} = \\operatorname{diag}(-1,1,1,1)", "Minkowski metric"],
      ["凯勒流形", "(M, g, J, \\omega)", "Kahler manifold"],
      ["凯勒度量", "\\omega = i\\partial\\bar\\partial\\varphi", "Kahler metric"],
      ["卡拉比-丘", "c_1(M) = 0", "Calabi-Yau manifold"],
      ["Â-类", "\\hat{A}(M) = \\prod_{i=1}^n \\frac{x_i/2}{\\sinh(x_i/2)}", "A-hat genus"],
      ["L-类", "L(M) = \\prod_{i=1}^n \\frac{x_i}{\\tanh x_i}", "L-genus"],
      ["拉普拉斯-贝特拉米", "\\Delta = -\\star d\\!\\!\\!^\\dagger d \\star", "Laplace-Beltrami"],
      ["消灭定理", "H^0(M, K_M) = 0", "Vanishing theorem"],
      ["小平消灭", "H^q(M, \\Omega^p(K_M)) = 0 \\quad p+q>n", "Kodaira vanishing"],
      ["辛流形", "(M, \\omega)", "Symplectic manifold"],
      ["泊松括号", "\\{f,g\\} = \\omega(X_f,X_g)", "Poisson bracket"],
      ["矩映射", "\\mu: M \\to \\mathfrak{g}^*", "Moment map"],
    ],
  },
  {
    id: "topology",
    structures: true,
    items: [
      ["开集", "U \\subset X", "Open set"],
      ["闭集", "F \\subset X", "Closed set"],
      ["紧致", "K \\subset X", "Compact"],
      ["连通", "X \\text{ connected}", "Connected"],
      ["道路连通", "\\pi_0(X) = 0", "Path-connected"],
      ["内部", "\\operatorname{int}(A)", "Interior"],
      ["闭包", "\\overline{A}", "Closure"],
      ["边界", "\\partial A", "Boundary"],
      ["邻域", "U \\ni x", "Neighborhood"],
      ["聚点", "x'", "Limit point"],
      ["度量空间", "(X,d)", "Metric space"],
      ["拓扑空间", "(X,\\mathcal{T})", "Topological space"],
      ["连续映射", "f: X \\to Y", "Continuous map"],
      ["同胚", "X \\cong Y", "Homeomorphism"],
      ["同伦", "f \\simeq g", "Homotopy"],
      ["基本群", "\\pi_1(X,x_0)", "Fundamental group"],
      ["高阶同伦", "\\pi_n(X)", "Higher homotopy group"],
      ["同调", "H_n(X;\\mathbb{Z})", "Homology"],
      ["上同调", "H^n(X;\\mathbb{Z})", "Cohomology"],
      ["贝蒂数", "b_n = \\operatorname{rank} H_n(X)", "Betti numbers"],
      ["欧拉示性数", "\\chi(X) = \\sum_{n}(-1)^n b_n", "Euler characteristic"],
      ["CW 复形", "X = \\bigcup_{n} X^{(n)}", "CW complex"],
      ["单纯形", "\\Delta^n", "Simplex"],
      ["复形", "K", "Simplicial complex"],
      ["胞腔同调", "H_n(X) \\cong H_n^{\\mathrm{CW}}(X)", "Cellular homology"],
      ["流形", "M^n", "Manifold"],
      ["带边流形", "\\partial M", "Manifold with boundary"],
      ["豪斯多夫", "T_2", "Hausdorff"],
      ["第二可数", "\\text{second countable}", "Second countable"],
      ["映射度", "\\deg(f) = \\sum_{x\\in f^{-1}(y)} \\operatorname{sgn} \\det df_x", "Mapping degree"],
      ["不动点", "\\operatorname{Fix}(f) = \\{x: f(x)=x\\}", "Fixed point"],
      ["莱夫谢茨", "L(f) = \\sum_k (-1)^k \\operatorname{tr}(f_*: H_k \\to H_k)", "Lefschetz number"],
      ["覆叠空间", "p: \\tilde{X} \\to X", "Covering space"],
      ["万有覆叠", "\\tilde{X}", "Universal cover"],
      ["纤维丛", "F \\to E \\xrightarrow{\\pi} B", "Fiber bundle"],
      ["向量丛", "E \\to M", "Vector bundle"],
      ["切丛", "TM", "Tangent bundle"],
      ["余切丛", "T^*M", "Cotangent bundle"],
      ["法丛", "\\nu = TM / T\\partial M", "Normal bundle"],
      ["球丛", "S(E) \\to M", "Sphere bundle"],
      ["悬垂", "\\Sigma X", "Suspension"],
      ["楔和", "X \\vee Y", "Wedge sum"],
      [" smash ", "X \\wedge Y", "Smash product"],
      ["无交并", "X \\sqcup Y", "Disjoint union"],
      ["拓扑和", "X \\cup_f Y", "Attaching space"],
      ["映射锥", "C_f = Y \\cup_f CX", "Mapping cone"],
      ["环路空间", "\\Omega X", "Loop space"],
      ["同伦纤维", "\\operatorname{hofib}(f)", "Homotopy fiber"],
      ["范坎彭", "\\pi_1(X) \\cong \\pi_1(U) *_{\\pi_1(U\\cap V)} \\pi_1(V)", "van Kampen theorem"],
      ["切除", "H_n(X,A) \\cong H_n(X\\setminus Z, A\\setminus Z)", "Excision theorem"],
      ["迈耶-维托里斯", "\\cdots\\!\\to\\!H_n(A\\cap B)\\!\\to\\!H_n(A)\\oplus H_n(B)\\!\\to\\!H_n(X)\\!\\to\\!H_{n-1}(A\\cap B)\\!\\to\\!\\cdots", "Mayer-Vietoris"],
      ["万有系数", "0 \\to H_n(X)\\otimes G \\to H_n(X;G) \\to \\operatorname{Tor}(H_{n-1}(X),G) \\to 0", "Universal coefficient"],
      ["Kunneth", "H_n(X\\times Y) \\cong \\bigoplus_{i+j=n} H_i(X)\\otimes H_j(Y)", "Kunneth formula"],
      ["庞加莱对偶", "H^k(M) \\cong H_{n-k}(M)", "Poincare duality"],
      ["杯积", "H^k \\times H^l \\xrightarrow{\\smile} H^{k+l}", "Cup product"],
      ["上同调环", "H^*(M)", "Cohomology ring"],
      ["示性类", "c(E) \\in H^*(B)", "Characteristic class"],
      ["陈类", "c_i(E) \\in H^{2i}(B;\\mathbb{Z})", "Chern class"],
      ["庞蒂亚金类", "p_i(E) \\in H^{4i}(B;\\mathbb{Z})", "Pontryagin class"],
      ["欧拉类", "e(E) \\in H^n(B;\\mathbb{Z})", "Euler class"],
      ["施蒂费尔-惠特尼", "w_i(E) \\in H^i(B;\\mathbb{Z}_2)", "Stiefel-Whitney class"],
      ["莫尔斯函数", "f: M \\to \\mathbb{R}", "Morse function"],
      ["临界点", "\\nabla f(p) = 0", "Critical point"],
      ["莫尔斯不等式", "M_k \\ge b_k", "Morse inequality"],
      ["莫尔斯同调", "HM_k(M,f)", "Morse homology"],
      ["塞尔谱序列", "E^2_{p,q} = H_p(B; H_q(F)) \\Rightarrow H_{p+q}(E)", "Serre spectral sequence"],
      ["托姆同构", "H^k(B) \\cong H^{k+n}(E,E_0)", "Thom isomorphism"],
      ["吉辛序列", "\\cdots \\to H^k(B) \\to H^k(S(E)) \\to H^{k-n+1}(B) \\to \\cdots", "Gysin sequence"],
      ["分类空间", "BG", "Classifying space"],
      ["普遍丛", "EG \\to BG", "Universal bundle"],
      ["配边", "\\Omega_n^O", "Cobordism"],
      ["拓扑量子场论", "Z: \\operatorname{Cob}_d \\to \\operatorname{Vect}", "TQFT"],
      ["上同调运算", "\\mathcal{O}: H^n(X;\\mathbb{Z}_p) \\to H^{n+k}(X;\\mathbb{Z}_p)", "Cohomology operation"],
      ["Steenrod 平方", "\\operatorname{Sq}^k: H^n \\to H^{n+k}", "Steenrod square"],
      ["代数K理论", "K_0(R),\\; K_1(R)", "Algebraic K-theory"],
      ["拓扑K理论", "K(X)", "Topological K-theory"],
      ["Bott 周期性", "K(X) \\cong K(\\Sigma^2 X)", "Bott periodicity"],
    ],
  },
  {
    id: "relations",
    items: [
      ["=", "="], ["≠", "\\neq"], ["≈", "\\approx"], ["≡", "\\equiv"], ["∼", "\\sim"], ["≅", "\\cong"],
      ["≃", "\\simeq"], ["∝", "\\propto"], ["<", "<"], [">", ">"], ["≤", "\\leq"], ["≥", "\\geq"],
      ["≪", "\\ll"], ["≫", "\\gg"], ["≦", "\\leqq"], ["≧", "\\geqq"],
      ["≲", "\\lesssim"], ["≳", "\\gtrsim"], ["⪅", "\\lessapprox"], ["⪆", "\\gtrapprox"],
      ["≶", "\\lessgtr"], ["≷", "\\gtrless"], ["⋚", "\\lesseqgtr"], ["⋛", "\\gtreqless"],
      ["∈", "\\in"], ["∉", "\\notin"], ["∋", "\\ni"], ["⊂", "\\subset"], ["⊃", "\\supset"],
      ["⊆", "\\subseteq"], ["⊇", "\\supseteq"], ["⊊", "\\subsetneq"], ["⊋", "\\supsetneq"],
      ["⊄", "\\not\\subset"], ["⊅", "\\not\\supset"], ["⊈", "\\nsubseteq"], ["⊉", "\\nsupseteq"],
      ["⊏", "\\sqsubset"], ["⊐", "\\sqsupset"], ["⊑", "\\sqsubseteq"], ["⊒", "\\sqsupseteq"],
      ["≺", "\\prec"], ["≻", "\\succ"], ["≼", "\\preceq"], ["≽", "\\succeq"],
      ["⋞", "\\preccurlyeq"], ["⋟", "\\succcurlyeq"],
      ["∥", "\\parallel"], ["∦", "\\nparallel"], ["⊥", "\\perp"],
      ["∴", "\\therefore"], ["∵", "\\because"],
      ["≔", "\\coloneqq"], ["≕", "\\eqqcolon"], ["≜", "\\triangleq"],
      ["≑", "\\doteqdot"], ["≐", "\\doteq"], ["≗", "\\circeq"], ["≖", "\\eqcirc"],
      ["≘", "\\arceq"], ["≙", "\\widehat{=}"], ["≚", "\\veeeq"],
      ["≒", "\\fallingdotseq"], ["≓", "\\risingdotseq"], ["≊", "\\approxeq"],
      ["≉", "\\napprox"], ["≄", "\\nsimeq"], ["≇", "\\ncong"],
      ["∤", "\\nmid"], ["≁", "\\nsim"], ["⋠", "\\npreceq"], ["⋡", "\\nsucceq"],
      ["⊲", "\\vartriangleleft"], ["⊳", "\\vartriangleright"],
      ["⊴", "\\trianglelefteq"], ["⊵", "\\trianglerighteq"],
      ["⋈", "\\bowtie"], ["⋉", "\\ltimes"], ["⋊", "\\rtimes"],
      ["≬", "\\between"], ["≍", "\\asymp"], ["⋍", "\\backsimeq"],
      ["⊨", "\\models"], ["⊢", "\\vdash"], ["⊣", "\\dashv"],
      ["⊩", "\\Vdash"], ["⊪", "\\Vvdash"], ["⊧", "\\Dashv"],
    ],
  },
  {
    id: "operators",
    items: [
      ["+", "+"], ["−", "-"], ["±", "\\pm"], ["∓", "\\mp"], ["×", "\\times"], ["÷", "\\div"],
      ["·", "\\cdot"], ["∗", "\\ast"], ["∘", "\\circ"], ["∙", "\\bullet"],
      ["∩", "\\cap"], ["∪", "\\cup"], ["∧", "\\wedge"], ["∨", "\\vee"],
      ["⊕", "\\oplus"], ["⊖", "\\ominus"], ["⊗", "\\otimes"], ["⊘", "\\oslash"],
      ["⊙", "\\odot"], ["⊚", "\\circledcirc"], ["⊛", "\\circledast"],
      ["⊡", "\\boxdot"], ["⊞", "\\boxplus"], ["⊟", "\\boxminus"],
      ["⨁", "\\bigoplus"], ["⨂", "\\bigotimes"], ["⨀", "\\bigodot"],
      ["⋄", "\\diamond"], ["◊", "\\lozenge"], ["△", "\\triangle"],
      ["▷", "\\triangleright"], ["◁", "\\triangleleft"],
      ["∔", "\\dotplus"], ["⨿", "\\amalg"], ["⊎", "\\uplus"],
      ["⋓", "\\Cup"], ["⋒", "\\Cap"], ["∖", "\\setminus"],
      ["⊓", "\\sqcap"], ["⊔", "\\sqcup"], ["†", "\\dagger"], ["‡", "\\ddagger"],
      ["′", "^{\\prime}"], ["″", "^{\\prime\\prime}"], ["‴", "^{\\prime\\prime\\prime}"],
      ["≀", "\\wr"], ["⋆", "\\star"],
    ],
  },
  {
    id: "bigops",
    items: [
      ["Σ", "\\sum"], ["∫", "\\int"], ["Π", "\\prod"], ["∏", "\\coprod"],
      ["∬", "\\iint"], ["∭", "\\iiint"], ["⨌", "\\iiiint"], ["∮", "\\oint"],
      ["∯", "\\oiint"], ["∰", "\\oiiint"], ["⨋", "\\sumint"],
      ["⋂", "\\bigcap"], ["⋃", "\\bigcup"], ["⋀", "\\bigwedge"], ["⋁", "\\bigvee"],
      ["⨁", "\\bigoplus"], ["⨂", "\\bigotimes"], ["⨆", "\\bigsqcup"], ["⨄", "\\biguplus"],
      ["⨉", "\\bigtimes"], ["∐", "\\amalg"],
    ],
  },
  {
    id: "arrows",
    items: [
      ["→", "\\rightarrow"], ["←", "\\leftarrow"], ["⇒", "\\Rightarrow"], ["⇐", "\\Leftarrow"],
      ["↔", "\\leftrightarrow"], ["⇔", "\\Leftrightarrow"],
      ["↑", "\\uparrow"], ["↓", "\\downarrow"], ["↦", "\\mapsto"], ["⟼", "\\longmapsto"],
      ["⟶", "\\longrightarrow"], ["⟵", "\\longleftarrow"],
      ["⟹", "\\Longrightarrow"], ["⟸", "\\Longleftarrow"], ["⟺", "\\Longleftrightarrow"],
      ["↗", "\\nearrow"], ["↘", "\\searrow"], ["↙", "\\swarrow"], ["↖", "\\nwarrow"],
      ["⇗", "\\Nearrow"], ["⇘", "\\Searrow"], ["⇙", "\\Swarrow"], ["⇖", "\\Nwarrow"],
      ["↪", "\\hookrightarrow"], ["↩", "\\hookleftarrow"],
      ["↠", "\\twoheadrightarrow"], ["↣", "\\rightarrowtail"],
      ["⇄", "\\rightleftarrows"], ["⇆", "\\leftrightarrows"],
      ["⇉", "\\rightrightarrows"], ["⇇", "\\leftleftarrows"],
      ["⇌", "\\rightleftharpoons"], ["⇋", "\\leftrightharpoons"],
      ["↝", "\\leadsto"], ["⇝", "\\rightsquigarrow"],
      ["⇢", "\\dashrightarrow"], ["⇠", "\\dashleftarrow"],
      ["↺", "\\circlearrowleft"], ["↻", "\\circlearrowright"],
      ["↶", "\\curvearrowleft"], ["↷", "\\curvearrowright"],
      ["⇀", "\\rightharpoonup"], ["⇁", "\\rightharpoondown"],
      ["↾", "\\upharpoonright"], ["↿", "\\upharpoonleft"],
      ["⇃", "\\downharpoonright"], ["⇂", "\\downharpoonleft"],
      ["↤", "\\mapsfrom"], ["⟻", "\\longmapsfrom"],
      ["↫", "\\looparrowleft"], ["↬", "\\looparrowright"],
    ],
  },
  {
    id: "sets",
    items: [
      ["∈", "\\in"], ["∉", "\\notin"], ["∋", "\\ni"], ["∌", "\\notni"],
      ["∅", "\\emptyset"], ["∅", "\\varnothing"],
      ["∀", "\\forall"], ["∃", "\\exists"], ["∄", "\\nexists"], ["¬", "\\neg"],
      ["∧", "\\land"], ["∨", "\\lor"], ["⟹", "\\implies"], ["⟺", "\\iff"],
      ["∴", "\\therefore"], ["∵", "\\because"],
      ["∁", "\\complement"], ["幂集", "\\mathcal{P}(#?)", "Power set"],
      ["补集", "#?^{c}", "Complement"],
      ["指示函数", "\\mathbf{1}_{#?}", "Indicator function"],
      ["对称差", "#? \\triangle #?", "Symmetric difference"],
      ["基数", "|#?|", "Cardinality"],
      ["ℝ", "\\mathbb{R}"], ["ℕ", "\\mathbb{N}"], ["ℤ", "\\mathbb{Z}"], ["ℚ", "\\mathbb{Q}"],
      ["ℂ", "\\mathbb{C}"], ["ℙ", "\\mathbb{P}"], ["ℍ", "\\mathbb{H}"],
      ["集族", "\\{#?\\}_{#?\\in #?}", "Family of sets"],
      ["集列上极限", "\\limsup_{n\\to\\infty} #?", "Set limsup"],
      ["集列下极限", "\\liminf_{n\\to\\infty} #?", "Set liminf"],
      ["⊤", "\\top"], ["⊥", "\\bot"],
    ],
  },
  {
    id: "functions",
    items: [
      ["sin", "\\sin"], ["cos", "\\cos"], ["tan", "\\tan"],
      ["log", "\\log"], ["ln", "\\ln"], ["lg", "\\lg"], ["exp", "\\exp"],
      ["lim", "\\lim"], ["max", "\\max"], ["min", "\\min"], ["sup", "\\sup"], ["inf", "\\inf"],
      ["argmax", "\\arg\\max"], ["argmin", "\\arg\\min"],
      ["sin⁻¹", "\\sin^{-1}"], ["cos⁻¹", "\\cos^{-1}"], ["tan⁻¹", "\\tan^{-1}"],
      ["sec", "\\sec"], ["csc", "\\csc"], ["cot", "\\cot"],
      ["arcsin", "\\arcsin"], ["arccos", "\\arccos"], ["arctan", "\\arctan"],
      ["sinh", "\\sinh"], ["cosh", "\\cosh"], ["tanh", "\\tanh"], ["coth", "\\coth"],
      ["sech", "\\operatorname{sech}"], ["csch", "\\operatorname{csch}"],
      ["det", "\\det"], ["dim", "\\dim"], ["gcd", "\\gcd"], ["lcm", "\\operatorname{lcm}"],
      ["arg", "\\arg"], ["deg", "\\deg"], ["ker", "\\ker"], ["hom", "\\hom"],
      ["Pr", "\\Pr"], ["sgn", "\\operatorname{sgn}"],
      ["mod", "\\bmod"], ["pmod", "\\pmod{#?}"],
      ["Re", "\\operatorname{Re}(#?)", "Real part"],
      ["Im", "\\operatorname{Im}(#?)", "Imaginary part"],
      ["cis", "\\operatorname{cis}(#?)", "cis"],
      ["sinc", "\\operatorname{sinc}(#?)", "Sinc"],
      ["rank", "\\operatorname{rank}"], ["span", "\\operatorname{span}"], ["tr", "\\operatorname{tr}"],
      ["erf", "\\operatorname{erf}"], ["erfc", "\\operatorname{erfc}"], ["erfi", "\\operatorname{erfi}"],
    ],
  },
  {
    id: "probability",
    structures: true,
    items: [
      ["概率", "\\mathbb{P}(#?)", "Probability"],
      ["期望", "\\mathbb{E}[#?]", "Expectation"],
      ["方差", "\\operatorname{Var}(#?)", "Variance"],
      ["标准差", "\\sigma(#?)", "Standard deviation"],
      ["协方差", "\\operatorname{Cov}(#?,#?)", "Covariance"],
      ["相关系数", "\\operatorname{Corr}(#?,#?)", "Correlation"],
      ["协方差矩阵", "\\Sigma", "Covariance matrix"],
      ["条件期望", "\\mathbb{E}[#?\\mid #?]", "Conditional expectation"],
      ["条件方差", "\\operatorname{Var}(#?\\mid #?)", "Conditional variance"],
      ["矩", "\\mathbb{E}[#?^{k}]", "Moment"],
      ["中心矩", "\\mathbb{E}[(#?-\\mu)^{k}]", "Central moment"],
      ["正态", "\\mathcal{N}(#?,#?)", "Normal distribution"],
      ["伯努利", "\\operatorname{Bernoulli}(#?)", "Bernoulli distribution"],
      ["二项", "\\operatorname{Bin}(#?,#?)", "Binomial distribution"],
      ["泊松", "\\operatorname{Poisson}(#?)", "Poisson distribution"],
      ["均匀", "\\operatorname{Uniform}(#?,#?)", "Uniform distribution"],
      ["指数", "\\operatorname{Exp}(#?)", "Exponential distribution"],
      ["几何", "\\operatorname{Geom}(#?)", "Geometric distribution"],
      ["多项", "\\operatorname{Multinomial}(#?,\\ldots)", "Multinomial distribution"],
      ["对数正态", "\\operatorname{LogNormal}(#?,#?)", "Log-normal distribution"],
      ["伽马", "\\Gamma(#?)", "Gamma distribution"],
      ["贝塔", "\\operatorname{Beta}(#?,#?)", "Beta distribution"],
      ["卡方", "\\chi^2_{(#?)}", "Chi-squared"],
      ["t 分布", "t_{(#?)}", "Student t"],
      ["F 分布", "F_{(#?,#?)}", "F-distribution"],
      ["条件", "#? \\mid #?", "Conditional bar"],
      ["独立", "#? \\perp\\!\\!\\!\\perp #?", "Independence"],
      ["贝叶斯", "\\mathbb{P}(A|B) = \\frac{\\mathbb{P}(B|A)\\mathbb{P}(A)}{\\mathbb{P}(B)}", "Bayes theorem"],
      ["似然", "\\mathcal{L}(#?;#?)", "Likelihood"],
      ["信息熵", "H(#?) = -\\sum p_i\\log p_i", "Entropy"],
      ["KL 散度", "D_{\\mathrm{KL}}(#?\\|#?)", "KL divergence"],
      ["互信息", "I(#?;#?)", "Mutual information"],
      ["特征函数", "\\varphi_{#?}(t) = \\mathbb{E}[e^{it#?}]", "Characteristic function"],
      ["生成函数", "M_{#?}(t) = \\mathbb{E}[e^{t#?}]", "Moment generating function"],
      ["大数定律", "\\bar{X}_n \\xrightarrow{p} \\mu", "Law of large numbers"],
      ["中心极限", "\\sqrt{n}(\\bar{X}_n-\\mu) \\xrightarrow{d} \\mathcal{N}(0,\\sigma^2)", "Central limit theorem"],
      ["马尔可夫", "\\mathbb{P}(X\\ge a) \\le \\frac{\\mathbb{E}[X]}{a}", "Markov inequality"],
      ["切比雪夫", "\\mathbb{P}(|X-\\mu|\\ge k\\sigma) \\le \\frac{1}{k^2}", "Chebyshev inequality"],
    ],
  },
  {
    id: "physics",
    structures: true,
    items: [
      ["牛顿第二定律", "\\mathbf{F} = m\\mathbf{a}", "Newton 2nd"],
      ["动能", "E_k = \\frac{1}{2}mv^2", "Kinetic energy"],
      ["动量", "\\mathbf{p} = m\\mathbf{v}", "Momentum"],
      ["角动量", "\\mathbf{L} = \\mathbf{r}\\times\\mathbf{p}", "Angular momentum"],
      ["扭矩", "\\boldsymbol{\\tau} = \\mathbf{r}\\times\\mathbf{F}", "Torque"],
      ["转动惯量", "I = \\int r^2\\,dm", "Moment of inertia"],
      ["角速度", "\\omega = \\frac{d\\theta}{dt}", "Angular velocity"],
      ["向心加速度", "a_c = \\frac{v^2}{r}", "Centripetal acceleration"],
      ["功", "W = \\int \\mathbf{F}\\cdot d\\mathbf{r}", "Work"],
      ["功率", "P = \\frac{dW}{dt} = \\mathbf{F}\\cdot\\mathbf{v}", "Power"],
      ["万有引力", "F = G\\frac{m_1 m_2}{r^2}", "Gravity"],
      ["引力势能", "U = -\\frac{GMm}{r}", "Gravitational potential"],
      ["胡克定律", "F = -k x", "Hooke law"],
      ["弹簧势能", "U = \\frac{1}{2}kx^2", "Spring potential"],
      ["简谐运动", "x(t) = A\\cos(\\omega t + \\phi)", "SHM"],
      ["简谐周期", "T = 2\\pi\\sqrt{\\frac{m}{k}}", "SHM period"],
      ["单摆周期", "T = 2\\pi\\sqrt{\\frac{L}{g}}", "Pendulum period"],
      ["欧姆定律", "V = IR", "Ohm law"],
      ["功率电学", "P = I^2 R = IV", "Electric power"],
      ["焦耳定律", "P = I^2 R", "Joule heating"],
      ["电容", "C = \\frac{Q}{V}", "Capacitance"],
      ["RC 充电", "V(t) = V_0(1-e^{-t/RC})", "RC charging"],
      ["RC 放电", "V(t) = V_0e^{-t/RC}", "RC discharging"],
      ["电感", "\\mathcal{E} = -L\\frac{dI}{dt}", "Inductance"],
      ["库仑定律", "F = k_e\\frac{q_1 q_2}{r^2}", "Coulomb law"],
      ["电场", "\\mathbf{E} = \\frac{\\mathbf{F}}{q}", "Electric field"],
      ["电势", "V = -\\int \\mathbf{E}\\cdot d\\mathbf{l}", "Electric potential"],
      ["电偶极矩", "\\mathbf{p} = q\\mathbf{d}", "Dipole moment"],
      ["高斯定律", "\\oint \\mathbf{E}\\cdot d\\mathbf{A} = \\frac{Q}{\\varepsilon_0}", "Gauss law"],
      ["法拉第定律", "\\mathcal{E} = -\\frac{d\\Phi_B}{dt}", "Faraday law"],
      ["安培定律", "\\oint \\mathbf{B}\\cdot d\\mathbf{l} = \\mu_0 I", "Ampere law"],
      ["毕奥-萨伐尔", "d\\mathbf{B} = \\frac{\\mu_0}{4\\pi}\\frac{I\\,d\\mathbf{l}\\times\\hat{r}}{r^2}", "Biot-Savart law"],
      ["洛伦兹力", "\\mathbf{F} = q(\\mathbf{E} + \\mathbf{v}\\times\\mathbf{B})", "Lorentz force"],
      ["磁矢势", "\\mathbf{B} = \\nabla\\times\\mathbf{A}", "Magnetic vector potential"],
      ["麦克斯韦", "\\nabla\\cdot\\mathbf{E}=\\frac{\\rho}{\\varepsilon_0},\\; \\nabla\\cdot\\mathbf{B}=0,\\; \\nabla\\times\\mathbf{E}=-\\frac{\\partial\\mathbf{B}}{\\partial t},\\; \\nabla\\times\\mathbf{B}=\\mu_0\\mathbf{J}+\\mu_0\\varepsilon_0\\frac{\\partial\\mathbf{E}}{\\partial t}", "Maxwell eqns"],
      ["理想气体", "PV = nRT", "Ideal gas law"],
      ["热力学第一定律", "\\Delta U = Q - W", "1st law thermo"],
      ["熵", "dS = \\frac{dQ_{\\text{rev}}}{T}", "Entropy"],
      ["玻尔兹曼", "S = k_B \\ln W", "Boltzmann entropy"],
      ["热容", "Q = mc\\Delta T", "Heat capacity"],
      ["潜热", "Q = mL", "Latent heat"],
      ["卡诺效率", "\\eta_C = 1 - \\frac{T_c}{T_h}", "Carnot efficiency"],
      ["自由能", "F = U - TS", "Helmholtz free energy"],
      ["吉布斯自由能", "G = H - TS", "Gibbs free energy"],
      ["焓", "H = U + PV", "Enthalpy"],
      ["伯努利", "P + \\frac12\\rho v^2 + \\rho gh = \\text{const}", "Bernoulli eqn"],
      ["浮力", "F_b = \\rho gV", "Buoyancy"],
      ["连续性", "A_1v_1 = A_2v_2", "Continuity eqn"],
      ["薛定谔方程", "i\\hbar\\frac{\\partial}{\\partial t}\\Psi = \\hat{H}\\Psi", "Schrodinger eqn"],
      ["质能方程", "E = mc^2", "Mass-energy"],
      ["不确定性", "\\Delta x\\,\\Delta p \\geq \\frac{\\hbar}{2}", "Uncertainty"],
      ["光电效应", "E_{\\text{max}} = h\\nu - \\phi", "Photoelectric"],
      ["德布罗意", "\\lambda = \\frac{h}{p}", "de Broglie"],
      ["黑体辐射", "I(\\nu,T) = \\frac{2h\\nu^3}{c^2}\\frac{1}{e^{h\\nu/k_B T}-1}", "Planck law"],
      ["衰变定律", "N(t) = N_0e^{-\\lambda t}", "Decay law"],
      ["半衰期", "T_{1/2} = \\frac{\\ln 2}{\\lambda}", "Half-life"],
      ["折射定律", "n_1\\sin\\theta_1 = n_2\\sin\\theta_2", "Snell law"],
      ["多普勒", "f' = f\\frac{c \\pm v_r}{c \\mp v_s}", "Doppler effect"],
      ["杨氏双缝", "d\\sin\\theta = m\\lambda", "Young double-slit"],
      ["相对论动量", "E^2 = (pc)^2 + (mc^2)^2", "Energy-momentum"],
    ],
  },
  {
    id: "chemistry",
    structures: true,
    items: [
      ["化学式", "\\ce{ #? }", "Formula"],
      ["反应式", "\\ce{ #? -> #? }", "Reaction"],
      ["可逆", "\\ce{ #? <=> #? }", "Reversible"],
      ["共振", "\\ce{ #? <-> #? }", "Resonance"],
      ["上下箭头", "\\ce{ #? ->[#?][#?] #? }", "Arrow with text"],
      ["H₂O", "\\ce{H2O}", "Water"],
      ["CO₂", "\\ce{CO2}", "Carbon dioxide"],
      ["O₂", "\\ce{O2}", "Oxygen"],
      ["NaCl", "\\ce{NaCl}", "Sodium chloride"],
      ["HCl", "\\ce{HCl}", "Hydrochloric acid"],
      ["HNO₃", "\\ce{HNO3}", "Nitric acid"],
      ["H₂SO₄", "\\ce{H2SO4}", "Sulfuric acid"],
      ["CH₄", "\\ce{CH4}", "Methane"],
      ["C₂H₅OH", "\\ce{C2H5OH}", "Ethanol"],
      ["C₆H₆", "\\ce{C6H6}", "Benzene"],
      ["CH₃COOH", "\\ce{CH3COOH}", "Acetic acid"],
      ["NH₃", "\\ce{NH3}", "Ammonia"],
      ["NaOH", "\\ce{NaOH}", "Sodium hydroxide"],
      ["H₂O₂", "\\ce{H2O2}", "Hydrogen peroxide"],
      ["KMnO₄", "\\ce{KMnO4}", "Potassium permanganate"],
      ["H⁺", "\\ce{H+}", "Proton"],
      ["OH⁻", "\\ce{OH-}", "Hydroxide"],
      ["SO₄²⁻", "\\ce{SO4^2-}", "Sulfate"],
      ["NO₃⁻", "\\ce{NO3-}", "Nitrate"],
      ["CO₃²⁻", "\\ce{CO3^2-}", "Carbonate"],
      ["NH₄⁺", "\\ce{NH4+}", "Ammonium"],
      ["Fe²⁺", "\\ce{Fe^2+}", "Iron(II)"],
      ["Fe³⁺", "\\ce{Fe^3+}", "Iron(III)"],
      ["→", "\\rightarrow"], ["⇌", "\\rightleftharpoons"], ["↑", "\\uparrow"], ["↓", "\\downarrow"],
      ["aq", "\\mathrm{(aq)}"], ["s", "\\mathrm{(s)}"], ["l", "\\mathrm{(l)}"], ["g", "\\mathrm{(g)}"],
      ["pH", "\\mathrm{pH} = -\\log[\\ce{H+}]", "pH"],
      ["pOH", "\\mathrm{pOH} = -\\log[\\ce{OH-}]", "pOH"],
      ["Kw", "K_w = [\\ce{H+}][\\ce{OH-}] = 10^{-14}", "Kw"],
      ["Ka", "K_a = \\frac{[\\ce{H+}][\\ce{A-}]}{[\\ce{HA}]}", "Ka"],
      ["Henderson-Hasselbalch", "\\mathrm{pH} = \\mathrm{p}K_a + \\log\\frac{[\\ce{A-}]}{[\\ce{HA}]}", "Henderson-Hasselbalch"],
      ["平衡常数", "K_c = \\frac{[\\ce{C}]^c[\\ce{D}]^d}{[\\ce{A}]^a[\\ce{B}]^b}", "Equilibrium constant"],
      ["反应商", "Q = \\frac{[\\ce{C}]^c[\\ce{D}]^d}{[\\ce{A}]^a[\\ce{B}]^b}", "Reaction quotient"],
      ["ΔH", "\\Delta H", "Enthalpy change"],
      ["ΔS", "\\Delta S", "Entropy change"],
      ["ΔG", "\\Delta G = \\Delta H - T\\Delta S", "Gibbs free energy"],
      ["能斯特", "E = E^\\circ - \\frac{RT}{nF}\\ln Q", "Nernst equation"],
      ["Arrhenius", "k = Ae^{-E_a/RT}", "Arrhenius eqn"],
      ["速率方程", "\\text{rate} = k[\\ce{A}]^m[\\ce{B}]^n", "Rate law"],
      ["Beer-Lambert", "A = \\varepsilon cl", "Beer-Lambert law"],
      ["△", "\\triangle"], ["催化", "\\xrightarrow{\\text{#?}}", "catalyst"],
      ["沉淀", "\\downarrow", "precipitate"], ["气体", "\\uparrow", "gas"],
    ],
  },
  {
    id: "accents",
    items: [
      ["𝐱", "\\mathbf{#?}"], ["ℝ", "\\mathbb{#?}"], ["𝓧", "\\mathcal{#?}"],
      ["𝓛", "\\mathscr{#?}"], ["𝖠", "\\mathsf{#?}"], ["𝚃", "\\mathtt{#?}"],
      ["x̂", "\\hat{x}"], ["x̄", "\\bar{x}"], ["x̃", "\\tilde{x}"], ["x⃗", "\\vec{x}"],
      ["ẋ", "\\dot{x}"], ["ẍ", "\\ddot{x}"],
      ["x̲", "\\underline{x}"], ["x̅", "\\overline{x}"],
      ["𝜶", "\\boldsymbol{#?}", "boldsymbol"],
      ["x̂̅", "\\widehat{#?}", "Wide hat"],
      ["x̃̅", "\\widetilde{#?}", "Wide tilde"],
      ["x̀", "\\grave{x}"], ["x́", "\\acute{x}"],
      ["x̌", "\\check{x}"], ["x̆", "\\breve{x}"], ["x̊", "\\mathring{x}"],
      ["𝑥", "\\mathit{#?}"], ["𝔁", "\\mathfrak{#?}"],
      ["text", "\\text{#?}"], ["rm", "\\mathrm{#?}"],
      ["ı", "\\imath"], ["ȷ", "\\jmath"],
    ],
  },
  {
    id: "misc",
    items: [
      ["⋯", "\\cdots"], ["…", "\\dots"], ["⋮", "\\vdots"], ["⋱", "\\ddots"],
      ["∞", "\\infty"], ["ℏ", "\\hbar"], ["ℓ", "\\ell"],
      ["∠", "\\angle"], ["∡", "\\measuredangle"], ["∢", "\\sphericalangle"],
      ["°", "^\\circ"], ["ℜ", "\\Re"], ["ℑ", "\\Im"], ["℘", "\\wp"],
      ["ı", "\\imath"], ["ȷ", "\\jmath"],
      ["△", "\\triangle"], ["□", "\\Box"], ["◇", "\\Diamond"],
      ["■", "\\blacksquare"], ["▲", "\\blacktriangle"], ["◆", "\\blacklozenge"],
      ["♠", "\\spadesuit"], ["♥", "\\heartsuit"], ["♣", "\\clubsuit"], ["♦", "\\diamondsuit"],
      ["★", "\\bigstar"], ["♮", "\\natural"], ["♭", "\\flat"], ["♯", "\\sharp"],
      ["✓", "\\checkmark"], ["✗", "\\times"], ["§", "\\S"], ["¶", "\\P"],
      ["©", "\\copyright"], ["®", "\\circledR"], ["¥", "\\yen"], ["£", "\\pounds"],
      ["µ", "\\textmu"], ["ð", "\\eth"], ["Ⅎ", "\\Finv"], ["⅁", "\\Game"],
      ["†", "\\dag"], ["‡", "\\ddag"],
    ],
  },
];

let mathfield = null;
let locale = "zh";
let mode = "insert";
let pendingInit = null;

const host = document.getElementById("mathfieldHost");
const latexSource = document.getElementById("latexSource");
const statusText = document.getElementById("statusText");
const cancelButton = document.getElementById("cancelButton");
const acceptButton = document.getElementById("acceptButton");
const tabs = document.getElementById("libraryTabs");
const titleText = document.getElementById("libraryTitleText");
const grid = document.getElementById("symbolGrid");
const searchInput = document.getElementById("symbolSearch");

function strings() {
  return locale.startsWith("zh") ? STRINGS.zh : STRINGS.en;
}

function displayLabel(item) {
  if (locale.startsWith("zh")) {
    return item[0];
  }

  return item[2] || item[0];
}

function groupTitle(group) {
  return strings().tabs[group.id] || group.id;
}

function send(message) {
  window.chrome?.webview?.postMessage(message);
}

function setStatus(text) {
  statusText.textContent = text || "";
}

function currentLatex() {
  const source = latexSource.value.trim();
  if (isMathMlSource(source)) {
    return source;
  }

  return mathfield?.getValue("latex-expanded")?.trim() || "";
}

function syncSource() {
  latexSource.value = currentLatex();
}

function setLatex(latex) {
  const source = latex || "";
  if (isMathMlSource(source.trim())) {
    latexSource.value = source;
    mathfield.setValue("", { silenceNotifications: true });
    return;
  }

  mathfield.setValue(source, { silenceNotifications: true });
  syncSource();
}

function isMathMlSource(source) {
  return /^<math(\s|>|:)/i.test(source);
}

function insertLatex(latex) {
  if (latex.startsWith("matrix:")) {
    insertMatrix(latex.slice("matrix:".length));
    return;
  }

  mathfield.insert(latex, { format: "latex" });
  mathfield.focus();
  syncSource();
}

function insertMatrix(env, rows = 2, cols = 2) {
  if (env === "cases") {
    cols = 2;
  }

  if (env === "hessian") {
    const body = Array.from({ length: rows }, (_, i) =>
      Array.from({ length: cols }, (_, j) =>
        `\\frac{\\partial^2 #?}{\\partial #?_{${i + 1}}\\partial #?_{${j + 1}}}`
      ).join(" & ")
    ).join(" \\\\ ");
    mathfield.insert(`\\begin{bmatrix} ${body} \\end{bmatrix}`, { format: "latex" });
    mathfield.focus();
    syncSource();
    return;
  }

  const body = Array.from({ length: rows }, () => Array.from({ length: cols }, () => "#?").join(" & ")).join(" \\\\ ");
  mathfield.insert(`\\begin{${env}} ${body} \\end{${env}}`, { format: "latex" });
  mathfield.focus();
  syncSource();
}

let _currentGroup = null;

function selectGroup(group) {
  _currentGroup = group;
  searchInput.value = "";
  for (const button of tabs.querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.group === group.id);
  }

  titleText.textContent = groupTitle(group);
  renderGrid(group, "");
}

function renderGrid(group, query) {
  grid.className = group.structures ? "symbol-grid structures" : "symbol-grid";
  grid.replaceChildren();
  const q = query.trim().toLowerCase();
  for (const item of group.items) {
    if (q && !matchItem(item, q)) continue;

    if (group.structures && String(item[1]).startsWith("matrix:")) {
      grid.appendChild(createMatrixControl(displayLabel(item), item[1].slice("matrix:".length)));
      continue;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = displayLabel(item);
    button.title = item[2] ? `${item[2]}\n${item[1]}` : item[1];
    button.addEventListener("click", () => insertLatex(item[1]));
    grid.appendChild(button);
  }
}

function matchItem(item, query) {
  const label = displayLabel(item).toLowerCase();
  const latex = item[1].toLowerCase();
  return label.includes(query) || latex.includes(query);
}

searchInput.addEventListener("input", () => {
  if (_currentGroup) renderGrid(_currentGroup, searchInput.value);
});

function createMatrixControl(label, env) {
  const isCases = env === "cases";
  const row = document.createElement("div");
  row.className = isCases ? "matrix-row cases" : "matrix-row";

  const rowSelect = document.createElement("select");
  rowSelect.title = strings().rows;
  for (let i = 1; i <= 10; i++) {
    rowSelect.appendChild(new Option(String(i), String(i), i === 2, i === 2));
  }
  row.appendChild(rowSelect);

  let colSelect = null;
  if (!isCases) {
    colSelect = document.createElement("select");
    colSelect.title = strings().columns;
    for (let i = 1; i <= 10; i++) {
      colSelect.appendChild(new Option(String(i), String(i), i === 2, i === 2));
    }
    row.appendChild(colSelect);
  }

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.title = `\\begin{${env}}...\\end{${env}}`;
  button.addEventListener("click", () => {
    insertMatrix(env, Number(rowSelect.value), colSelect ? Number(colSelect.value) : 2);
  });
  row.appendChild(button);
  return row;
}

function buildLibrary() {
  tabs.replaceChildren();
  for (const group of GROUPS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tab";
    button.dataset.group = group.id;
    button.textContent = groupTitle(group);
    button.title = groupTitle(group);
    button.addEventListener("click", () => selectGroup(group));
    tabs.appendChild(button);
  }

  selectGroup(GROUPS[0]);
}

function accept() {
  const latex = currentLatex();
  if (!latex) {
    setStatus(strings().latexRequired);
    return;
  }

  send({ type: "accept", latex, display: true });
}

function hideVirtualKeyboard() {
  window.mathVirtualKeyboard?.hide();
  mathfield?.focus();
}

function configureText() {
  document.documentElement.lang = locale.startsWith("zh") ? "zh-CN" : "en";
  cancelButton.textContent = strings().cancel;
  acceptButton.textContent = mode === "update" ? strings().acceptUpdate : strings().acceptInsert;
  setStatus(strings().ready);
  buildLibrary();
}

function applyInit(payload) {
  locale = String(payload?.locale || "zh").toLowerCase();
  mode = payload?.mode === "update" ? "update" : "insert";
  configureText();
  setLatex(payload?.latex || "");
  mathfield?.focus();
}

async function bootstrap() {
  MathfieldElement.fontsDirectory = new URL("./vendor/fonts", window.location.href).href;
  mathfield = new MathfieldElement();
  mathfield.smartFence = true;
  mathfield.smartMode = false;
  mathfield.mathVirtualKeyboardPolicy = "onfocus";
  mathfield.defaultMode = "math";
  host.appendChild(mathfield);
  mathfield.addEventListener("input", syncSource);
  latexSource.addEventListener("input", () => {
    const source = latexSource.value || "";
    if (!isMathMlSource(source.trim())) {
      mathfield.setValue(source, { silenceNotifications: true });
    }

    mathfield.focus();
  });
  cancelButton.addEventListener("click", () => send({ type: "cancel" }));
  acceptButton.addEventListener("click", accept);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      hideVirtualKeyboard();
      return;
    }

    if (event.key === "Enter" && !event.isComposing && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
      event.preventDefault();
      accept();
    }
  });
  configureText();
  if (pendingInit || window.__latexSnipperPendingInit) {
    applyInit(pendingInit || window.__latexSnipperPendingInit);
    pendingInit = null;
    window.__latexSnipperPendingInit = null;
  }
  mathfield.focus();
}

window.LaTeXSnipperEditor = {
  init(payload) {
    pendingInit = payload;
    if (mathfield) {
      applyInit(payload);
      pendingInit = null;
    }
  },
};

bootstrap().catch((error) => setStatus(String(error)));
